import os
from dotenv import load_dotenv

load_dotenv()


def get_database_url():
    """Build database URL from Railway environment variables."""
    # First check for explicit DATABASE_URL
    if os.environ.get('DATABASE_URL'):
        return os.environ.get('DATABASE_URL')

    # Check for Railway's MYSQL_URL
    if os.environ.get('MYSQL_URL'):
        url = os.environ.get('MYSQL_URL')
        # Railway uses mysql:// but SQLAlchemy needs mysql+pymysql://
        if url.startswith('mysql://'):
            url = url.replace('mysql://', 'mysql+pymysql://', 1)
        return url

    # Build from individual Railway MySQL variables
    host = os.environ.get('MYSQLHOST')
    port = os.environ.get('MYSQLPORT', '3306')
    database = os.environ.get('MYSQLDATABASE')
    user = os.environ.get('MYSQLUSER')
    password = os.environ.get('MYSQLPASSWORD')

    if all([host, database, user]):
        return f'mysql+pymysql://{user}:{password}@{host}:{port}/{database}'

    # Fallback to local development
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
