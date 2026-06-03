from flask import Blueprint, request, jsonify
from models import db, Salary, Attendance
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

    # Group by month
    months_data = {}
    for record in records:
        month_key = f"{record.year}-{record.month:02d}"
        if month_key not in months_data:
            months_data[month_key] = {
                'workers': [],
                'total_salary': Decimal('0')
            }

        # Calculate base_pay and ot_pay
        base_salary = float(record.base_salary_per_day) if record.base_salary_per_day else 0
        working_days = record.total_working_days or 0
        ot_hours = float(record.ot_hours) if record.ot_hours else 0
        base_pay = working_days * base_salary
        ot_pay = (base_salary / 8) * ot_hours if base_salary > 0 else 0

        months_data[month_key]['workers'].append({
            'id': record.id,
            'worker_id': record.worker_id,
            'name': record.name,
            'designation': record.designation,
            'base_salary_per_day': base_salary,
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
        # Recalculate total for this month
        base_salary = float(salary.base_salary_per_day)
        base_pay = salary.total_working_days * base_salary
        ot_pay = (base_salary / 8) * float(salary.ot_hours) if base_salary > 0 else 0
        salary.total_salary = base_pay + ot_pay

    if 'name' in data:
        salary.name = data['name']
    if 'designation' in data:
        salary.designation = data['designation']

    db.session.commit()
    return jsonify(salary.to_dict())


@salary_bp.route('/api/salary/worker/<int:worker_id>', methods=['PUT'])
def update_worker_salary(worker_id):
    """Update worker details across all monthly salary records."""
    data = request.get_json()
    base_salary = data.get('base_salary_per_day')
    designation = data.get('designation')
    name = data.get('name')

    if base_salary is None and designation is None and name is None:
        return jsonify({'error': 'At least one field (name, designation, base_salary_per_day) is required'}), 400

    # Get all salary records for this worker
    records = Salary.query.filter_by(worker_id=worker_id).all()

    if not records:
        return jsonify({'error': 'Worker not found'}), 404

    # Update all records
    for salary in records:
        if name is not None:
            salary.name = name
        if designation is not None:
            salary.designation = designation

        if base_salary is not None:
            salary.base_salary_per_day = base_salary
            base_pay = salary.total_working_days * float(base_salary)
            ot_pay = (float(base_salary) / 8) * float(salary.ot_hours) if base_salary > 0 else 0
            salary.total_salary = base_pay + ot_pay

    db.session.commit()

    return jsonify({'message': f'Updated {len(records)} records', 'worker_id': worker_id})


@salary_bp.route('/api/salary/worker/<int:worker_id>', methods=['DELETE'])
def delete_worker(worker_id):
    """Delete a worker and all their attendance and salary records."""
    salary_records = Salary.query.filter_by(worker_id=worker_id).all()
    attendance_records = Attendance.query.filter_by(worker_id=worker_id).all()

    if not salary_records and not attendance_records:
        return jsonify({'error': 'Worker not found'}), 404

    salary_count = len(salary_records)
    attendance_count = len(attendance_records)

    for record in attendance_records:
        db.session.delete(record)
    for record in salary_records:
        db.session.delete(record)

    db.session.commit()

    return jsonify({
        'message': f'Worker {worker_id} deleted',
        'deleted_salary_records': salary_count,
        'deleted_attendance_records': attendance_count
    })
