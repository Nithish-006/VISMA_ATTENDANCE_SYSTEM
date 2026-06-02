from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class Salary(db.Model):
    """Monthly salary records - one row per worker per month."""
    __tablename__ = 'salary'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    worker_id = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    designation = db.Column(db.String(50))
    team = db.Column(db.String(50))
    base_salary_per_day = db.Column(db.Numeric(10, 2), default=0)
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)  # 1-12
    total_working_days = db.Column(db.Integer, default=0)
    ot_hours = db.Column(db.Numeric(6, 2), default=0)
    total_salary = db.Column(db.Numeric(12, 2), default=0)

    __table_args__ = (
        db.UniqueConstraint('worker_id', 'year', 'month', name='unique_worker_month'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'worker_id': self.worker_id,
            'name': self.name,
            'designation': self.designation,
            'team': self.team,
            'base_salary_per_day': float(self.base_salary_per_day) if self.base_salary_per_day else 0,
            'year': self.year,
            'month': self.month,
            'total_working_days': self.total_working_days,
            'ot_hours': float(self.ot_hours) if self.ot_hours else 0,
            'total_salary': float(self.total_salary) if self.total_salary else 0
        }


class Supervisor(db.Model):
    """Supervisors who mark attendance. Workers are not fixed to a supervisor."""
    __tablename__ = 'supervisor'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False, unique=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name
        }


class Attendance(db.Model):
    """Attendance records - daily attendance linked to worker."""
    __tablename__ = 'attendance'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    worker_id = db.Column(db.Integer, nullable=False)
    date = db.Column(db.Date, nullable=False)
    # 'H' is retained for legacy data; new marking only uses 'P'/'A'.
    status = db.Column(db.Enum('P', 'A', 'H', name='attendance_status'), default='A')
    ot_hours = db.Column(db.Numeric(4, 2), default=0)
    project = db.Column(db.String(300))  # holds canonical "{id} - {stem_name}"
    supervisor_id = db.Column(db.Integer)  # who marked it (nullable for legacy records)
    # Role performed on this day. Roles are elastic — a worker can do any job —
    # so the role is chosen per attendance record, not fixed to the worker.
    role = db.Column(db.String(50))
    # The specific work done that day (e.g. welding, grinding). Like role, it's
    # per-day and chosen at marking time.
    work = db.Column(db.String(50))

    __table_args__ = (
        db.UniqueConstraint('worker_id', 'date', name='unique_daily_attendance'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'worker_id': self.worker_id,
            'date': self.date.isoformat() if self.date else None,
            'status': self.status,
            'ot_hours': float(self.ot_hours) if self.ot_hours else 0,
            'project': self.project,
            'supervisor_id': self.supervisor_id,
            'role': self.role,
            'work': self.work
        }
