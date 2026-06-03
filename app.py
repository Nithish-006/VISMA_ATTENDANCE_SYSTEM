import os
from flask import Flask, render_template
from flask_cors import CORS
from sqlalchemy import inspect, text
from config import config
from models import db


def run_migrations(app):
    """Apply lightweight schema changes that db.create_all() can't handle.

    create_all() makes new tables (e.g. supervisor) but never alters existing
    ones, so adding attendance.supervisor_id to a live DB needs an explicit
    ALTER. Idempotent: checks the column exists before adding it.
    """
    with app.app_context():
        try:
            inspector = inspect(db.engine)
            if 'attendance' not in inspector.get_table_names():
                return
            columns = {c['name']: c for c in inspector.get_columns('attendance')}
            if 'supervisor_id' not in columns:
                db.session.execute(
                    text('ALTER TABLE attendance ADD COLUMN supervisor_id INTEGER NULL')
                )
                db.session.commit()
                app.logger.info("Migration: added attendance.supervisor_id")

            # Role is chosen per day at marking time (roles are elastic), so it
            # lives on the attendance record rather than the worker.
            if 'role' not in columns:
                db.session.execute(
                    text('ALTER TABLE attendance ADD COLUMN role VARCHAR(50) NULL')
                )
                db.session.commit()
                app.logger.info("Migration: added attendance.role")

            # Like role, the work done is per-day and chosen at marking time.
            if 'work' not in columns:
                db.session.execute(
                    text('ALTER TABLE attendance ADD COLUMN work VARCHAR(50) NULL')
                )
                db.session.commit()
                app.logger.info("Migration: added attendance.work")

            # Canonical project values ("{id} - {stem_name}") can exceed the
            # original VARCHAR(100), since stem_name alone is up to 255 chars.
            # Widen the column if it's still too narrow.
            project_col = columns.get('project')
            project_len = getattr(getattr(project_col, 'type', None), 'length', None) if project_col else None
            if project_col is not None and (project_len is None or project_len < 300):
                db.session.execute(
                    text('ALTER TABLE attendance MODIFY COLUMN project VARCHAR(300)')
                )
                db.session.commit()
                app.logger.info("Migration: widened attendance.project to VARCHAR(300)")

            # Audit columns. create_all() adds these to the new `worker` table
            # but never to the pre-existing attendance/salary tables, so add
            # them explicitly. CURRENT_TIMESTAMP backfills existing rows with
            # the time the column is added (best available for legacy rows).
            for tbl in ('attendance', 'salary'):
                if tbl not in inspector.get_table_names():
                    continue
                tbl_cols = {c['name'] for c in inspector.get_columns(tbl)}
                if 'created_at' not in tbl_cols:
                    db.session.execute(text(
                        f'ALTER TABLE {tbl} ADD COLUMN created_at DATETIME NULL '
                        f'DEFAULT CURRENT_TIMESTAMP'
                    ))
                    db.session.commit()
                    app.logger.info(f"Migration: added {tbl}.created_at")
                if 'updated_at' not in tbl_cols:
                    db.session.execute(text(
                        f'ALTER TABLE {tbl} ADD COLUMN updated_at DATETIME NULL '
                        f'DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'
                    ))
                    db.session.commit()
                    app.logger.info(f"Migration: added {tbl}.updated_at")
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Migration failed: {e}")


DEFAULT_SUPERVISORS = ['Thamburaj', 'Dhanapal', 'Arjun']


def seed_supervisors(app):
    """Ensure the canonical supervisors exist so the Mark-attendance dropdown
    is never empty.

    The roster was revised to exactly DEFAULT_SUPERVISORS. The first startup
    after that change is detected by *none* of the canonical names being
    present yet — when that's the case we clear the old roster and insert the
    new names (a one-time replacement). On every later startup we only top-up
    missing canonical names, so any supervisor added through the UI ('+ New')
    is preserved across restarts. Safe on fresh/empty deployments too.
    """
    from models import Supervisor

    with app.app_context():
        try:
            existing = Supervisor.query.all()
            existing_names = {s.name.lower() for s in existing}
            desired_names = {n.lower() for n in DEFAULT_SUPERVISORS}

            # One-time replacement: a non-empty roster with no overlap at all
            # means we're still on the old defaults — wipe and re-seed.
            if existing and not (desired_names & existing_names):
                for s in existing:
                    db.session.delete(s)
                db.session.flush()
                existing_names = set()
                app.logger.info("Cleared previous supervisor roster for replacement")

            added = False
            for name in DEFAULT_SUPERVISORS:
                if name.lower() not in existing_names:
                    db.session.add(Supervisor(name=name))
                    added = True
            if added:
                db.session.commit()
                app.logger.info("Seeded default supervisors")
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Supervisor seeding failed: {e}")


def auto_init_database(app):
    """Auto-initialize database with data if empty (for Railway deployment)."""
    from models import Salary, Attendance

    with app.app_context():
        try:
            # Check if data exists
            if Salary.query.first() is not None:
                return  # Data exists, skip

            # Check if Excel files exist
            if not os.path.exists('Attendance.xlsx') or not os.path.exists('Salary.xlsx'):
                app.logger.info("Excel files not found, skipping auto-import")
                return

            app.logger.info("Database empty - auto-importing from Excel files...")

            # Import the data
            from import_data import import_from_excel
            import_from_excel()

            app.logger.info("Auto-import completed!")

        except Exception as e:
            app.logger.error(f"Auto-init failed: {e}")


def create_app(config_name=None):
    """Application factory."""
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Initialize extensions
    CORS(app)
    db.init_app(app)

    # Register API blueprints
    from routes.attendance import attendance_bp
    from routes.salary import salary_bp

    app.register_blueprint(attendance_bp)
    app.register_blueprint(salary_bp)

    # Create database tables
    with app.app_context():
        db.create_all()

    # Apply incremental schema migrations (e.g. attendance.supervisor_id)
    run_migrations(app)

    # Ensure the default supervisors exist (populates the Mark dropdown)
    seed_supervisors(app)

    # Auto-initialize if database is empty (Railway deployment)
    if os.environ.get('FLASK_ENV') == 'production':
        auto_init_database(app)

    # Page routes
    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/attendance')
    def attendance_page():
        return render_template('attendance.html')

    @app.route('/salary')
    def salary_page():
        return render_template('salary.html')

    # Health check
    @app.route('/api/health')
    def health_check():
        return {'status': 'healthy'}

    # Manual database init endpoint (one-time use)
    @app.route('/api/init-db', methods=['POST'])
    def init_db_endpoint():
        from models import Salary, Attendance

        # Check if already has data
        if Salary.query.first() is not None:
            return {'status': 'skipped', 'message': 'Data already exists'}, 200

        try:
            # Check for Excel files
            if not os.path.exists('Attendance.xlsx') or not os.path.exists('Salary.xlsx'):
                return {'status': 'error', 'message': 'Excel files not found'}, 404

            from import_data import import_from_excel
            success = import_from_excel()

            if success:
                count = Salary.query.count()
                return {'status': 'success', 'message': f'Imported {count} workers'}, 200
            else:
                return {'status': 'error', 'message': 'Import failed'}, 500
        except Exception as e:
            return {'status': 'error', 'message': str(e)}, 500

    return app


# Create app instance for gunicorn (production)
app = create_app()

if __name__ == '__main__':
    app.run(debug=True, port=5000)
