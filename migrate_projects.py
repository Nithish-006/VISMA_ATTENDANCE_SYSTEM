"""Normalize existing attendance project values to the canonical registry form.

Old attendance records stored the project as free text. The registry now owns
the canonical value "{id} - {stem_name}" (e.g. "655 - RCH"). This script:

  - reads the canonical projects from the VISMA registry,
  - scans the distinct project values currently on attendance records,
  - normalizes any value that matches a registry stem_name (case-insensitive)
    to the canonical "{id} - {stem_name}" string,
  - reports values that DON'T match so they can be mapped by hand.

It does NOT guess. Anything that isn't already canonical or an exact
stem_name match is left untouched and listed for manual review.

Usage:
    venv\\Scripts\\python.exe migrate_projects.py            # dry run (no writes)
    venv\\Scripts\\python.exe migrate_projects.py --apply    # commit changes
"""
import sys

from app import app
from models import db, Attendance
from services.projects_registry import get_projects, canonical_value
from sqlalchemy import create_engine, text
from config import Config


# Hand-confirmed mappings for values that don't exactly match a registry
# stem_name. Keyed by the exact old attendance value -> canonical target.
# `Mandabam` and `sri Ram` are intentionally left out (no confident target);
# they stay as-is and will be reported as unmatched for manual handling.
MANUAL_MAP = {
    'CB': '655 - RCH',
    'CT': '655 - RCH',
    'Factory': '2 - FACTORY EXPENSE',
    'GAS GM': '655 - RCH',
    'GAS MANI': '655 - RCH',
    'Palson': '647 - POLSONS',
    'RCH  MANI': '655 - RCH',
    'RCH CB': '655 - RCH',
    'RCH CT': '655 - RCH',
    'RCH GAS': '655 - RCH',
    'RCH GAS MANI': '655 - RCH',
    'RCH GAS MANIFILD': '655 - RCH',
    'RCH GAS MANIFOLD': '655 - RCH',
    'RCH GM': '655 - RCH',
    'RCH LPG': '655 - RCH',
    'RCH MANI': '655 - RCH',
    'RCH MANIFOLD': '655 - RCH',
    'Rch dinning': '655 - RCH',
    'SEM': '635 - SHANMATHI CONSTRUCTIONS',
    'SEMOZHI': '635 - SHANMATHI CONSTRUCTIONS',
    'gas plant': '655 - RCH',
    'gas pt': '655 - RCH',
    'gm': '655 - RCH',
}


def load_registry():
    """Return (canonical_values set, stem_name->canonical map) from the registry.

    Uses the registry directly (not the cache) so the migration always works
    against the live table.
    """
    engine = create_engine(Config.PROJECTS_DB_URL, pool_pre_ping=True)
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id, stem_name FROM projects ORDER BY id")).fetchall()

    canonical_set = set()
    by_stem = {}
    for pid, stem in rows:
        value = canonical_value(pid, stem)
        canonical_set.add(value)
        # Case-insensitive, trimmed match on the bare stem name.
        by_stem.setdefault((stem or '').strip().lower(), value)
    return canonical_set, by_stem


def main():
    apply = '--apply' in sys.argv

    if not Config.PROJECTS_DB_URL:
        print("ERROR: PROJECTS_DB_* env vars are not configured.")
        return 1

    canonical_set, by_stem = load_registry()
    print(f"Registry: {len(canonical_set)} canonical projects loaded.\n")

    # Guard: every manual target must actually exist in the registry, otherwise
    # we'd write a value the dropdown can never reproduce.
    bad_targets = {t for t in MANUAL_MAP.values() if t not in canonical_set}
    if bad_targets:
        print("ERROR: these manual-map targets are not in the registry:")
        for t in sorted(bad_targets):
            print(f"  {t!r}")
        return 1

    with app.app_context():
        # Distinct current values + how many rows use each.
        rows = (
            db.session.query(Attendance.project, db.func.count(Attendance.id))
            .filter(Attendance.project.isnot(None))
            .filter(Attendance.project != '')
            .group_by(Attendance.project)
            .all()
        )

        already_ok = []     # (value, count)
        to_migrate = []     # (old_value, new_value, count)
        unmatched = []      # (value, count)

        for value, count in rows:
            if value in canonical_set:
                already_ok.append((value, count))
            elif value in MANUAL_MAP:
                to_migrate.append((value, MANUAL_MAP[value], count))
            elif value.strip().lower() in by_stem:
                to_migrate.append((value, by_stem[value.strip().lower()], count))
            else:
                unmatched.append((value, count))

        # --- Report ---
        print(f"Already canonical ({len(already_ok)}):")
        for v, c in sorted(already_ok):
            print(f"  OK    {v!r}  ({c} rows)")

        print(f"\nWill normalize ({len(to_migrate)}):")
        for old, new, c in sorted(to_migrate):
            print(f"  MAP   {old!r} -> {new!r}  ({c} rows)")

        print(f"\nUNMATCHED — map these by hand ({len(unmatched)}):")
        for v, c in sorted(unmatched):
            print(f"  ????  {v!r}  ({c} rows)")

        if not apply:
            print("\nDry run — no changes written. Re-run with --apply to commit the 'MAP' rows above.")
            return 0

        if not to_migrate:
            print("\nNothing to migrate.")
            return 0

        total = 0
        for old, new, _ in to_migrate:
            updated = (
                db.session.query(Attendance)
                .filter(Attendance.project == old)
                .update({Attendance.project: new}, synchronize_session=False)
            )
            total += updated
        db.session.commit()
        print(f"\nApplied: updated {total} attendance rows across {len(to_migrate)} project values.")
        if unmatched:
            print(f"{len(unmatched)} unmatched value(s) were left untouched (see list above).")
        return 0


if __name__ == '__main__':
    sys.exit(main())
