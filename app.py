import os
from flask import Flask, render_template
from flask_cors import CORS
from config import config
from models import db


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

    # Page routes
    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/attendance')
    def attendance_page():
        return render_template('attendance.html')

    @app.route('/attendance/mark')
    def mark_attendance_page():
        return render_template('mark_attendance.html')

    @app.route('/salary')
    def salary_page():
        return render_template('salary.html')

    # Health check
    @app.route('/api/health')
    def health_check():
        return {'status': 'healthy'}

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, port=5000)
