from flask import Blueprint, request, jsonify
from models import db, Attendance, Salary
from datetime import datetime
from sqlalchemy import func, case

attendance_bp = Blueprint('attendance', __name__)


@attendance_bp.route('/api/labours', methods=['GET'])
def get_labours():
    """Get list of all unique workers (latest record per worker)."""
    # Get the most recent record for each worker
    subquery = db.session.query(
        Salary.worker_id,
        func.max(Salary.year * 100 + Salary.month).label('max_period')
    ).group_by(Salary.worker_id).subquery()

    workers = db.session.query(Salary).join(
        subquery,
        (Salary.worker_id == subquery.c.worker_id) &
        (Salary.year * 100 + Salary.month == subquery.c.max_period)
    ).order_by(Salary.team, Salary.name).all()

    result = []
    for w in workers:
        last_att = Attendance.query.filter_by(worker_id=w.worker_id).order_by(Attendance.date.desc()).first()
        result.append({
            'worker_id': w.worker_id,
            'name': w.name,
            'designation': w.designation,
            'team': w.team,
            'base_salary_per_day': float(w.base_salary_per_day) if w.base_salary_per_day else 0,
            'last_attendance': last_att.date.isoformat() if last_att else None
        })

    return jsonify(result)


@attendance_bp.route('/api/labours/<int:worker_id>/history', methods=['GET'])
def get_labour_history(worker_id):
    """Get complete attendance history for a worker."""
    # Get latest worker info
    worker = Salary.query.filter_by(worker_id=worker_id).order_by(
        Salary.year.desc(), Salary.month.desc()
    ).first_or_404()

    records = Attendance.query.filter_by(worker_id=worker_id).order_by(Attendance.date.desc()).all()

    return jsonify({
        'worker_id': worker.worker_id,
        'name': worker.name,
        'designation': worker.designation,
        'team': worker.team,
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

    # Get unique workers (latest record per worker)
    subquery = db.session.query(
        Salary.worker_id,
        func.max(Salary.year * 100 + Salary.month).label('max_period')
    ).group_by(Salary.worker_id).subquery()

    workers = db.session.query(Salary).join(
        subquery,
        (Salary.worker_id == subquery.c.worker_id) &
        (Salary.year * 100 + Salary.month == subquery.c.max_period)
    ).order_by(Salary.team, Salary.name).all()

    # Get attendance for the date
    attendance_map = {
        a.worker_id: a for a in Attendance.query.filter_by(date=filter_date).all()
    }

    result = []
    for w in workers:
        att = attendance_map.get(w.worker_id)
        result.append({
            'worker_id': w.worker_id,
            'name': w.name,
            'designation': w.designation,
            'team': w.team,
            'base_salary_per_day': float(w.base_salary_per_day) if w.base_salary_per_day else 0,
            'attendance': att.to_dict() if att else {
                'id': None,
                'worker_id': w.worker_id,
                'date': date_str,
                'status': 'A',
                'ot_hours': 0,
                'project': None
            }
        })

    return jsonify(result)


@attendance_bp.route('/api/attendance', methods=['POST'])
def mark_attendance():
    """Mark or update attendance (supports bulk)."""
    data = request.get_json()

    if isinstance(data, list):
        results = []
        affected = set()  # (worker_id, year, month)
        team_updates = {}  # worker_id -> team
        for record in data:
            result = _upsert_attendance(record)
            results.append(result)
            if 'worker_id' in record and 'date' in record:
                try:
                    d = datetime.strptime(record['date'], '%Y-%m-%d').date()
                    affected.add((record['worker_id'], d.year, d.month))
                except:
                    pass
            # Track team updates
            if 'worker_id' in record and 'team' in record and record['team']:
                team_updates[record['worker_id']] = record['team']
        db.session.commit()
        _recalculate_monthly_salaries(affected)
        _update_worker_teams(team_updates)
        return jsonify(results), 201

    result = _upsert_attendance(data)
    db.session.commit()
    if 'worker_id' in data and 'date' in data:
        try:
            d = datetime.strptime(data['date'], '%Y-%m-%d').date()
            _recalculate_monthly_salaries({(data['worker_id'], d.year, d.month)})
        except:
            pass
    # Handle single team update
    if 'worker_id' in data and 'team' in data and data['team']:
        _update_worker_teams({data['worker_id']: data['team']})
    return jsonify(result), 201


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
    else:
        attendance = Attendance(
            worker_id=worker_id,
            date=record_date,
            status=data.get('status', 'A'),
            ot_hours=data.get('ot_hours', 0),
            project=data.get('project')
        )
        db.session.add(attendance)

    db.session.flush()
    return attendance.to_dict()


def _recalculate_monthly_salaries(affected_periods):
    """Recalculate salary for affected (worker_id, year, month) combinations."""
    for worker_id, year, month in affected_periods:
        # Get worker info from most recent salary record
        worker_info = Salary.query.filter_by(worker_id=worker_id).order_by(
            Salary.year.desc(), Salary.month.desc()
        ).first()

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
                team=worker_info.team,
                base_salary_per_day=worker_info.base_salary_per_day,
                year=year,
                month=month,
                total_working_days=working_days,
                ot_hours=ot_hours,
                total_salary=total
            )
            db.session.add(salary)

    db.session.commit()


def _update_worker_teams(team_updates):
    """Update team for workers across all their salary records."""
    for worker_id, team in team_updates.items():
        # Update all salary records for this worker
        Salary.query.filter_by(worker_id=worker_id).update({'team': team})
    db.session.commit()


@attendance_bp.route('/api/labours', methods=['POST'])
def add_labour():
    """Add a new worker."""
    data = request.get_json()

    name = data.get('name')
    base_salary = data.get('base_salary_per_day', 0)

    if not name:
        return jsonify({'error': 'name is required'}), 400

    # Get next worker_id
    max_id = db.session.query(func.max(Salary.worker_id)).scalar() or 0
    new_id = max_id + 1

    # Get current month/year
    now = datetime.now()

    salary = Salary(
        worker_id=new_id,
        name=name,
        designation=data.get('designation'),
        team=data.get('team'),
        base_salary_per_day=base_salary,
        year=now.year,
        month=now.month,
        total_working_days=0,
        ot_hours=0,
        total_salary=0
    )
    db.session.add(salary)
    db.session.commit()

    return jsonify(salary.to_dict()), 201


@attendance_bp.route('/api/teams', methods=['GET'])
def get_teams():
    """Get list of unique teams."""
    teams = db.session.query(Salary.team).distinct().filter(Salary.team.isnot(None)).all()
    return jsonify([t[0] for t in teams if t[0]])


@attendance_bp.route('/api/projects', methods=['GET'])
def get_projects():
    """Get list of unique projects."""
    projects = db.session.query(Attendance.project).distinct().filter(Attendance.project.isnot(None)).all()
    return jsonify([p[0] for p in projects if p[0]])


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
        # Get latest salary record per worker for name/team info
        subquery = db.session.query(
            Salary.worker_id,
            func.max(Salary.year * 100 + Salary.month).label('max_period')
        ).filter(Salary.worker_id.in_(worker_ids)).group_by(Salary.worker_id).subquery()

        workers = db.session.query(Salary).join(
            subquery,
            (Salary.worker_id == subquery.c.worker_id) &
            (Salary.year * 100 + Salary.month == subquery.c.max_period)
        ).all()

        for w in workers:
            worker_info_map[w.worker_id] = {
                'name': w.name,
                'team': w.team,
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

    total_present_days = 0
    total_ot_hours = 0.0

    for r in records:
        ot = float(r.ot_hours) if r.ot_hours else 0
        proj = r.project or 'Unassigned'
        date_str = r.date.isoformat()

        # Project aggregation - only include present workers
        if r.status == 'P':
            if proj not in project_data:
                project_data[proj] = {'worker_ids': set(), 'present_dates': set(), 'ot_hours': 0}
            project_data[proj]['worker_ids'].add(r.worker_id)
            project_data[proj]['present_dates'].add(r.date)
            project_data[proj]['ot_hours'] += ot
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
                'team': info.get('team', ''),
                'base_salary_per_day': info.get('base_salary_per_day', 0),
                'present_days': 0,
                'absent_days': 0,
                'ot_hours': 0,
                'projects': set()
            }
        if r.status == 'P':
            worker_data[r.worker_id]['present_days'] += 1
        elif r.status == 'A':
            worker_data[r.worker_id]['absent_days'] += 1
        worker_data[r.worker_id]['ot_hours'] += ot
        if r.project:
            worker_data[r.worker_id]['projects'].add(r.project)

    # Build response
    projects_list = []
    for name, data in sorted(project_data.items()):
        projects_list.append({
            'name': name,
            'worker_count': len(data['worker_ids']),
            'working_days': len(data['present_dates']),
            'ot_hours': round(data['ot_hours'], 2)
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
            'team': data['team'],
            'present_days': data['present_days'],
            'absent_days': data['absent_days'],
            'ot_hours': round(data['ot_hours'], 2),
            'salary': salary,
            'projects': sorted(list(data['projects']))
        })

    # Working days = unique dates that had at least one Present worker
    working_days = sum(1 for d in daily_data.values() if d['present'] > 0)

    return jsonify({
        'total_workers': len(present_workers),  # Only count workers with Present status
        'working_days': working_days,
        'total_present_days': total_present_days,
        'total_ot_hours': round(total_ot_hours, 2),
        'total_salary': round(total_salary, 2),
        'projects': projects_list,
        'daily_breakdown': daily_list,
        'workers': workers_list
    })


@attendance_bp.route('/api/attendance/export', methods=['GET'])
def export_attendance():
    """Get all attendance records for export."""
    project = request.args.get('project', '').strip()

    # Get all attendance records with worker info
    query = db.session.query(
        Attendance,
        Salary.name,
        Salary.designation,
        Salary.team
    ).join(
        Salary,
        (Attendance.worker_id == Salary.worker_id)
    )

    if project:
        query = query.filter(Attendance.project == project)

    records = query.distinct(
        Attendance.id
    ).order_by(
        Attendance.date.desc(),
        Salary.team,
        Salary.name
    ).all()

    # Remove duplicates (keep first occurrence per attendance record)
    seen = set()
    result = []
    for att, name, designation, team in records:
        if att.id not in seen:
            seen.add(att.id)
            result.append({
                'date': att.date.isoformat(),
                'worker_id': att.worker_id,
                'name': name,
                'designation': designation,
                'team': team,
                'status': att.status,
                'ot_hours': float(att.ot_hours) if att.ot_hours else 0,
                'project': att.project or ''
            })

    return jsonify(result)
