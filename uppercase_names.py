"""
One-time migration: upper-case every existing worker and salary name.

Going forward, names are normalized to UPPERCASE at the model layer (see
models._normalize_name + the @validates hooks), so this script only needs to
fix rows written before that change.

Usage:
    python uppercase_names.py
"""

from app import create_app
from models import db, Worker, Salary


def main():
    app = create_app()
    with app.app_context():
        changed = 0
        for model in (Worker, Salary):
            for row in model.query.all():
                upper = (row.name or '').strip().upper()
                if row.name != upper:
                    row.name = upper
                    changed += 1
        db.session.commit()
        print(f"Upper-cased {changed} name(s) across worker + salary tables.")


if __name__ == '__main__':
    main()
