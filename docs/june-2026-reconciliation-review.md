# June 2026 Attendance Reconciliation — Review Journal

Date: 2026-07-04. Source of truth: `VISMA ATTANDANCE 2026-2027 (4).xlsx` (sheet `JUNE-26`),
cross-checked against the production DB (Railway `railway`).

---

## ✅ FINAL EXACT ALIGNMENT APPLIED — 2026-07-06
User confirmed the open items below and directed a **complete, exact** alignment of prod
June to the Excel `JUNE-26` sheet (not just the earlier raise-only pass). Applied to prod:

**Rule used (faithful reproduction):** for every worker×day, status `P` only where the
Excel status cell is a plain `P`; everything else (`AB`/`A`/`P/2`) → `A`. OT is copied
verbatim from the Excel OT-row for **every** day regardless of status — this reproduces the
Excel's daily-worker half-day trick (`AB`+OT4 = `rate/8×4` = ½ pay, e.g. VINAY 6/30,
BIKKI 6/25) and makes each worker's prod present-count = Excel `AH` and OT-total = Excel `AJ`
(hence recomputed salary = Excel `AO` for daily workers). Worker rates were **not** touched.

**17 attendance changes (14 workers):**
- 4 present→absent (Excel = absent): S.PRINCE 6/17, SHIVAKUMAR 6/23, DASHARATH 6/13 & 6/16 (§A resolved)
- 6 OT lowered on present days: GAURAV 6/30, HIMANSHU 6/3, R NITISH 6/1, SATHISH 6/8, VINAY 6/16 & 6/18 (§B resolved)
- 6 OT lowered on absent rows: BAJINATH/SHIVAKUMAR/ASHISH 6/18 (`P/2`→A+OT0, §C — Excel OT-row is 0), PRINCE 6/9, NITHISH LAUHAR 6/23, GIRIJESH 6/23
- 1 OT raised: ABHISHEK 6/15 1→8 (§D — **large but required** to hit Excel OT-total 65; 6/29 was already 8). ⚠️ If this 8 is truly an Excel typo, fix the Excel and re-run.

