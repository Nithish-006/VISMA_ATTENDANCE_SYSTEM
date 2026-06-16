from flask import Blueprint, request, jsonify
from models import db, Salary, Attendance, Worker, compute_pay
from decimal import Decimal
from sqlalchemy import func, case
import calendar

salary_bp = Blueprint('salary', __name__)


@salary_bp.route('/api/salary', methods=['GET'])
def get_all_salaries():
    """Get all salary records grouped by month."""
    return get_monthly_salaries()


@salary_bp.route('/api/salary/monthly', methods=['GET'])
def get_monthly_salaries():
    """Get monthly salary breakdown."""
    # Get all salary records ordered by date (newest first)
    records = Salary.query.order_by(
        Salary.year.desc(),
        Salary.month.desc(),
        Salary.name
    ).all()

    # Pay model per worker (single source of truth is the Worker master). Used
    # to decide whether OT is paid; missing workers default to daily-rate.
    monthly_flag = {
        w.id: bool(w.monthly_salaried) for w in Worker.query.all()
    }

    # Group by month
    months_data = {}
    for record in records:
        month_key = f"{record.year}-{record.month:02d}"
        if month_key not in months_data:
            months_data[month_key] = {
                'workers': [],
                'total_salary': Decimal('0')
            }

        # Calculate base_pay and ot_pay. Monthly-salaried workers track OT but
        # are never paid for it, so ot_pay is 0 for them (compute_pay enforces).
        base_salary = float(record.base_salary_per_day) if record.base_salary_per_day else 0
        working_days = record.total_working_days or 0
        ot_hours = float(record.ot_hours) if record.ot_hours else 0
        is_monthly = monthly_flag.get(record.worker_id, False)
        base_pay, ot_pay, _ = compute_pay(base_salary, working_days, ot_hours, monthly_salaried=is_monthly)

        months_data[month_key]['workers'].append({
            'id': record.id,
            'worker_id': record.worker_id,
            'name': record.name,
            'designation': record.designation,
            'base_salary_per_day': base_salary,
            'monthly_salaried': is_monthly,
            'working_days': working_days,
            'ot_hours': ot_hours,
            'base_pay': base_pay,
            'ot_pay': ot_pay,
            'total_salary': float(record.total_salary) if record.total_salary else 0
        })
        months_data[month_key]['total_salary'] += Decimal(str(record.total_salary or 0))

    # Convert to list
    result = []
    for month_key in sorted(months_data.keys(), reverse=True):
        year, month = month_key.split('-')
        result.append({
            'month': month_key,
            'year': int(year),
            'month_num': int(month),
            'month_name': f"{calendar.month_name[int(month)]} {year}",
            'workers': months_data[month_key]['workers'],
            'total_salary': float(months_data[month_key]['total_salary'])
        })

    return jsonify(result)


@salary_bp.route('/api/salary/<int:record_id>', methods=['GET'])
def get_salary_record(record_id):
    """Get a specific salary record."""
    salary = Salary.query.get_or_404(record_id)
    return jsonify(salary.to_dict())


@salary_bp.route('/api/salary/<int:record_id>', methods=['PUT'])
def update_salary(record_id):
    """Update salary info for a record."""
    salary = Salary.query.get_or_404(record_id)
    data = request.get_json()

    if 'base_salary_per_day' in data:
        salary.base_salary_per_day = data['base_salary_per_day']
        # Recalculate total for this month (OT excluded for monthly workers).
        worker = Worker.query.get(salary.worker_id)
        is_monthly = bool(worker.monthly_salaried) if worker else False
        _, _, salary.total_salary = compute_pay(
            salary.base_salary_per_day, salary.total_working_days, salary.ot_hours,
            monthly_salaried=is_monthly
        )

    if 'name' in data:
        salary.name = data['name']
    if 'designation' in data:
        salary.designation = data['designation']

    db.session.commit()
    return jsonify(salary.to_dict())


