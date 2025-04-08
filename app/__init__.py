# app/__init__.py
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
import os

db = SQLAlchemy()

def create_app():
    app = Flask(__name__)
    
    # Configurações
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', '00974655')
    # Atualização para usar PostgreSQL do Render em produção, com fallback para SQLite local
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
        'DATABASE_URL', 
        'sqlite:///facilita.db'
    ).replace('postgres://', 'postgresql://')  # Render usa 'postgres://', SQLAlchemy espera 'postgresql://'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Inicializar extensões
    db.init_app(app)
    
    # Criar tabelas no banco
    with app.app_context():
        db.create_all()
    
    # Registrar rotas
    from .routes import init_routes
    from .queue_routes import init_queue_routes
    init_routes(app)
    init_queue_routes(app)
    
    return app