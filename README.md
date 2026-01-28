# Visma Attendance System

Factory attendance management system for supervisors to mark daily attendance, track overtime, and calculate wages.

## Features

- **Attendance Module**: View all labours, click to see history, mark daily attendance
- **Salary Module**: Monthly salary reports with export to CSV
- **Add New Labour**: Add workers on the fly while marking attendance

## Tech Stack

- Python + Flask
- MySQL + SQLAlchemy
- Jinja templates + vanilla JS

## Database Schema

**Attendance Table**
- id, date, name, designation, team, status (P/A/H), ot_hours, project

**Salary Table**
- id, name, month, year, total_working_days, ot_hours, base_salary_per_day, total_salary

## Setup

### 1. Create MySQL Database
```sql
CREATE DATABASE visma_attendance;
```

### 2. Configure Database
Edit `.env`:
```
DATABASE_URL=mysql+pymysql://root:yourpassword@localhost/visma_attendance
```

### 3. Install & Import Data
```bash
pip install -r requirements.txt
python import_data.py
```

### 4. Run
```bash
python app.py
```

Open **http://localhost:5000**

## UI Flow

1. **Landing Page** → Choose Attendance or Salary
2. **Attendance** → See all labours by team → Click to view history
3. **Mark Attendance** → Select date, mark P/A/H, add OT hours, save
4. **Salary** → Select month/year → View report → Export CSV
