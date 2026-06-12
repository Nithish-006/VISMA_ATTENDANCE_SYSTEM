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
    """Update worker details.

    The Worker master is the single source of truth and is updated here. The
    per-month salary snapshots are then kept in sync so the monthly salary view
    stays consistent — this preserves prior behaviour: a name/designation change
    is reflected across all months, and a base-pay change recalculates every
    month's total.

    NOTE: retroactively re-pricing finalized past months on a base-pay change is
    pointer #2; it is intentionally left as-is here pending that decision.
    """
    data = request.get_json()
    base_salary = data.get('base_salary_per_day')
    designation = data.get('designation')
    name = data.get('name')
    monthly_salaried = data.get('monthly_salaried')

    if base_salary is None and designation is None and name is None and monthly_salaried is None:
        return jsonify({'error': 'At least one field (name, designation, base_salary_per_day, monthly_salaried) is required'}), 400

    worker = Worker.query.get(worker_id)
    if worker is None:
        return jsonify({'error': 'Worker not found'}), 404

    # 1. Update the master record (authoritative).
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

    # 2. Keep the monthly salary snapshots in sync. A change to base pay OR the
    # monthly-salaried flag re-prices every month (the flag toggles OT on/off).
    reprice = base_salary is not None or monthly_salaried is not None
    records = Salary.query.filter_by(worker_id=worker_id).all()
    for salary in records:
        if name is not None:
            salary.name = name
        if designation is not None:
            salary.designation = designation
        if base_salary is not None:
            salary.base_salary_per_day = base_salary
        if reprice:
            _, _, salary.total_salary = compute_pay(
                salary.base_salary_per_day, salary.total_working_days, salary.ot_hours,
                monthly_salaried=is_monthly
            )

    db.session.commit()

    return jsonify({'message': f'Updated worker {worker_id} ({len(records)} months synced)', 'worker_id': worker_id})


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
