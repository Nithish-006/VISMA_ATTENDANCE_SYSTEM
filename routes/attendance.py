from flask import Blueprint, request, jsonify
from models import db, Attendance, Salary, Supervisor, Worker
from datetime import datetime
from sqlalchemy import func, case
from services.projects_registry import get_projects, ProjectsRegistryError

attendance_bp = Blueprint('attendance', __name__)


def _worker_info_map(worker_ids):
    """Return {worker_id: Worker} for the given worker ids.

    Worker is the single source of truth for identity (name/designation/rate);
    callers use .name/.designation/.base_salary_per_day off the returned rows.
    """
    if not worker_ids:
        return {}
    workers = Worker.query.filter(Worker.id.in_(worker_ids)).all()
    return {w.id: w for w in workers}


# Attendance can be marked or edited for any past day up to and including today.
# Future dates are rejected (you can't record attendance for a day that hasn't
# happened yet).
def _is_within_marking_window(date_str):
    """True if date_str (YYYY-MM-DD) is a valid date no later than today."""
    try:
        d = datetime.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return False
    return d <= datetime.now().date()


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
            'base_salary_per_day': float(w.base_salary_per_day) if w.base_salary_per_day else 0,
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

    Attendance can be created or edited for any past day up to and including
    today; only future dates are rejected.
    """
    data = request.get_json()

    # Guard: every record must fall within the marking window (any date up to
    # today) and a present worker must be assigned to a project (so labor cost
    # can be attributed). Absent workers don't require a project.
    records_to_check = data if isinstance(data, list) else [data]
    for rec in records_to_check:
        if not isinstance(rec, dict) or not _is_within_marking_window(rec.get('date')):
            return jsonify({
                'error': 'Attendance cannot be marked for a future date.'
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
    """Remove a worker's attendance for a date (any date up to today)."""
    try:
        record_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    if not _is_within_marking_window(date_str):
        return jsonify({'error': 'Attendance cannot be edited for a future date.'}), 403

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
        base_salary = float(worker_info.base_salary_per_day) if worker_info.base_salary_per_day else 0

        # Calculate salary
        base_pay = working_days * base_salary
        ot_pay = (base_salary / 8) * ot_hours if base_salary > 0 else 0
        total = base_pay + ot_pay

        # Upsert salary record for this month
        salary = Salary.query.filter_by(worker_id=worker_id, year=year, month=month).first()

        if salary:
            salary.total_working_days = working_days
            salary.ot_hours = ot_hours
            salary.total_salary = total
        else:
            salary = Salary(
                worker_id=worker_id,
                name=worker_info.name,
                designation=worker_info.designation,
                base_salary_per_day=worker_info.base_salary_per_day,
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

    if not name:
        return jsonify({'error': 'name is required'}), 400

    worker = Worker(
        name=name,
        designation=designation,
        base_salary_per_day=base_salary,
        active=True,
    )
    db.session.add(worker)
    db.session.flush()  # assign worker.id before the salary row references it

    now = datetime.now()
    salary = Salary(
        worker_id=worker.id,
        name=name,
        designation=designation,
        base_salary_per_day=base_salary,
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
                'base_salary_per_day': float(w.base_salary_per_day) if w.base_salary_per_day else 0
            }

    # Aggregate by project
    project_data = {}
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

        # Project aggregation - only include present workers
        if r.status == 'P':
            if proj not in project_data:
                project_data[proj] = {'worker_ids': set(), 'present_dates': set(), 'ot_hours': 0, 'labor_cost': 0.0}
            project_data[proj]['worker_ids'].add(r.worker_id)
            project_data[proj]['present_dates'].add(r.date)
            project_data[proj]['ot_hours'] += ot
            # Labor cost for this present-day: base day-rate plus overtime paid
            # at the per-hour rate (rate/8), matching the salary calculation.
            rate = worker_info_map.get(r.worker_id, {}).get('base_salary_per_day', 0)
            project_data[proj]['labor_cost'] += rate + (rate / 8) * ot
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
                'base_salary_per_day': info.get('base_salary_per_day', 0),
                'present_days': 0,
                'absent_days': 0,
                'ot_hours': 0,
                'projects': set(),
                'roles': set(),
                'works': set()
            }
        if r.status == 'P':
            worker_data[r.worker_id]['present_days'] += 1
        elif r.status == 'A':
            worker_data[r.worker_id]['absent_days'] += 1
        worker_data[r.worker_id]['ot_hours'] += ot
        if r.project:
            worker_data[r.worker_id]['projects'].add(r.project)
        if r.role:
            worker_data[r.worker_id]['roles'].add(r.role)
        if r.work:
            worker_data[r.worker_id]['works'].add(r.work)

        # Activity breakdown counts worker-days of work actually done (present).
        if r.status == 'P' and r.work:
            activity[r.work] = activity.get(r.work, 0) + 1

    # Build response
    projects_list = []
    for name, data in sorted(project_data.items()):
        projects_list.append({
            'name': name,
            'worker_count': len(data['worker_ids']),
            'working_days': len(data['present_dates']),
            'ot_hours': round(data['ot_hours'], 2),
            'labor_cost': round(data['labor_cost'], 2)
        })

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
        base = data['base_salary_per_day']
        base_pay = data['present_days'] * base
        ot_pay = (base / 8) * data['ot_hours'] if base > 0 else 0
        salary = round(base_pay + ot_pay, 2)
        total_salary += salary
        workers_list.append({
            'worker_id': data['worker_id'],
            'name': data['name'],
            'present_days': data['present_days'],
            'absent_days': data['absent_days'],
            'ot_hours': round(data['ot_hours'], 2),
            'salary': salary,
            'projects': sorted(list(data['projects'])),
            'roles': sorted(list(data['roles'])),
            'works': sorted(list(data['works']))
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
