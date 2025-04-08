# app/__init__.py
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
import os
from dotenv import load_dotenv

# Carrega o .env localmente
load_dotenv()

db = SQLAlchemy()

def create_app():
    app = Flask(__name__)
    
    # Configurações
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', '00974655')
    database_url = os.getenv('DATABASE_URL', 'sqlite:///facilita.db')
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://')
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Inicializar extensões
    db.init_app(app)
    
    # Registrar rotas
    from .routes import init_routes
    from .queue_routes import init_queue_routes
    init_routes(app)
    init_queue_routes(app)
    
    return app