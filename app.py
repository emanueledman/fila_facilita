from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager, create_access_token
from flask_socketio import SocketIO, emit
import traceback
import os

# Crie a aplicação Flask
app = Flask(__name__)

# Configurações básicas
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///test.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'sua_chave_secreta')

# Inicialize as extensões
db = SQLAlchemy(app)
jwt = JWTManager(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Modelo de Usuário
class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha = db.Column(db.String(120), nullable=False)
    tipo = db.Column(db.String(50), default='normal')

    def __repr__(self):
        return f'<Usuario {self.email}>'

# Crie as tabelas
with app.app_context():
    db.create_all()

# Rota de login
@app.route('/api/auth/login', methods=['POST'])
def login():
    try:
        dados = request.get_json()
        email = dados.get('email')
        senha = dados.get('senha')

        if not email or not senha:
            print("Erro: Email ou senha não fornecidos")
            return jsonify({"erro": "Email e senha são obrigatórios"}), 400

        print(f"Tentando login com email: {email}")
        usuario = Usuario.query.filter_by(email=email).first()

        if not usuario or usuario.senha != senha:
            print(f"Credenciais inválidas para {email}")
            return jsonify({"erro": "Credenciais inválidas"}), 401

        token = create_access_token(identity={'id': usuario.id, 'tipo': usuario.tipo})
        print(f"Login bem-sucedido para {email}")
        return jsonify({
            "access_token": token,
            "id": usuario.id,
            "tipo": usuario.tipo
        }), 200

    except Exception as e:
        print("Erro interno no servidor:")
        traceback.print_exc()
        return jsonify({"erro": "Erro interno no servidor"}), 500

# Evento SocketIO
@socketio.on('connect_fila')
def handle_connect(data):
    print("Cliente conectado ao SocketIO:", data)
    emit('fila_atualizada', {"mensagem": "Conexão estabelecida"}, broadcast=True)

# Adicione usuário de teste (apenas local)
def adicionar_usuario_teste():
    with app.app_context():
        usuario = Usuario.query.filter_by(email='edmannews5@gmail.com').first()
        if not usuario:
            usuario = Usuario(email='edmannews5@gmail.com', senha='123456', tipo='normal')
            db.session.add(usuario)
            db.session.commit()
            print("Usuário de teste criado com ID:", usuario.id)

if __name__ == '__main__':
    adicionar_usuario_teste()
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)