@salary_bp.route('/api/salary/worker/<int:worker_id>', methods=['PUT'])
def update_worker_salary(worker_id):
    """Update worker details — without silently rewriting wage history.

    The Worker master is the single source of truth and is always updated here,
    so the new rate / pay model takes effect going forward (the current month is
    recomputed from the master whenever attendance is next marked).

    Name and designation are pure labels, so they propagate to every monthly
    snapshot for consistency. A change to base pay or the pay model (daily vs
    monthly), however, re-prices ONLY the months the caller explicitly lists in
    `reprice_months` (["YYYY-MM", ...]). Past months not listed stay frozen at
    the rate and total that were actually paid then — finalized history is never
    retroactively rewritten unless the user opts a month in.
    """
    data = request.get_json()
    base_salary = data.get('base_salary_per_day')
    designation = data.get('designation')
    name = data.get('name')
    monthly_salaried = data.get('monthly_salaried')
    reprice_months = data.get('reprice_months') or []

    if base_salary is None and designation is None and name is None and monthly_salaried is None:
        return jsonify({'error': 'At least one field (name, designation, base_salary_per_day, monthly_salaried) is required'}), 400

    worker = Worker.query.get(worker_id)
    if worker is None:
        return jsonify({'error': 'Worker not found'}), 404

    # 1. Update the master record (authoritative — drives future months).
    if name is not None:
        worker.name = name
    if designation is not None:
        worker.designation = designation
    if base_salary is not None:
        worker.base_salary_per_day = base_salary
    if monthly_salaried is not None:
        worker.monthly_salaried = bool(monthly_salaried)

    # The effective pay model after this update — drives whether OT is paid.
    is_monthly = bool(worker.monthly_salaried)

    # Parse the opt-in month list into a set of (year, month) to re-price.
    reprice_set = set()
    for token in reprice_months:
        try:
            y, m = str(token).split('-')
            reprice_set.add((int(y), int(m)))
        except (ValueError, AttributeError):
            continue

    # 2. Sync the monthly snapshots. Labels (name/designation) propagate to all;
    # base pay and total are rewritten ONLY for explicitly-selected months.
    records = Salary.query.filter_by(worker_id=worker_id).all()
    repriced = 0
    for salary in records:
        if name is not None:
            salary.name = name
        if designation is not None:
            salary.designation = designation
        if (salary.year, salary.month) in reprice_set:
            # Apply the new base rate to this month if one was provided; otherwise
            # keep the month's own historical rate and only re-apply the OT rule.
            if base_salary is not None:
                salary.base_salary_per_day = base_salary
            _, _, salary.total_salary = compute_pay(
                salary.base_salary_per_day, salary.total_working_days, salary.ot_hours,
                monthly_salaried=is_monthly
            )
            repriced += 1

    db.session.commit()

    return jsonify({
        'message': f'Updated worker {worker_id} ({repriced} month(s) re-priced)',
        'worker_id': worker_id,
        'repriced_months': repriced
    })


@salary_bp.route('/api/salary/worker/<int:worker_id>', methods=['DELETE'])
def delete_worker(worker_id):
    """Delete a worker and all their attendance and salary records."""
    salary_records = Salary.query.filter_by(worker_id=worker_id).all()
    attendance_records = Attendance.query.filter_by(worker_id=worker_id).all()
    worker = Worker.query.get(worker_id)

    if not salary_records and not attendance_records and worker is None:
        return jsonify({'error': 'Worker not found'}), 404

    salary_count = len(salary_records)
    attendance_count = len(attendance_records)

    # Delete children before the parent so the worker FK (RESTRICT) is satisfied.
    for record in attendance_records:
        db.session.delete(record)
    for record in salary_records:
        db.session.delete(record)
    db.session.flush()
    if worker is not None:
        db.session.delete(worker)

    db.session.commit()

    return jsonify({
        'message': f'Worker {worker_id} deleted',
        'deleted_salary_records': salary_count,
        'deleted_attendance_records': attendance_count
    })
