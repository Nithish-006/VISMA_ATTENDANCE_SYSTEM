"""Backfill the new `worker` master table and fix worker-id referential integrity.

Background
----------
Worker identity (name / designation / day-rate) used to live ONLY as copies on
every monthly `salary` row, and the database enforced a single hidden foreign
key `attendance.worker_id -> salary.worker_id` (named `attendance_ibfk_1`).
This script introduces a proper `worker` master table as the single source of
truth and repoints the foreign keys at it.

What it does
------------
  1. Creates exactly one `worker` row per existing worker_id, copying
     name/designation/base_salary_per_day from that worker's LATEST salary row
     and preserving the original worker_id as `worker.id` (so all existing
     attendance/salary rows still line up). Idempotent: existing worker rows
     are left untouched.
  2. Repoints referential integrity (only when no orphan rows would be
     violated):
       - drops the old `attendance_ibfk_1` (attendance -> salary)
       - adds  fk_attendance_worker     (attendance.worker_id  -> worker.id)
       - adds  fk_salary_worker         (salary.worker_id      -> worker.id)
       - adds  fk_attendance_supervisor (attendance.supervisor_id -> supervisor.id)
  3. Bumps the worker AUTO_INCREMENT past the highest existing id.

It is NON-destructive to attendance/salary data and changes no application
behaviour: the FK delete semantics (RESTRICT) match the previous hidden FK, and
the app already deletes child rows before parents.

Usage
-----
    venv\\Scripts\\python.exe migrate_workers.py            # dry run (no writes)
    venv\\Scripts\\python.exe migrate_workers.py --apply    # commit changes
"""
import sys

from app import app
from models import db, Worker
from sqlalchemy import text


def _existing_fk_names(schema):
    rows = db.session.execute(text(
        "SELECT constraint_name FROM information_schema.TABLE_CONSTRAINTS "
        "WHERE table_schema=:s AND constraint_type='FOREIGN KEY'"
    ), {"s": schema}).fetchall()
    return {r[0] for r in rows}


def run(apply):
    with app.app_context():
        schema = db.session.execute(text("SELECT DATABASE()")).scalar()

        # --- 1. Determine the worker set from the latest salary row per id ----
        # Union with attendance to be safe, though they are known to match.
        latest = db.session.execute(text("""
            SELECT s.worker_id, s.name, s.designation, s.base_salary_per_day
            FROM salary s
            JOIN (
                SELECT worker_id, MAX(year*100+month) AS mp
                FROM salary GROUP BY worker_id
            ) m ON s.worker_id = m.worker_id AND (s.year*100+s.month) = m.mp
        """)).fetchall()
        salary_workers = {r[0]: r for r in latest}

        att_only = db.session.execute(text(
            "SELECT DISTINCT worker_id FROM attendance "
            "WHERE worker_id NOT IN (SELECT worker_id FROM salary)"
        )).fetchall()
        orphan_att_ids = [r[0] for r in att_only]

        existing_worker_ids = {w.id for w in Worker.query.all()}

        to_create = [r for wid, r in salary_workers.items() if wid not in existing_worker_ids]

        print("=== Worker backfill ===")
        print(f"  workers found in salary : {len(salary_workers)}")
        print(f"  worker rows already present: {len(existing_worker_ids)}")
        print(f"  worker rows to create   : {len(to_create)}")
        if orphan_att_ids:
            print(f"  WARNING: attendance worker_ids with no salary row: {orphan_att_ids}")
            print("           (these would have no identity; aborting FK step)")
        for r in to_create:
            print(f"    + worker {r[0]:>3}  {r[1]!r:30} {r[2]!r:18} rate={r[3]}")

        if apply and to_create:
            for r in to_create:
                db.session.add(Worker(
                    id=r[0], name=r[1], designation=r[2],
                    base_salary_per_day=r[3] if r[3] is not None else 0,
                    active=True,
                ))
            db.session.commit()
            print(f"  -> inserted {len(to_create)} worker rows")

        # --- 2. Referential integrity --------------------------------------
        # Recompute orphans against the worker table that now (would) exist.
        att_no_worker = db.session.execute(text(
            "SELECT COUNT(*) FROM attendance WHERE worker_id NOT IN (SELECT id FROM worker)"
        )).scalar() if apply else len(orphan_att_ids)
        sal_no_worker = db.session.execute(text(
            "SELECT COUNT(*) FROM salary WHERE worker_id NOT IN (SELECT id FROM worker)"
        )).scalar() if apply else (len(salary_workers) - len(salary_workers))
        sup_orphans = db.session.execute(text(
            "SELECT COUNT(*) FROM attendance WHERE supervisor_id IS NOT NULL "
            "AND supervisor_id NOT IN (SELECT id FROM supervisor)"
        )).scalar()

        print("\n=== Foreign keys ===")
        print(f"  attendance rows lacking a worker : {att_no_worker}")
        print(f"  salary rows lacking a worker     : {sal_no_worker}")
        print(f"  attendance rows w/ orphan supervisor_id : {sup_orphans}")

        fks = _existing_fk_names(schema)
        plan = []
        if 'attendance_ibfk_1' in fks:
            plan.append(("DROP old attendance->salary FK (attendance_ibfk_1)",
                         "ALTER TABLE attendance DROP FOREIGN KEY attendance_ibfk_1"))
        if 'fk_attendance_worker' not in fks:
            plan.append(("ADD fk_attendance_worker (attendance.worker_id -> worker.id)",
                         "ALTER TABLE attendance ADD CONSTRAINT fk_attendance_worker "
                         "FOREIGN KEY (worker_id) REFERENCES worker(id)"))
        if 'fk_salary_worker' not in fks:
            plan.append(("ADD fk_salary_worker (salary.worker_id -> worker.id)",
                         "ALTER TABLE salary ADD CONSTRAINT fk_salary_worker "
                         "FOREIGN KEY (worker_id) REFERENCES worker(id)"))
        if 'fk_attendance_supervisor' not in fks and sup_orphans == 0:
            plan.append(("ADD fk_attendance_supervisor (attendance.supervisor_id -> supervisor.id)",
                         "ALTER TABLE attendance ADD CONSTRAINT fk_attendance_supervisor "
                         "FOREIGN KEY (supervisor_id) REFERENCES supervisor(id)"))

        if not plan:
            print("  FK structure already up to date — nothing to do.")
        for desc, _ in plan:
            print(f"    * {desc}")

        # Guard: never add worker FKs while orphan rows exist.
        safe = (att_no_worker == 0 and sal_no_worker == 0)
        if not safe:
            print("  ABORTING FK changes: orphan rows present. Backfill first.")
            plan = []

        if apply and plan:
            for desc, sql in plan:
                db.session.execute(text(sql))
            db.session.commit()
            # Keep AUTO_INCREMENT ahead of the highest explicit id.
            max_id = db.session.execute(text("SELECT COALESCE(MAX(id),0) FROM worker")).scalar()
            db.session.execute(text(f"ALTER TABLE worker AUTO_INCREMENT = {max_id + 1}"))
            db.session.commit()
            print(f"  -> applied {len(plan)} FK change(s); worker AUTO_INCREMENT set to {max_id + 1}")

        if not apply:
            print("\n(dry run — no changes written. Re-run with --apply to commit.)")


if __name__ == '__main__':
    run(apply='--apply' in sys.argv)
