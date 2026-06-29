from flask import Blueprint, request, jsonify
from models import db, Attendance, Salary, Supervisor, Worker, compute_pay, TEAMS
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import func, case
from services.projects_registry import get_projects, ProjectsRegistryError

attendance_bp = Blueprint('attendance', __name__)

# Attendance is always reckoned in IST regardless of where the app is hosted
# (Railway containers run in UTC, which is ~5.5h behind and would roll the date
# over early). "Today" must mean today in India.
IST = ZoneInfo('Asia/Kolkata')


def ist_now():
    """Current datetime in IST."""
    return datetime.now(IST)


def _worker_info_map(worker_ids):
    """Return {worker_id: Worker} for the given worker ids.

    Worker is the single source of truth for identity (name/designation/rate);
    callers use .name/.designation/.base_salary_per_day off the returned rows.
    """
    if not worker_ids:
        return {}
    workers = Worker.query.filter(Worker.id.in_(worker_ids)).all()
    return {w.id: w for w in workers}


# Attendance is normally marked on the day itself, but supervisors only learn
# the previous day's overtime the next morning. A one-day buffer lets them mark
# (or edit) today and yesterday; anything older stays locked.
MARKING_BUFFER_DAYS = 1


def _is_within_marking_window(date_str):
    """True if date_str (YYYY-MM-DD) is today or within the buffer (yesterday)."""
    try:
        d = datetime.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return False
    today = ist_now().date()
    return today - timedelta(days=MARKING_BUFFER_DAYS) <= d <= today


@attendance_bp.route('/api/supervisors', methods=['GET'])
def get_supervisors():
    """List all supervisors."""
    supervisors = Supervisor.query.order_by(Supervisor.name).all()
    return jsonify([s.to_dict() for s in supervisors])


@attendance_bp.route('/api/supervisors', methods=['POST'])
def add_supervisor():
    """Add a new supervisor."""
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()

    if not name:
        return jsonify({'error': 'name is required'}), 400

    existing = Supervisor.query.filter(func.lower(Supervisor.name) == name.lower()).first()
    if existing:
        return jsonify({'error': 'Supervisor already exists', 'supervisor': existing.to_dict()}), 409

    supervisor = Supervisor(name=name)
    db.session.add(supervisor)
    db.session.commit()
    return jsonify(supervisor.to_dict()), 201


@attendance_bp.route('/api/teams', methods=['GET'])
def get_teams():
    """List selectable teams.

    The canonical TEAMS come first; any ad-hoc team value already on a worker but
    not in that list is appended, so a team added directly in the DB still shows
    up in the dropdowns/filters rather than silently disappearing.
    """
    extra = db.session.query(Worker.team).distinct().filter(
        Worker.team.isnot(None), Worker.team != ''
    ).all()
    teams = list(TEAMS)
    for (t,) in extra:
        if t not in teams:
            teams.append(t)
    return jsonify(teams)


@attendance_bp.route('/api/attendance/day-roster/<date_str>', methods=['GET'])
def get_day_roster(date_str):
    """Roster for the Mark Attendance flow.

    Returns the workers a given supervisor has already marked on this date,
    plus every worker_id marked by anyone (so the UI can hide them from the
    "add worker" dropdown and prevent double-assignment).
    """
    try:
        roster_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    supervisor_id = request.args.get('supervisor_id', type=int)

    records = Attendance.query.filter_by(date=roster_date).all()
    marked_worker_ids = [r.worker_id for r in records]

    marked_by_supervisor = []
    if supervisor_id is not None:
        sup_records = [r for r in records if r.supervisor_id == supervisor_id]
        info = _worker_info_map([r.worker_id for r in sup_records])
        for r in sup_records:
            w = info.get(r.worker_id)
            marked_by_supervisor.append({
                'worker_id': r.worker_id,
                'name': w.name if w else f'Worker {r.worker_id}',
                'role': r.role or '',
                'work': r.work or '',
                'status': r.status,
                'ot_hours': float(r.ot_hours) if r.ot_hours else 0,
                'project': r.project or ''
            })
        marked_by_supervisor.sort(key=lambda x: x['name'])

    return jsonify({
        'date': date_str,
        'marked_worker_ids': marked_worker_ids,
        'marked_by_supervisor': marked_by_supervisor
    })


