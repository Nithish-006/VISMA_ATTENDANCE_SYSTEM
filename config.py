import os
import sys
from dotenv import load_dotenv

load_dotenv()


def get_database_url():
    """Build database URL from Railway environment variables."""
    # First check for explicit DATABASE_URL
    if os.environ.get('DATABASE_URL'):
        url = os.environ.get('DATABASE_URL')
        if url.startswith('mysql://'):
            url = url.replace('mysql://', 'mysql+pymysql://', 1)
        print(f"[Config] Using DATABASE_URL", file=sys.stderr)
        return url

    # Check for Railway's MYSQL_URL (auto-provided when MySQL is linked)
    if os.environ.get('MYSQL_URL'):
        url = os.environ.get('MYSQL_URL')
        # Railway uses mysql:// but SQLAlchemy needs mysql+pymysql://
        if url.startswith('mysql://'):
            url = url.replace('mysql://', 'mysql+pymysql://', 1)
        print(f"[Config] Using MYSQL_URL", file=sys.stderr)
        return url

    # Build from individual Railway MySQL variables
    # Railway uses both formats: MYSQLHOST and MYSQL_HOST
    host = os.environ.get('MYSQLHOST') or os.environ.get('MYSQL_HOST')
    port = os.environ.get('MYSQLPORT') or os.environ.get('MYSQL_PORT') or '3306'
    database = os.environ.get('MYSQLDATABASE') or os.environ.get('MYSQL_DATABASE')
    user = os.environ.get('MYSQLUSER') or os.environ.get('MYSQL_USER')
    password = os.environ.get('MYSQLPASSWORD') or os.environ.get('MYSQL_PASSWORD') or ''

    if all([host, database, user]):
        print(f"[Config] Using individual MySQL vars: {user}@{host}:{port}/{database}", file=sys.stderr)
        return f'mysql+pymysql://{user}:{password}@{host}:{port}/{database}'

    # Fallback to local development
    print("[Config] No Railway MySQL vars found, using local database", file=sys.stderr)
    return 'mysql+pymysql://root:@localhost/visma_attendance'


class Config:
    """Base configuration."""
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key')


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = get_database_url()


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = get_database_url()


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
