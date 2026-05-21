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
            columns = [c['name'] for c in inspector.get_columns('attendance')]
            if 'supervisor_id' not in columns:
                db.session.execute(
                    text('ALTER TABLE attendance ADD COLUMN supervisor_id INTEGER NULL')
                )
                db.session.commit()
                app.logger.info("Migration: added attendance.supervisor_id")
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Migration failed: {e}")


DEFAULT_SUPERVISORS = ['AMBETHRAJ', 'KEDHAR', 'RAJU', 'VISMA']


def seed_supervisors(app):
    """Ensure the default supervisors exist so the Mark-attendance dropdown is
    never empty. Idempotent: only inserts names not already present
    (case-insensitive), so it's safe on every startup and fresh deployments.
    """
    from models import Supervisor
    from sqlalchemy import func

    with app.app_context():
        try:
            existing = {s.name.lower() for s in Supervisor.query.all()}
            added = False
            for name in DEFAULT_SUPERVISORS:
                if name.lower() not in existing:
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