@attendance_bp.route('/api/labours', methods=['GET'])
def get_labours():
    """Get list of all workers (from the Worker master, alphabetical)."""
    workers = Worker.query.filter_by(active=True).order_by(Worker.name).all()

    result = []
    for w in workers:
        last_att = Attendance.query.filter_by(worker_id=w.id).order_by(Attendance.date.desc()).first()
        result.append({
            'worker_id': w.id,
            'name': w.name,
            'designation': w.designation,
            'team': w.team,
            'base_salary_per_day': float(w.base_salary_per_day) if w.base_salary_per_day else 0,
            'monthly_salaried': bool(w.monthly_salaried),
            'last_attendance': last_att.date.isoformat() if last_att else None
        })

    return jsonify(result)


@attendance_bp.route('/api/labours/<int:worker_id>/history', methods=['GET'])
def get_labour_history(worker_id):
    """Get complete attendance history for a worker."""
    worker = Worker.query.get_or_404(worker_id)

    records = Attendance.query.filter_by(worker_id=worker_id).order_by(Attendance.date.desc()).all()

    return jsonify({
        'worker_id': worker.id,
        'name': worker.name,
        'designation': worker.designation,
        'base_salary_per_day': float(worker.base_salary_per_day) if worker.base_salary_per_day else 0,
        'attendance': [r.to_dict() for r in records],
        'total_records': len(records)
    })


@attendance_bp.route('/api/attendance/date/<date_str>', methods=['GET'])
def get_attendance_by_date(date_str):
    """Get all workers' attendance for a specific date."""
    try:
        filter_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    # Get all workers from the master table (alphabetical)
    workers = Worker.query.filter_by(active=True).order_by(Worker.name).all()

    # Get attendance for the date
    attendance_map = {
        a.worker_id: a for a in Attendance.query.filter_by(date=filter_date).all()
    }

    result = []
    for w in workers:
        att = attendance_map.get(w.id)
        result.append({
            'worker_id': w.id,
            'name': w.name,
            'designation': w.designation,
            'team': w.team,
            'base_salary_per_day': float(w.base_salary_per_day) if w.base_salary_per_day else 0,
            'attendance': att.to_dict() if att else {
                'id': None,
                'worker_id': w.id,
                'date': date_str,
                'status': 'A',
                'ot_hours': 0,
                'project': None
            }
        })

    return jsonify(result)


@attendance_bp.route('/api/attendance', methods=['POST'])
def mark_attendance():
    """Mark or update attendance (supports bulk).

    Enforces that attendance can only be created or edited for today or
    yesterday (a one-day buffer for late-reported overtime), so older
    records can never be modified after the fact.
    """
    data = request.get_json()

    # Guard: every record must fall within the marking window (today/yesterday)
    # and a present worker must be assigned to a project (so labor cost can be
    # attributed). Absent workers don't require a project.
    records_to_check = data if isinstance(data, list) else [data]
    for rec in records_to_check:
        if not isinstance(rec, dict) or not _is_within_marking_window(rec.get('date')):
            return jsonify({
                'error': 'Attendance can only be marked or edited for today or yesterday.'
            }), 403
        if rec.get('status') == 'P' and not str(rec.get('project') or '').strip():
            return jsonify({
                'error': 'A project is required when marking a worker present.'
            }), 400

    if isinstance(data, list):
        results = []
        affected = set()  # (worker_id, year, month)
        for record in data:
            result = _upsert_attendance(record)
            results.append(result)
            if 'worker_id' in record and 'date' in record:
                try:
                    d = datetime.strptime(record['date'], '%Y-%m-%d').date()
                    affected.add((record['worker_id'], d.year, d.month))
                except:
                    pass
        db.session.commit()
        _recalculate_monthly_salaries(affected)
        return jsonify(results), 201

    result = _upsert_attendance(data)
    db.session.commit()
    if 'worker_id' in data and 'date' in data:
        try:
            d = datetime.strptime(data['date'], '%Y-%m-%d').date()
            _recalculate_monthly_salaries({(data['worker_id'], d.year, d.month)})
        except:
            pass
    return jsonify(result), 201


@attendance_bp.route('/api/attendance/<int:worker_id>/<date_str>', methods=['DELETE'])
def delete_attendance(worker_id, date_str):
    """Remove a worker's attendance for a date (today or yesterday only)."""
    try:
        record_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    if not _is_within_marking_window(date_str):
        return jsonify({'error': 'Attendance can only be edited for today or yesterday.'}), 403

    record = Attendance.query.filter_by(worker_id=worker_id, date=record_date).first()
    if not record:
        return jsonify({'error': 'Record not found'}), 404

    db.session.delete(record)
    db.session.commit()
    _recalculate_monthly_salaries({(worker_id, record_date.year, record_date.month)})

    return jsonify({'message': 'Attendance removed', 'worker_id': worker_id, 'date': date_str})


