# app/config.py
import os
from datetime import timedelta

class Config:
    DEBUG = False
    TESTING = False
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Configuração do banco de dados
    if 'RENDER' in os.environ:
        # No Render, usa DATABASE_URL diretamente e ajusta para postgresql://
        database_url = os.environ.get('DATABASE_URL')
        if not database_url:
            raise ValueError("DATABASE_URL não está definido no ambiente do Render")
        SQLALCHEMY_DATABASE_URI = database_url.replace('postgres://', 'postgresql://')
        # Garante que sslmode=require esteja presente
        if 'sslmode' not in SQLALCHEMY_DATABASE_URI:
            SQLALCHEMY_DATABASE_URI += '?sslmode=require'
    else:
        # Localmente, usa SQLite por padrão, a menos que TRY_POSTGRES esteja ativado
        try_postgres = os.getenv('TRY_POSTGRES', 'False').lower() == 'true'
        if try_postgres:
            database_url = os.environ.get('DATABASE_URL', 'sqlite:///facilita.db')
            if database_url.startswith('postgres://'):
                database_url = database_url.replace('postgres://', 'postgresql://')
            if 'postgresql://' in database_url and 'sslmode' not in database_url:
                database_url += '?sslmode=require'
            SQLALCHEMY_DATABASE_URI = database_url
        else:
            SQLALCHEMY_DATABASE_URI = 'sqlite:///facilita.db'
    
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', '00974655')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    CORS_HEADERS = 'Content-Type'

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    pass

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'

config_by_name = {
    'dev': DevelopmentConfig,
    'prod': ProductionConfig,
    'test': TestingConfig
}

def get_config():
    env = os.environ.get('FLASK_ENV', 'dev')
    return config_by_name[env]