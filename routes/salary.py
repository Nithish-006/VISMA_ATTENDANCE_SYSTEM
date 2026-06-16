from flask import Blueprint, request, jsonify, send_file
from models import db, Salary, Attendance, Worker, compute_pay
from routes.attendance import ist_now
from decimal import Decimal
from sqlalchemy import func, case
from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from io import BytesIO
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

        # Every figure comes from the frozen snapshot, never recomputed from the
        # live pay model. base_pay is days x the rate that was in force that
        # month; the stored total already reflects whether OT was paid, so ot_pay
        # falls out as the remainder (0 for months a worker was monthly-salaried).
        # monthly_salaried is the pay model recorded for THAT month.
        base_salary = float(record.base_salary_per_day) if record.base_salary_per_day else 0
        working_days = record.total_working_days or 0
        ot_hours = float(record.ot_hours) if record.ot_hours else 0
        total_salary = float(record.total_salary) if record.total_salary else 0
        base_pay = round(working_days * base_salary, 2)
        ot_pay = max(0.0, round(total_salary - base_pay, 2))

        months_data[month_key]['workers'].append({
            'id': record.id,
            'worker_id': record.worker_id,
            'name': record.name,
            'designation': record.designation,
            'base_salary_per_day': base_salary,
            'monthly_salaried': bool(record.monthly_salaried),
            'working_days': working_days,
            'ot_hours': ot_hours,
            'base_pay': base_pay,
            'ot_pay': ot_pay,
            'total_salary': total_salary
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
    """Update worker details — pay-impacting changes apply from this month on.

    The Worker master is the single source of truth and is always updated here,
    so the new rate / pay model drives every future month automatically.

    Name and designation are pure labels, so they propagate to every monthly
    snapshot for consistency. A change to base pay or the pay model (daily vs
    monthly) re-prices ONLY the current month and any later month — every month
    before this one stays frozen at the rate and total that were actually paid
    then. Finalized history is never rewritten.
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
    pay_changed = base_salary is not None or monthly_salaried is not None

    # The boundary: the current month (IST). This month and every later month
    # are re-priced; everything earlier stays frozen.
    now = ist_now()
    current_ym = (now.year, now.month)

    # 2. Sync the monthly snapshots. Labels (name/designation) propagate to all;
    # base pay and total are rewritten only for the current month and forward.
    records = Salary.query.filter_by(worker_id=worker_id).all()
    repriced = 0
    for salary in records:
        if name is not None:
            salary.name = name
        if designation is not None:
            salary.designation = designation
        if pay_changed and (salary.year, salary.month) >= current_ym:
            if base_salary is not None:
                salary.base_salary_per_day = base_salary
            salary.monthly_salaried = is_monthly
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


@salary_bp.route('/api/salary/export', methods=['GET'])
def export_salary_report():
    """Build the salary report .xlsx entirely server-side.

    All pay figures flow through compute_pay (the single source of truth), so
    the workbook can never drift from the dashboard / salary view the way the
    old client-side calculation did. One sheet per month, newest first.

    Worker pay rows come from the frozen monthly Salary snapshots; the per-month
    project and daily breakdowns are computed from the attendance records, using
    the same present-only + monthly-salaried-OT-excluded rules the dashboard
    applies. An optional ?project= filter scopes to a single project.
    """
    project = request.args.get('project', '').strip()

    # Frozen per-month pay snapshots, newest first (mirrors /api/salary/monthly).
    salary_records = Salary.query.order_by(
        Salary.year.desc(), Salary.month.desc(), Salary.name
    ).all()

    months = {}  # (year, month) -> [worker pay dicts]
    for rec in salary_records:
        # Every figure comes from the frozen snapshot — never recomputed from the
        # live pay model. base_pay is days x the month's rate; the stored total
        # already reflects whether OT was paid, so ot_pay is the remainder.
        base = float(rec.base_salary_per_day) if rec.base_salary_per_day else 0
        working_days = rec.total_working_days or 0
        ot_hours = float(rec.ot_hours) if rec.ot_hours else 0
        total = float(rec.total_salary) if rec.total_salary else 0
        base_pay = round(working_days * base, 2)
        ot_pay = max(0.0, round(total - base_pay, 2))
        months.setdefault((rec.year, rec.month), []).append({
            'worker_id': rec.worker_id,
            'name': rec.name,
            'designation': rec.designation,
            'base_salary_per_day': base,
            'working_days': working_days,
            'ot_hours': ot_hours,
            'base_pay': base_pay,
            'ot_pay': ot_pay,
            'total_salary': total,
            # OT is paid for daily-rate months only (the month's frozen pay model).
            'paid_ot': base > 0 and not bool(rec.monthly_salaried),
        })

    # Attendance feeds the day grid and the project / daily breakdowns.
    att_query = Attendance.query
    if project:
        att_query = att_query.filter(Attendance.project == project)
    att_records = att_query.all()

    wb = Workbook()
    wb.remove(wb.active)  # drop the default empty sheet

    for (year, month) in sorted(months.keys(), reverse=True):
        month_abbr = calendar.month_name[month][:3].upper()
        year_short = str(year)[-2:]
        sheet_name = f"{month_abbr}-{year_short}"
        days_in_month = calendar.monthrange(year, month)[1]

        # Attendance for this month -> worker_id -> day -> cell.
        attendance_map = {}
        month_att = []
        for a in att_records:
            if a.date.year != year or a.date.month != month:
                continue
            month_att.append(a)
            attendance_map.setdefault(a.worker_id, {})[a.date.day] = {
                'status': a.status,
                'ot': float(a.ot_hours) if a.ot_hours else '',
                'project': a.project or '',
                'work': a.work or '',
            }

        # When a project is selected, only workers who actually worked it appear.
        if project:
            month_workers = [w for w in months[(year, month)]
                             if w['worker_id'] in attendance_map]
        else:
            month_workers = months[(year, month)]
        if not month_workers:
            continue

        # --- Header rows ---
        title_row = [f"LABOUR ATTENDANCE FOR {sheet_name}"]
        # The fixed designation rides in the Name column ("NAME - DESIGNATION")
        # rather than being repeated per day.
        header_row1 = ['S. No', 'Name']
        header_row2 = ['', '']
        for day in range(1, days_in_month + 1):
            is_sunday = calendar.weekday(year, month, day) == 6  # Mon=0..Sun=6
            header_row1 += [f"{day} SUNDAY" if is_sunday else day, '', '', '']
            header_row2 += ['', 'OT', 'Pr', 'Work']
        header_row1 += [f"{sheet_name} MONTH LABOUR ATTENDANCE & PAYMENT", '', '', '', '', '']
        header_row2 += ['TOTAL PRESENT', 'TOTAL OT', 'BASE SALARY', 'BASE PAY', 'OT PAY', 'TOTAL SALARY']

        # --- Worker data rows ---
        data_rows = []
        for s_no, w in enumerate(month_workers, start=1):
            name_with_role = f"{w['name']} - {w['designation']}" if w['designation'] else w['name']
            row = [s_no, name_with_role]
            for day in range(1, days_in_month + 1):
                cell = attendance_map.get(w['worker_id'], {}).get(day)
                if cell:
                    row += [cell['status'], cell['ot'] or '', cell['project'], cell['work']]
                else:
                    row += ['', '', '', '']
            row += [w['working_days'], w['ot_hours'], w['base_salary_per_day'],
                    w['base_pay'], w['ot_pay'], w['total_salary']]
            data_rows.append(row)

        # --- Monthly summary ---
        total_workers = len(month_workers)
        total_present = sum(w['working_days'] for w in month_workers)
        total_ot = round(sum(w['ot_hours'] for w in month_workers), 2)
        total_salary_amt = round(sum(w['total_salary'] for w in month_workers), 2)

        # --- Project breakdown (present-only). Labor cost uses the month's frozen
        # rate and its frozen OT decision: OT is added only for workers whose
        # snapshot shows OT was paid that month (daily-rate). ---
        rate_by_id = {w['worker_id']: w['base_salary_per_day'] for w in month_workers}
        paid_ot_by_id = {w['worker_id']: w['paid_ot'] for w in month_workers}
        project_stats = {}
        for a in month_att:
            if a.status != 'P':
                continue
            proj = a.project or 'Unassigned'
            ps = project_stats.setdefault(proj, {
                'worker_ids': set(), 'present_dates': set(),
                'ot_hours': 0.0, 'labor_cost': 0.0,
            })
            ps['worker_ids'].add(a.worker_id)
            ps['present_dates'].add(a.date)
            rate = rate_by_id.get(a.worker_id, 0)
            ot = float(a.ot_hours) if a.ot_hours else 0
            day_ot_pay = (rate / 8) * ot if paid_ot_by_id.get(a.worker_id) else 0
            ps['labor_cost'] += rate + day_ot_pay
            ps['ot_hours'] += ot

        # --- Daily headcount (OT across all statuses, matching the dashboard) ---
        daily_stats = {}
        for a in month_att:
            ds = daily_stats.setdefault(a.date.day, {
                'present': 0, 'absent': 0, 'holiday': 0, 'ot_hours': 0.0,
            })
            if a.status == 'P':
                ds['present'] += 1
            elif a.status == 'A':
                ds['absent'] += 1
            elif a.status == 'H':
                ds['holiday'] += 1
            ds['ot_hours'] += float(a.ot_hours) if a.ot_hours else 0

        # --- Assemble summary rows ---
        summary_rows = [
            [],
            ['MONTHLY SUMMARY'],
            ['Total Workers', total_workers, '', 'Total Present Days', total_present,
             '', 'Total OT Hours', total_ot, '', 'Total Salary', total_salary_amt],
            [],
            ['PROJECT BREAKDOWN'],
            ['Project', 'Workers', 'Working Days', 'OT Hours', 'Labor Cost'],
        ]
        for proj, stats in sorted(project_stats.items()):
            summary_rows.append([
                proj, len(stats['worker_ids']), len(stats['present_dates']),
                round(stats['ot_hours'], 2), round(stats['labor_cost'], 2),
            ])
        summary_rows += [[], ['DAILY HEADCOUNT'],
                         ['Day', 'Date', 'Present', 'Absent', 'Holiday', 'OT Hours']]
        for day in range(1, days_in_month + 1):
            ds = daily_stats.get(day)
            if not ds:
                continue
            day_name = calendar.day_abbr[calendar.weekday(year, month, day)]
            summary_rows.append([
                day_name, f"{day}/{month}/{year}",
                ds['present'], ds['absent'], ds['holiday'], round(ds['ot_hours'], 2),
            ])

        # --- Write the sheet ---
        ws = wb.create_sheet(title=sheet_name)
        for row in [title_row, header_row1, header_row2, *data_rows, *summary_rows]:
            ws.append(row)

        widths = [5, 28]
        for _ in range(days_in_month):
            widths += [3, 3, 8, 10]
        widths += [13, 10, 12, 10, 10, 12]
        for idx, width in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(idx)].width = width
        ws.merge_cells('A1:B1')

    # openpyxl cannot save a workbook with zero sheets.
    if not wb.sheetnames:
        wb.create_sheet(title='No Data')

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    suffix = f"_{project.replace(' ', '_')}" if project else ''
    filename = f"salary_report{suffix}_{ist_now().date().isoformat()}.xlsx"
    return send_file(
        buffer,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename,
    )