def _upsert_attendance(data):
    """Insert or update a single attendance record."""
    worker_id = data.get('worker_id')
    date_str = data.get('date')

    if not worker_id or not date_str:
        return {'error': 'worker_id and date are required'}

    try:
        record_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return {'error': 'Invalid date format'}

    attendance = Attendance.query.filter_by(worker_id=worker_id, date=record_date).first()

    if attendance:
        if 'status' in data:
            attendance.status = data['status']
        if 'ot_hours' in data:
            attendance.ot_hours = data['ot_hours']
        if 'project' in data:
            attendance.project = data['project']
        if 'supervisor_id' in data:
            attendance.supervisor_id = data['supervisor_id']
        if 'role' in data:
            attendance.role = data['role']
        if 'work' in data:
            attendance.work = data['work']
    else:
        attendance = Attendance(
            worker_id=worker_id,
            date=record_date,
            status=data.get('status', 'A'),
            ot_hours=data.get('ot_hours', 0),
            project=data.get('project'),
            supervisor_id=data.get('supervisor_id'),
            role=data.get('role'),
            work=data.get('work')
        )
        db.session.add(attendance)

    db.session.flush()
    return attendance.to_dict()


def _recalculate_monthly_salaries(affected_periods):
    """Recalculate salary for affected (worker_id, year, month) combinations."""
    for worker_id, year, month in affected_periods:
        # Identity (name/designation/current rate) comes from the Worker master.
        worker_info = Worker.query.get(worker_id)

        if not worker_info:
            continue

        # Calculate monthly stats from attendance
        stats = db.session.query(
            func.sum(case((Attendance.status == 'P', 1), else_=0)).label('working_days'),
            func.coalesce(func.sum(Attendance.ot_hours), 0).label('total_ot')
        ).filter(
            Attendance.worker_id == worker_id,
            func.extract('year', Attendance.date) == year,
            func.extract('month', Attendance.date) == month
        ).first()

        working_days = int(stats.working_days or 0)
        ot_hours = float(stats.total_ot or 0)

        # Calculate salary. Monthly-salaried workers are paid base x days only;
        # their OT hours are still stored on the salary row for the record but
        # are not paid (compute_pay enforces this).
        _, _, total = compute_pay(
            worker_info.base_salary_per_day, working_days, ot_hours,
            monthly_salaried=worker_info.monthly_salaried
        )

        # Upsert salary record for this month
        salary = Salary.query.filter_by(worker_id=worker_id, year=year, month=month).first()

        if salary:
            salary.total_working_days = working_days
            salary.ot_hours = ot_hours
            salary.monthly_salaried = bool(worker_info.monthly_salaried)
            # Keep the snapshot's rate in lock-step with the total we recompute
            # from it. Without this the rate column goes stale (a row created
            # before the worker's rate was set keeps base 0 even as its total is
            # recomputed correctly), which made the report price days at 0.
            salary.base_salary_per_day = worker_info.base_salary_per_day
            salary.total_salary = total
        else:
            salary = Salary(
                worker_id=worker_id,
                name=worker_info.name,
                designation=worker_info.designation,
                base_salary_per_day=worker_info.base_salary_per_day,
                monthly_salaried=bool(worker_info.monthly_salaried),
                year=year,
                month=month,
                total_working_days=working_days,
                ot_hours=ot_hours,
                total_salary=total
            )
            db.session.add(salary)

    db.session.commit()


@attendance_bp.route('/api/labours', methods=['POST'])
def add_labour():
    """Add a new worker.

    Creates the Worker master row — its id is a real auto-increment PK, so the
    old race-prone max(worker_id)+1 is gone. A zeroed salary row for the current
    month is also seeded so the worker shows up immediately in the monthly
    salary view, exactly as before.
    """
    data = request.get_json()

    name = data.get('name')
    base_salary = data.get('base_salary_per_day', 0)
    designation = data.get('designation')
    team = data.get('team')

    if not name:
        return jsonify({'error': 'name is required'}), 400

    worker = Worker(
        name=name,
        designation=designation,
        team=team,
        base_salary_per_day=base_salary,
        active=True,
    )
    db.session.add(worker)
    db.session.flush()  # assign worker.id before the salary row references it

    now = ist_now()
    salary = Salary(
        worker_id=worker.id,
        name=name,
        designation=designation,
        base_salary_per_day=base_salary,
        monthly_salaried=bool(worker.monthly_salaried),
        year=now.year,
        month=now.month,
        total_working_days=0,
        ot_hours=0,
        total_salary=0
    )
    db.session.add(salary)
    db.session.commit()

    return jsonify(worker.to_dict()), 201


