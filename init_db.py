"""
Database initialization script for Railway deployment.

Run this once after deploying to import data:
    railway run python init_db.py

Or use Railway's shell:
    python init_db.py
"""

import os
import sys

# Set production environment
os.environ['FLASK_ENV'] = 'production'

from app import create_app
from models import db, Attendance, Salary
from import_data import import_from_excel, show_summary


def init_database():
    """Initialize database tables and import data."""
    print("=== Railway Database Initialization ===\n")

    app = create_app('production')

    with app.app_context():
        # Check database connection
        try:
            db.engine.connect()
            print("Database connection: OK")
        except Exception as e:
            print(f"Database connection FAILED: {e}")
            sys.exit(1)

        # Create tables
        print("Creating database tables...")
        db.create_all()
        print("Tables created successfully!\n")

        # Check if data already exists
        salary_count = Salary.query.count()
        attendance_count = Attendance.query.count()

        if salary_count > 0 or attendance_count > 0:
            print(f"Data already exists:")
            print(f"  - Salary records: {salary_count}")
            print(f"  - Attendance records: {attendance_count}")
            response = input("\nDo you want to reimport? This will DELETE existing data. (yes/no): ")
            if response.lower() != 'yes':
                print("Skipping import.")
                return

    # Run import
    print("\nImporting data from Excel files...")
    success = import_from_excel()

    if success:
        print("\n=== Initialization Complete ===")
        show_summary()
    else:
        print("\n=== Initialization Failed ===")
        sys.exit(1)


if __name__ == '__main__':
    init_database()
