"""Canonical team rosters + the name-matching used to backfill `worker.team`.

This lives in its own module (not models.py, not app.py) so BOTH the startup
seeder (`app.seed_teams`) and the one-off CLI backfill (`migrate_teams.py`) can
share a single source of the roster and the matching logic without a circular
import (migrate_teams imports `app`, and app imports this).

Matching is exact on a normalised name (trimmed, upper-cased, inner whitespace
collapsed; designation suffixes like "(F)"/"(W)"/"(H)"/"(RGR)" are already
stripped from the roster below). Exact match is deliberate so "NITHISH KUMAR"
(Rajeeb) never collides with "NITHISH KUMAR LAUHAR" (Visma).
"""
from models import TEAMS

# Team rosters from the May-2026 attendance image
# (WhatsApp Image 2026-06-29 at 17.07.50.jpeg), designation suffixes stripped.
# Edit here to fix any spelling the backfill reports as unmatched.
ROSTER = {
    'Rajeeb': [
        'RAVI', 'SURAJ', 'NITHISH KUMAR', 'GANDHI', 'GAURAV', 'S PRINCE',
        'PRINCE KUMAR CHOUDHARY', 'HIMANSHU GUPTA', 'PRASATH', 'KUNTHAN',
        'LALMOHAN', 'AMIT', 'R NITHISH CHOUDHARY',
    ],
    'Visma': [
        'KRISHNA KUMAR', 'NITHISH KUMAR LAUHAR',
    ],
    'Ambeth': [
        'SONU', 'PROMOD', 'BAJINATH KUMAR', 'DEVENDRA SHA', 'SHIVAKUMAR',
        'DURGESH KUSHWALA', 'DASHARATH KUSHWALA', 'AKILESH YADAV', 'INDRADEV',
        'PRAHALAD MAHTO', 'TRILOKI', 'GIRIJESH KUSHWALA', 'ASHISH', 'JANUDEEN',
        'HARINDHAR CHOUDRY', 'KAUSHLENDAR',
    ],
}


def norm(name):
    """Trim, upper-case and collapse inner whitespace for exact matching."""
    return ' '.join((name or '').strip().upper().split())


def name_to_team():
    """Return {normalised name -> team} for exact lookups."""
    mapping = {}
    for team, names in ROSTER.items():
        for n in names:
            mapping[norm(n)] = team
    return mapping


# Sanity: keep the roster teams in lock-step with the canonical team list.
for _team in ROSTER:
    if _team not in TEAMS:  # pragma: no cover - guards a typo, not runtime logic
        raise ValueError(f"Roster team {_team!r} is not in models.TEAMS {TEAMS}")
