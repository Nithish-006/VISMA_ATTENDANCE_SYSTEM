from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import validates
from datetime import datetime

db = SQLAlchemy()

# Canonical teams a worker can belong to. Single source of truth shared by the
# Worker.team dropdowns, the /api/teams endpoint and the backfill script, so the
# three never drift. A worker's team is a label on the master record (like
# designation); the app slices attendance/salary by it via the worker master.
TEAMS = ['Rajeeb', 'Visma', 'Ambeth']


def _normalize_name(value):
    """Canonical form for a worker name: trimmed and fully upper-cased.

    Enforced at the model layer so every write path (add-worker, salary edit,
    bulk import) stores names identically, regardless of how the caller typed
    them. Returns the value untouched if it isn't a string (e.g. None).
    """
    if isinstance(value, str):
        return value.strip().upper()
    return value


class Worker(db.Model):
    """Master record for a worker — the single source of truth for identity.

    Name, designation and the current default day-rate live here in exactly
    ONE row. The monthly `salary` rows and daily `attendance` rows reference a
    worker by id. Previously this identity was copied onto every monthly salary
    row (so the worker "existed" only as a side effect of having salary rows),
    which caused update anomalies and made editing a multi-row rewrite. Worker
    normalizes that: edit once here, and it is the authoritative source.

    The per-month `salary.base_salary_per_day` is intentionally retained as the
    historical rate actually paid that month; this column is the *current*
    default rate used when computing new/recalculated months.
    """
    __tablename__ = 'worker'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    designation = db.Column(db.String(50))
    # The team this worker belongs to (one of models.TEAMS). A plain label on the
    # master record — the app filters/groups attendance and salary by it live.
    team = db.Column(db.String(50))
    base_salary_per_day = db.Column(db.Numeric(10, 2), default=0)
    # Pay model. Daily-rate workers (default) earn overtime at the hourly rate
    # (day-rate / 8). Monthly-salaried workers are paid base_salary_per_day x
    # present days only — their overtime is still recorded against the day/site
    # for tracking, but is never added to their pay. This flag is the single
    # switch the salary calculation reads to decide whether OT is paid.
    monthly_salaried = db.Column(db.Boolean, nullable=False, default=False)
    # Soft-delete flag. Wage history should not be destroyed outright; this lets
    # a worker be hidden without deleting their records. (The delete endpoint
    # still hard-deletes for now to preserve current behaviour — see routes.)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    @validates('name')
    def _uppercase_name(self, key, value):
        return _normalize_name(value)

    def to_dict(self):
        return {
            'id': self.id,
            'worker_id': self.id,
            'name': self.name,
            'designation': self.designation,
            'team': self.team,
            'base_salary_per_day': float(self.base_salary_per_day) if self.base_salary_per_day else 0,
            'monthly_salaried': bool(self.monthly_salaried),
            'active': self.active,
        }


class Salary(db.Model):
    """Monthly salary records - one row per worker per month."""
    __tablename__ = 'salary'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('worker.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    designation = db.Column(db.String(50))
    base_salary_per_day = db.Column(db.Numeric(10, 2), default=0)
    # The pay model that applied THIS month, snapshotted from the worker master
    # when the month was computed. Stored per month (not read live) so that
    # converting a worker to/from monthly-salaried never rewrites how an earlier
    # month was paid — last month stays on the rule it was actually paid under.
    monthly_salaried = db.Column(db.Boolean, nullable=False, default=False)
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)  # 1-12
    total_working_days = db.Column(db.Integer, default=0)
    ot_hours = db.Column(db.Numeric(6, 2), default=0)
    total_salary = db.Column(db.Numeric(12, 2), default=0)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    __table_args__ = (
        db.UniqueConstraint('worker_id', 'year', 'month', name='unique_worker_month'),
    )

    @validates('name')
    def _uppercase_name(self, key, value):
        return _normalize_name(value)

    def to_dict(self):
        return {
            'id': self.id,
            'worker_id': self.worker_id,
            'name': self.name,
            'designation': self.designation,
            'base_salary_per_day': float(self.base_salary_per_day) if self.base_salary_per_day else 0,
            'monthly_salaried': bool(self.monthly_salaried),
            'year': self.year,
            'month': self.month,
            'total_working_days': self.total_working_days,
            'ot_hours': float(self.ot_hours) if self.ot_hours else 0,
            'total_salary': float(self.total_salary) if self.total_salary else 0
        }


class Supervisor(db.Model):
    """Supervisors who mark attendance. Workers are not fixed to a supervisor."""
    __tablename__ = 'supervisor'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False, unique=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name
        }


class Attendance(db.Model):
    """Attendance records - daily attendance linked to worker."""
    __tablename__ = 'attendance'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('worker.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    # 'H' is retained for legacy data; new marking only uses 'P'/'A'.
    status = db.Column(db.Enum('P', 'A', 'H', name='attendance_status'), default='A')
    ot_hours = db.Column(db.Numeric(4, 2), default=0)
    project = db.Column(db.String(300))  # holds canonical "{id} - {stem_name}"
    supervisor_id = db.Column(db.Integer, db.ForeignKey('supervisor.id'))  # who marked it (nullable for legacy records)
    # Role for this day — a snapshot of the worker's fixed designation at
    # marking time (the Mark UI copies it from the worker, it isn't chosen).
    role = db.Column(db.String(50))
    # The specific work done that day (e.g. welding, grinding). Unlike role,
    # work is elastic and chosen per attendance record at marking time.
    work = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    __table_args__ = (
        db.UniqueConstraint('worker_id', 'date', name='unique_daily_attendance'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'worker_id': self.worker_id,
            'date': self.date.isoformat() if self.date else None,
            'status': self.status,
            'ot_hours': float(self.ot_hours) if self.ot_hours else 0,
            'project': self.project,
            'supervisor_id': self.supervisor_id,
            'role': self.role,
            'work': self.work
        }


def compute_pay(base_salary, working_days, ot_hours, monthly_salaried=False):
    """Single source of truth for turning attendance into pay.

    Returns (base_pay, ot_pay, total). Overtime is paid at the hourly rate
    (day-rate / 8) for daily-rate workers, but NEVER for monthly-salaried
    workers — for them OT is recorded for site/day tracking only and excluded
    from pay. Every place that prices attendance must call this so the rule
    stays consistent across the salary view, recalculation and summaries.
    """
    base_salary = float(base_salary or 0)
    working_days = working_days or 0
    ot_hours = float(ot_hours or 0)
    base_pay = working_days * base_salary
    if monthly_salaried or base_salary <= 0:
        ot_pay = 0.0
    else:
        ot_pay = (base_salary / 8) * ot_hours
    return base_pay, ot_pay, base_pay + ot_pay