**PRASANTH (id34):** kept at 16 present (the daily grid); the Excel's own `AH` cell wrongly
says 15 (§ data-quality #2). Verified: prod now = Excel exactly (diff = 0 ops).
Salaries recomputed via the app's own `_recalculate_monthly_salaries`.

**Project mapping (reporting-only)** — filled 24 of the previously-blank present-days from
the already-marked June attendance (nearest-neighbour site + team-modal site that day); 10
genuine switch-days were initially left blank, then **carry-forward filled later the same day**
(see "Project backfill audit trail" at the bottom). Unassigned bucket for June: 34 → 10 → **0**.

Backup of all affected pre-change June rows: `backups/june_2026_final_align_backup.json`
(313 attendance + 14 salary rows). Reproduction scripts in the session scratchpad
(`common.py`/`match.py`/`diff.py`/`apply.py`/`project_infer.py`).

## Context
- **May 2026 reconciled to zero conflicts** — Excel and prod already matched exactly.
- **June 2026 prod was materially incomplete** (whole days of OT / present-marks never
  entered). The Excel is the more complete record for June.

## What was auto-aligned (prod → Excel, 164 changes across 40 workers)
Applied on 2026-07-04. Only cases where **prod was *missing* data vs the Excel** were touched:

| Action | Count | Rule |
|---|---|---|
| Inserted missing present-days | 64 | Excel = present, no prod row → insert `P` + Excel OT |
| Flipped `A` → `P` | 9 | Excel = present, prod row was `A` → set `P` + Excel OT |
| Raised OT | 91 | both present, `excel_ot > prod_ot` → set prod OT = Excel OT |

Salary rows for all 40 affected workers were recomputed via the app's own
`_recalculate_monthly_salaries` (same logic the UI uses).

**Backup of every affected worker's June rows (pre-change):**
`scratchpad/backup_june_before_apply.json` (in the session temp dir). Full deviation
list: `scratchpad/june_deviations.csv`.

Auto-align rules deliberately did **not** reduce any prod value or delete any prod
record — prod was only ever raised toward the Excel.

---

## Project backfill for reconciled days (2026-07-04)
The 64 inserted + 9 flipped June present-days had no `project` (the June sheet carries no
site info), so they surfaced in the dashboard's **"Unassigned"** bucket (72 rows / ₹69,916).
Assumption tested: "same workers stay on the same site." Verdict — **partly true**: reliable
in runs, but workers switch sites often (esp. whole-crew move days Jun 2 & 9), so a blanket
guess was rejected. Backfilled only **38 near-certain days** (same site before+after the gap,
worker only-ever-one-site, or a one-sided neighbour that was the team's *modal* site that day
with ≥2 corroborating teammates). Left **34 blank** (16 genuine switch-days + 18 weakly
supported). Reporting-only — **no pay changed**. Unassigned bucket now 34 rows / ₹30,989.
Backup: `scratchpad/backup_backfill_before.json`.

### Still Unassigned after backfill (34 days)
Left blank on purpose — site could not be inferred safely. Candidate site(s) shown for
manual filling if the real one is known. Reporting-only; no pay attached to the choice.

**Genuine switch-days (16)** — different site immediately before vs after; no safe pick:

| Worker (id) | Team | Date | Candidate sites |
|---|---|---|---|
| AMITH (7) | Rajeeb | Jun 2 | VETHA KUZHUMAM or JAMUNA |
| ASHISH (46) | Ambeth | Jun 9 | JAMUNA or POLSONS |
| BAJINATH KUMAR (45) | Ambeth | Jun 9 | TITAN PAINTS or POLSONS |
| GAURAV (24) | Rajeeb | Jun 2 | TITAN PAINTS or VISMA ENGINEERING |
| HIMANSHU GUPTA (14) | Rajeeb | Jun 2 | POLSONS or PROMINANCE |
| KRISHNAKUMAR (32) | Visma | Jun 17 | TITAN PAINTS or INFINIUM |
| KUNDHAN (26) | Rajeeb | Jun 13 | TITAN PAINTS or INFINIUM |
| KUNDHAN (26) | Rajeeb | Jun 14 | TITAN PAINTS or INFINIUM |
| LALMOHAN (27) | Rajeeb | Jun 2 | POLSONS or TITAN PAINTS |
| PRAHALAD MAHTO (50) | Ambeth | Jun 17 | TITAN PAINTS or JAMUNA |
| PRINCE KUMAR CHOUDHARY (35) | Rajeeb | Jun 2 | TITAN PAINTS or VETHA KUZHUMAM |
| SHIVAKUMAR (47) | Ambeth | Jun 9 | TITAN PAINTS or POLSONS |
| SURAJ (13) | Rajeeb | Jun 2 | POLSONS or TITAN PAINTS |
| SURAJ (13) | Rajeeb | Jun 13 | JAMUNA or TITAN PAINTS |
| SURENDHAR CHOUDRY (2) | Visma | Jun 17 | JAMUNA or TITAN PAINTS |
| VIKAS (62) | Visma | Jun 17 | JAMUNA or INFINIUM |

**One-sided / weak support (18)** — only one neighbour and teammates that day did not clearly back it:

| Worker (id) | Team | Date | Candidate site |
|---|---|---|---|
| ABHISHEK KUMAR (59) | Visma | Jun 5 | TITAN PAINTS (likely) |
| ABHISHEK KUMAR (59) | Visma | Jun 6 | TITAN PAINTS (likely) |
| ANKITH KUMAR (66) | Ambeth | Jun 20 | POLSONS (likely) |
| ASHISH (46) | Ambeth | Jun 1 | TITAN PAINTS (likely) |
| ASHISH (46) | Ambeth | Jun 25 | POLSONS (likely) |
| BAJINATH KUMAR (45) | Ambeth | Jun 1 | TITAN PAINTS (likely) |
| BAJINATH KUMAR (45) | Ambeth | Jun 29 | POLSONS (likely) |
| BIKKI KUMAR (65) | Ambeth | Jun 20 | POLSONS (likely) |
| GUDDU KUMAR (67) | Ambeth | Jun 20 | POLSONS (likely) |
| INDRADEV (40) | Ambeth | Jun 1 | TITAN PAINTS (likely) |
| KUNDAN GOUTAM (60) | Visma | Jun 5 | TITAN PAINTS (likely) |
| KUNDAN GOUTAM (60) | Visma | Jun 6 | TITAN PAINTS (likely) |
| NITHISH KUMAR LAUHAR (28) | Visma | Jun 1 | TITAN PAINTS (likely) |
| ROHIT KUMAR (68) | Ambeth | Jun 20 | POLSONS (likely) |
| SATHISH (29) | Visma | Jun 1 | JAMUNA (likely) |
| SATHISH (29) | Visma | Jun 2 | JAMUNA (likely) |
| SHIVAKUMAR (47) | Ambeth | Jun 29 | POLSONS (likely) |
| TRILOKI (54) | Ambeth | Jun 9 | TITAN PAINTS (likely) |

---

## OPEN — needs human review (12 day-level items, NOT changed)

### A. Prod says PRESENT but Excel says ABSENT (4) — who is right?
Prod has attendance (with a project) that the Excel doesn't show. Left as-is; confirm
whether the worker actually worked (pay stays) or the prod row is wrong (delete).

| Worker | Day | Prod | Project |
|---|---|---|---|
| S.PRINCE (id36) | Jun 17 | P, OT 3 | 662 – INFINIUM |
| SHIVAKUMAR (id47) | Jun 23 | P, OT 0 | 647 – POLSONS |
| DASHARATH KUSHWALA (id49) | Jun 13 | P, OT 0 | 665 – TITAN PAINTS |
| DASHARATH KUSHWALA (id49) | Jun 16 | P, OT 3 | 659 – JAMUNA |

### B. Prod OT HIGHER than Excel (4) — not raised (would have reduced pay)
Prod already has more OT than the Excel. Confirm which is correct.

| Worker | Day | Prod OT | Excel OT |
|---|---|---|---|
| GAURAV (id24) | Jun 30 | 3.0 | 0.0 |
| HIMANSHU GUPTA (id14) | Jun 3 | 2.5 | 2.0 |
| NITHISH CHOUDRY (id52) | Jun 1 | 3.0 | 2.0 |
| SATHISH (id29) | Jun 8 | 3.0 | 2.0 |
| VINAY (id58) | Jun 16 | 3.0 | 0.0 |
| VINAY (id58) | Jun 18 | 3.0 | 0.0 |

### C. Half-day (`P/2`) in Excel, prod = Absent (3) — RESOLVED 2026-07-04
Convention chosen: **half-day = status `A` + OT 4h** (matches the Excel's half-salary
math `rate/8 × 4 = ½ rate` for daily workers, and the existing VINAY Jun 30 precedent).
All three (BAJINATH id45, SHIVAKUMAR id47, ASHISH id46 — Jun 18) were **already stored
as `A` + OT4** in prod, so no attendance change was needed; salary recomputed to confirm.

NOTE: all three are `monthly_salaried`, and monthly-salaried OT is never paid, so their
half-day carries **₹0** in this system (base pay = present-days only). The Excel likewise
prices the Ambeth crew's days/OT elsewhere (monthly bill), showing ₹0 in the day sheet.
If a half-day should actually pay these workers ½ day, it must be handled in the monthly
reconciliation — this app has no fractional present-day for monthly-salaried workers.

### D. Suspect Excel OT value (1)
- **A BISHIEK KUMAR (id59) — Jun 15: Excel OT = 8** vs prod 1. 8h in a single day is a
  full extra shift — likely an Excel typo. Verify before applying. (Excluded from the
  auto OT-raise by the >6h/day guard.)

---

## OPEN — data-quality issues (worker master / Excel)

### 1. Duplicate worker: VINAY (Visma, Welder, ₹1000/day) — id57 + id58 — RESOLVED 2026-07-04
VINAY's attendance was **split across two duplicate worker rows** (no overlapping days).
Merged **id57 → id58** (kept id58; id57's 8 June + 1 July rows repointed, then id57's
salary rows and worker record deleted). Applied the Excel alignment that had been skipped:
inserted the two genuinely-missing days (Jun 5 OT3, Jun 6 OT5) and raised OT on Jun
13/17/20/28. Result: id58 June = **24 present-days** (matches Excel), OT 67, salary
₹32,375; July = 3 days. Backup: `scratchpad/backup_vinay_before.json`.
(Jun 16 & 18 kept prod OT 3 vs Excel 0 — see section B, prod-OT-higher review list.)

### 2. Excel internal inconsistency
- **PRASATH (id34)**: the June sheet's daily marks sum to **16** present days but its
  own "PRESENT" total cell says **15**. Confirm the correct count. (Prod now = 16 to
  match the daily marks.)

### 3. Team label mismatch
- **SURENDHAR CHOUDRY (id2)**: sits in the Rajeeb block on the sheet but is `Visma` in
  the worker master. Cosmetic (doesn't affect attendance), but worth aligning.

---

## Name-map note (Excel → prod worker id)
Subtle typos reconciled during matching (kept for audit): `PRASATH`→PRASANTH,
`KUNTHAN`→KUNDHAN, `A BISHIEK KUMAR`→ABHISHEK KUMAR, `HARINDHAR`→HARINDHER,
`KAUSHLENDAR`→KAUSHLENDER, `AMIT`→AMITH, `KUNDAN GOUTHAM`→KUNDAN GOUTAM,
`NITHISH KUMAR CHOUDRY`/`NITHISH CHOUDRY`→R NITISH CHOUDHARY, `NITHISH (F)`→NITHISH KUMAR.

---

## Project backfill audit trail — 2026-07-06 (reporting-only, no pay changed)
Filled the dashboard "Unassigned" bucket (present-days with no `project`). Rule:
**CERTAIN** = worker at the identical site the day before AND after (sandwich), or only
one neighbour existed; **GUESS (carry-forward)** = a crew-move/switch-day (different site
before vs after) filled with the worker's most-recent prior site. `project` never affects
pay. Bucket went **427 → 362** (only April remains — a whole-month gap with no anchor data,
left untouched by request).

| Month | Filled | Certain | Guess (carry-fwd) | Remaining |
|---|---|---|---|---|
| Jun | 34 | 24 (neighbour+team-modal) | 10 | 0 |
| May | 38 | 26 | 12 | 0 |
| Jan–Mar | 17 | 9 | 8 | 0 |
| Apr | 0 | — | — | 362 (left) |

### GUESS days (carry-forward — verify if a real site is known)
**June (10):** SURAJ 6/2 → 647 POLSONS · LALMOHAN 6/2 → 647 POLSONS · HIMANSHU GUPTA 6/2 →
647 POLSONS · GAURAV 6/2 → 665 TITAN PAINTS · SURAJ 6/13 → 659 JAMUNA · KUNDHAN 6/13 → 665
TITAN PAINTS · KRISHNAKUMAR 6/17 → 665 TITAN PAINTS · PRAHALAD MAHTO 6/17 → 665 TITAN PAINTS ·
BAJINATH KUMAR 6/9 → 665 TITAN PAINTS · SHIVAKUMAR 6/9 → 665 TITAN PAINTS.

**May (12):** GANDHI 5/2 → PRAKASH SITE · PRINCE KUMAR CHOUDHARY 5/20 → 664 VETHA KUZHUMAM ·
SURAJ 5/23 → 665 TITAN PAINTS · DEVENDRA SHA 5/23 → FACTORY · DEVENDRA SHA 5/31 → 665 TITAN
PAINTS · TRILOKI 5/31 → 651 PROMINANCE · INDRADEV 5/31 → 651 PROMINANCE · DASHARATH KUSHWALA
5/31 → 651 PROMINANCE · GAURAV 5/31 → 3 VISMA ENGINEERING · NITHISH KUMAR LAUHAR 5/31 → 3
VISMA ENGINEERING · R NITISH CHOUDHARY 5/31 → 659 JAMUNA · **SATHISH 5/31 → 659 JAMUNA**
(overrode the prior day's `CNC PLATE SUTTING` work-label with the next-day site).

**Jan–Mar (8):** SURAJ RAM 1/21 → 647 POLSONS · SURAJ 1/21 → 647 POLSONS · SURENDHAR CHOUDRY
1/21 → 647 POLSONS · HIMANSHU GUPTA 1/31 → 655 RCH · GAURAV 3/12 → 660 SUN
ASSOCIATES/PRAKALATHAN · RAJEEV KUMAR 3/19 → FACTORY · SURENDHAR CHOUDRY 3/19 → 658 MARVEL ·
SURAJ RAM 3/19 → 658 MARVEL.

**Note:** some carried-forward values are legacy/non-canonical site labels that already
existed in the data (`FACTORY`, `PRAKASH SITE`, `655 – RCH`) — propagated as-is, worth
normalising separately. The CERTAIN fills (59 days) are high-confidence and not listed
individually.
