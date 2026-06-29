# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Factory worker attendance and salary management system built with Flask. Supervisors use it to mark daily attendance, track overtime, and calculate wages.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application (starts on port 5000)
python app.py

# Import data from Excel files
python import_data.py

# Show database summary
python import_data.py --summary
```

## Architecture

**Pattern**: MVC with Flask Blueprints

- `app.py` - Application factory (`create_app()`) and page route registration
- `config.py` - Environment-based configuration (development/production)
- `models.py` - SQLAlchemy ORM models
- `routes/` - API Blueprint modules (attendance.py, salary.py)
- `templates/` - Jinja2 HTML templates with base.html inheritance
- `static/js/` - Vanilla JavaScript for client-side logic

**Database Schema** (MySQL):
- **Salary**: id (PK), worker_id, name, designation, base_salary_per_day, year, month, total_working_days, ot_hours, total_salary
  - One row per worker per month
  - Unique constraint on (worker_id, year, month)
  - Auto-created/updated when attendance is marked
- **Attendance**: id (PK), worker_id, date, status (P/A/H), ot_hours, project
  - Unique constraint on (worker_id, date)

**Key Data Flows**:
1. Attendance updates trigger salary recalculation
2. Upsert pattern for attendance records (insert-or-update on unique constraint)
3. Worker lists are flat (alphabetical by name). Each worker carries a `team`
   label (one of `models.TEAMS`: Rajeeb/Visma/Ambeth) on the worker master.
   Team is NOT snapshotted onto salary rows — summary/salary slice by team via a
   live join from attendance back to the worker master (same as project pricing).

## API Endpoints

**Attendance** (`/api/`):
- `GET /labours` - List all workers
- `GET /labours/<id>/history` - Worker attendance history (month-wise)
- `GET /attendance/date/<date>` - All attendance for a date
- `POST /attendance` - Mark attendance (single or bulk)
- `POST /labours` - Add new worker (base_salary, team optional)
- `GET /projects` - List unique projects
- `GET /teams` - List selectable teams (models.TEAMS + any ad-hoc values)

**Salary** (`/api/`):
- `GET /salary` - All salaries with totals
- `GET /salary/monthly` - Monthly breakdown for all workers
- `GET /salary/<id>` - Single worker salary
- `PUT /salary/<id>` - Update salary info (triggers recalculation)
