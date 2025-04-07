# app/__init__.py
from flask import Flask

def create_app():
    app = Flask(__name__)
    
    # Configurações básicas
    app.config['SECRET_KEY'] = 'sua-chave-secreta-aqui'  # Substitua por uma chave segura
    
    # Registrar rotas
    from .routes import init_routes
    init_routes(app)
    
    return app