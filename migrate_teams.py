"""One-time backfill of `worker.team` from the May-2026 attendance sheet.

Background
----------
Workers belong to one of three teams — Rajeeb, Visma, Ambeth. The team is a new
label column on the `worker` master (added idempotently by app.run_migrations).
This script populates that column for existing workers using the team rosters in
the WhatsApp attendance image (WhatsApp Image 2026-06-29 at 17.07.50.jpeg).

The roster and matching live in `team_roster.py` (shared with the startup
seeder `app.seed_teams`); edit the names there if the dry run flags a mismatch.

How it matches
--------------
Each roster name is matched EXACTLY against the normalised `worker.name`. Exact
match is deliberate so "NITHISH KUMAR" (Rajeeb) never collides with "NITHISH
KUMAR LAUHAR" (Visma).

The dry run reports, per team, which roster names matched which worker rows and
which roster names found NO worker, plus every DB worker still left without a
team — so the owner can reconcile spellings before committing. Unlike the startup
seeder (which only fills teams still unset), this CLI OVERWRITES the team of any
matched worker, so it's the tool to use when correcting an earlier assignment.

Usage
-----
    venv\\Scripts\\python.exe migrate_teams.py            # dry run (no writes)
    venv\\Scripts\\python.exe migrate_teams.py --apply    # commit changes

NOTE: run against the PRODUCTION database (the local DB may be empty). Point
DATABASE_URL at prod for this one-time backfill.
"""
import sys

from app import app
from models import db, Worker
from team_roster import ROSTER, norm as _norm


def run(apply):
    with app.app_context():
        # (Roster teams are validated against models.TEAMS at import in team_roster.)
        workers = Worker.query.all()
        by_name = {}
        for w in workers:
            by_name.setdefault(_norm(w.name), []).append(w)

        print("=== Team backfill (dry run) ===" if not apply
              else "=== Team backfill (APPLY) ===")
        print(f"  workers in DB: {len(workers)}")

        assigned_ids = set()
        unmatched = {}  # team -> [roster names with no worker]
        ambiguous = []  # (name, team, count) where a name hit multiple workers

        for team, names in ROSTER.items():
            matched = []
            misses = []
            for raw in names:
                key = _norm(raw)
                rows = by_name.get(key, [])
                if not rows:
                    misses.append(raw)
                    continue
                if len(rows) > 1:
                    ambiguous.append((raw, team, len(rows)))
                for w in rows:
                    matched.append(w)
                    assigned_ids.add(w.id)
                    if apply:
                        w.team = team

            print(f"\n  {team}: {len(matched)} matched / {len(names)} roster names")
            for w in sorted(matched, key=lambda x: x.name):
                print(f"    + {w.id:>3}  {w.name}")
            if misses:
                unmatched[team] = misses
                print(f"    unmatched roster names ({len(misses)}): {misses}")

        if ambiguous:
            print("\n  AMBIGUOUS (name matched multiple workers — all were set):")
            for raw, team, n in ambiguous:
                print(f"    ! {raw!r} -> {team} ({n} workers)")

        # DB workers left without a team after this mapping.
        leftover = [w for w in workers if w.id not in assigned_ids]
        print(f"\n  DB workers still without a team: {len(leftover)}")
        for w in sorted(leftover, key=lambda x: x.name):
            current = f" (currently {w.team!r})" if w.team else ""
            print(f"    ? {w.id:>3}  {w.name}{current}")

        if apply:
            db.session.commit()
            print(f"\n  -> committed team for {len(assigned_ids)} worker(s).")
        else:
            print("\n(dry run — no changes written. Re-run with --apply to commit.)")


if __name__ == '__main__':
    run(apply='--apply' in sys.argv)