@attendance_bp.route('/api/projects', methods=['GET'])
def get_distinct_projects():
    """Get list of unique project values already recorded in attendance.

    Used by the Summary tab as a historical filter (it should only list
    projects that actually have data). The Mark flow uses the live registry
    endpoint below instead.
    """
    projects = db.session.query(Attendance.project).distinct().filter(Attendance.project.isnot(None)).all()
    return jsonify([p[0] for p in projects if p[0]])


@attendance_bp.route('/api/projects/registry', methods=['GET'])
def get_projects_registry():
    """Live list of selectable projects from the shared VISMA registry.

    Returns {"projects": [{"id", "value"}...], "stale": bool}. `stale` is true
    when the registry DB was unreachable and we served the last cached list.
    If the DB is unreachable and nothing is cached, returns 503 with an error
    so the UI can show a clear message — it never falls back to free text.
    """
    try:
        result = get_projects()
    except ProjectsRegistryError as exc:
        return jsonify({
            'projects': [],
            'stale': True,
            'error': 'Projects registry is unavailable. Please try again shortly.',
            'detail': str(exc),
        }), 503
    return jsonify(result)


@attendance_bp.route('/api/attendance/summary', methods=['GET'])
def get_attendance_summary():
    """Get aggregated attendance summary with filters."""
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    project_filter = request.args.get('project')
    worker_id_filter = request.args.get('worker_id')
    team_filter = request.args.get('team')
    supervisor_id_filter = request.args.get('supervisor_id')

    if not start_date_str or not end_date_str:
        return jsonify({'error': 'start_date and end_date are required'}), 400

    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    # Base query for attendance in date range
    base_query = Attendance.query.filter(
        Attendance.date >= start_date,
        Attendance.date <= end_date
    )

    if project_filter:
        base_query = base_query.filter(Attendance.project == project_filter)
    if worker_id_filter:
        base_query = base_query.filter(Attendance.worker_id == int(worker_id_filter))
    if supervisor_id_filter:
        base_query = base_query.filter(Attendance.supervisor_id == int(supervisor_id_filter))
    # Team lives on the worker master, so scope by the worker ids in that team.
    if team_filter:
        team_worker_ids = [w.id for w in Worker.query.filter_by(team=team_filter).all()]
        base_query = base_query.filter(Attendance.worker_id.in_(team_worker_ids or [-1]))

    records = base_query.all()

    # Get worker info map
    worker_ids = list(set(r.worker_id for r in records))
    worker_info_map = {}
    if worker_ids:
        # Identity (name/designation/rate) comes from the Worker master.
        for w in Worker.query.filter(Worker.id.in_(worker_ids)).all():
            worker_info_map[w.id] = {
                'name': w.name,
                'designation': w.designation,
                'team': w.team,
                'base_salary_per_day': float(w.base_salary_per_day) if w.base_salary_per_day else 0,
                'monthly_salaried': bool(w.monthly_salaried)
            }

    # Supervisor id -> name, for the supervisor grouping. Whoever marked a
    # worker-day is its supervisor for breakdown purposes.
    supervisor_name_map = {s.id: s.name for s in Supervisor.query.all()}

    # Per-month rate: the base pay/day that applied in each month is stored on
    # that month's salary row, so a worker raised mid-life keeps the old rate on
    # earlier months. Keyed by (worker_id, year, month) -> (base, monthly).
    month_rate = {}
    if worker_ids:
        for s in Salary.query.filter(Salary.worker_id.in_(worker_ids)).all():
            base = float(s.base_salary_per_day) if s.base_salary_per_day else 0
            month_rate[(s.worker_id, s.year, s.month)] = (base, bool(s.monthly_salaried))

    def day_pay_for(record, ot_hours):
        """(rate, ot_pay) for one present day, using that month's stored rate.

        Look up the base pay/day saved for the record's own month and use it, so a
        worker raised mid-life keeps the old rate on earlier months. If a month's
        stored rate is missing/0, fall back to the worker's current master rate.
        OT is paid at the hourly rate (day rate / 8) for daily-rate workers only.
        This keeps the dashboard identical to the exported report.
        """
        winfo = worker_info_map.get(record.worker_id, {})
        master_rate = winfo.get('base_salary_per_day', 0)
        key = (record.worker_id, record.date.year, record.date.month)
        if key in month_rate:
            rate, monthly = month_rate[key]
            if rate <= 0:
                rate = master_rate
        else:
            rate = master_rate
            monthly = winfo.get('monthly_salaried', False)
        paid_ot = rate > 0 and not monthly
        ot_pay = (rate / 8) * ot_hours if paid_ot else 0
        return rate, ot_pay

    # Group aggregations. Each maps a group key -> stats including a `members`
    # dict (worker_id -> {present_days, ot_hours}) for the drill-down. Three
    # groupings are produced from the same records: project, team and supervisor.
    project_data = {}
    team_data = {}
    supervisor_data = {}

    def _add_group(group, key, r, ot, rate, ot_pay):
        g = group.get(key)
        if g is None:
            g = group[key] = {'worker_ids': set(), 'present_dates': set(),
                              'ot_hours': 0.0, 'labor_cost': 0.0, 'members': {}}
        g['worker_ids'].add(r.worker_id)
        g['present_dates'].add(r.date)
        g['ot_hours'] += ot
        g['labor_cost'] += rate + ot_pay
        m = g['members'].get(r.worker_id)
        if m is None:
            m = g['members'][r.worker_id] = {'present_days': 0, 'ot_hours': 0.0}
        m['present_days'] += 1
        m['ot_hours'] += ot

    # Aggregate by date
    daily_data = {}
    # Aggregate by worker
    worker_data = {}
    # Track present workers (for KPI)
    present_workers = set()
    # Activity breakdown: present worker-days per work type
    activity = {}

    total_present_days = 0
    total_ot_hours = 0.0

    for r in records:
        ot = float(r.ot_hours) if r.ot_hours else 0
        proj = r.project or 'Unassigned'
        date_str = r.date.isoformat()

        # Price this record live from the worker's Base Pay/Day. base rate is
        # earned on present days; ot_pay applies to any day that logged overtime
        # (daily-rate workers only).
        rate, ot_pay = day_pay_for(r, ot)

        # Group aggregations (project / team / supervisor) — present days only.
        # Labor cost per present-day is the day-rate plus overtime, priced
        # exactly as the salary report does.
        if r.status == 'P':
            winfo = worker_info_map.get(r.worker_id, {})
            team_key = winfo.get('team') or 'No team'
            sup_key = supervisor_name_map.get(r.supervisor_id) or 'Unassigned'
            _add_group(project_data, proj, r, ot, rate, ot_pay)
            _add_group(team_data, team_key, r, ot, rate, ot_pay)
            _add_group(supervisor_data, sup_key, r, ot, rate, ot_pay)
            # Track this worker as present
            present_workers.add(r.worker_id)

        # Daily aggregation
        if date_str not in daily_data:
            daily_data[date_str] = {'present': 0, 'absent': 0, 'holiday': 0, 'ot_hours': 0}
        if r.status == 'P':
            daily_data[date_str]['present'] += 1
            total_present_days += 1
        elif r.status == 'A':
            daily_data[date_str]['absent'] += 1
        elif r.status == 'H':
            daily_data[date_str]['holiday'] += 1
        daily_data[date_str]['ot_hours'] += ot
        total_ot_hours += ot

        # Worker aggregation
        if r.worker_id not in worker_data:
            info = worker_info_map.get(r.worker_id, {})
            worker_data[r.worker_id] = {
                'worker_id': r.worker_id,
                'name': info.get('name', f'Worker {r.worker_id}'),
                'designation': info.get('designation'),
                'team': info.get('team'),
                'present_days': 0,
                'absent_days': 0,
                'ot_hours': 0,
                'salary': 0.0,
                'projects': set(),
                'roles': set(),
                'works': set(),
                'supervisors': set()
            }
        if r.status == 'P':
            worker_data[r.worker_id]['present_days'] += 1
            worker_data[r.worker_id]['salary'] += rate  # base earned this present day
        elif r.status == 'A':
            worker_data[r.worker_id]['absent_days'] += 1
        worker_data[r.worker_id]['ot_hours'] += ot
        # OT pay accrues wherever OT was logged (daily-rate workers only).
        worker_data[r.worker_id]['salary'] += ot_pay
        if r.project:
            worker_data[r.worker_id]['projects'].add(r.project)
        if r.role:
            worker_data[r.worker_id]['roles'].add(r.role)
        if r.work:
            worker_data[r.worker_id]['works'].add(r.work)
        sup_name = supervisor_name_map.get(r.supervisor_id)
        if sup_name:
            worker_data[r.worker_id]['supervisors'].add(sup_name)

        # Activity breakdown counts worker-days of work actually done (present).
        if r.status == 'P' and r.work:
            activity[r.work] = activity.get(r.work, 0) + 1

    # Build response. Each grouping (project/team/supervisor) is shaped the same
    # so the front-end can switch between them and drill into a group's members
    # (the present labours, each with their designation — for the team view this
    # answers "who in this team was present, and in what role").
    def _build_breakdown(group_data):
        out = []
        for key, data in sorted(group_data.items()):
            members = []
            for wid, m in data['members'].items():
                info = worker_info_map.get(wid, {})
                members.append({
                    'worker_id': wid,
                    'name': info.get('name', f'Worker {wid}'),
                    'designation': info.get('designation'),
                    'present_days': m['present_days'],
                    'ot_hours': round(m['ot_hours'], 2),
                })
            members.sort(key=lambda x: x['name'])
            out.append({
                'name': key,
                'worker_count': len(data['worker_ids']),
                'working_days': len(data['present_dates']),
                'ot_hours': round(data['ot_hours'], 2),
                'labor_cost': round(data['labor_cost'], 2),
                'members': members,
            })
        return out

    projects_list = _build_breakdown(project_data)
    teams_list = _build_breakdown(team_data)
    supervisors_list = _build_breakdown(supervisor_data)

    daily_list = []
    for date_str in sorted(daily_data.keys()):
        d = daily_data[date_str]
        daily_list.append({
            'date': date_str,
            'present': d['present'],
            'absent': d['absent'],
            'holiday': d['holiday'],
            'ot_hours': round(d['ot_hours'], 2)
        })

    workers_list = []
    total_salary = 0.0
    for wid, data in sorted(worker_data.items(), key=lambda x: x[1]['name']):
        # Salary was accumulated per present-day at the worker's Base Pay/Day.
        salary = round(data['salary'], 2)
        total_salary += salary
        workers_list.append({
            'worker_id': data['worker_id'],
            'name': data['name'],
            'designation': data['designation'],
            'team': data['team'],
            'present_days': data['present_days'],
            'absent_days': data['absent_days'],
            'ot_hours': round(data['ot_hours'], 2),
            'salary': salary,
            'projects': sorted(list(data['projects'])),
            'roles': sorted(list(data['roles'])),
            'works': sorted(list(data['works'])),
            'supervisors': sorted(list(data['supervisors']))
        })

    # Working days = unique dates that had at least one Present worker
    working_days = sum(1 for d in daily_data.values() if d['present'] > 0)

    # Activity breakdown sorted by worker-days desc (most-done work first)
    activity_breakdown = [
        {'work': work, 'days': days}
        for work, days in sorted(activity.items(), key=lambda x: x[1], reverse=True)
    ]

    return jsonify({
        'total_workers': len(present_workers),  # Only count workers with Present status
        'working_days': working_days,
        'total_present_days': total_present_days,
        'total_ot_hours': round(total_ot_hours, 2),
        'total_salary': round(total_salary, 2),
        'projects': projects_list,
        'teams': teams_list,
        'supervisors': supervisors_list,
        'daily_breakdown': daily_list,
        'workers': workers_list,
        'activity_breakdown': activity_breakdown
    })


@attendance_bp.route('/api/attendance/export', methods=['GET'])
def export_attendance():
    """Get all attendance records for export."""
    project = request.args.get('project', '').strip()

    # Get all attendance records with worker info (identity from Worker master)
    query = db.session.query(
        Attendance,
        Worker.name,
        Worker.designation
    ).join(
        Worker,
        (Attendance.worker_id == Worker.id)
    )

    if project:
        query = query.filter(Attendance.project == project)

    records = query.distinct(
        Attendance.id
    ).order_by(
        Attendance.date.desc(),
        Worker.name
    ).all()

    # Remove duplicates (keep first occurrence per attendance record)
    seen = set()
    result = []
    for att, name, designation in records:
        if att.id not in seen:
            seen.add(att.id)
            result.append({
                'date': att.date.isoformat(),
                'worker_id': att.worker_id,
                'name': name,
                'designation': designation,
                'status': att.status,
                'ot_hours': float(att.ot_hours) if att.ot_hours else 0,
                'project': att.project or '',
                'role': att.role or '',
                'work': att.work or ''
            })

    return jsonify(result)
