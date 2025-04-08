import jwt
from flask import request, jsonify, current_app
from functools import wraps
import os
from datetime import datetime
import logging

# Configuração de logging
logger = logging.getLogger(__name__)

def setup_logging():
    if not logger.handlers:
        log_handler = logging.handlers.RotatingFileHandler(
            'auth.log', maxBytes=1024*1024, backupCount=10
        )
        log_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        log_handler.setLevel(logging.INFO)
        logger.addHandler(log_handler)
        logger.setLevel(logging.INFO)

setup_logging()

# Decorador para autenticação básica
def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            logger.warning("Tentativa de acesso sem token")
            return jsonify({'error': 'Token de autenticação necessário'}), 401
        
        try:
            # Remove "Bearer " do token, se presente
            token = token.replace('Bearer ', '')
            # Decodifica o token com a chave secreta do ambiente
            secret = os.getenv('JWT_SECRET', '974655')  # Fallback para desenvolvimento
            payload = jwt.decode(token, secret, algorithms=['HS256'])
            
            # Extrai informações do usuário do payload
            request.user_id = payload.get('user_id')
            request.user_nome = payload.get('nome', 'Usuário Anônimo')
            request.user_telefone = payload.get('telefone')
            request.user_tipo = payload.get('tipo', 'normal')  # normal ou gestor
            
            if not request.user_id:
                logger.error("Token sem user_id")
                return jsonify({'error': 'Token inválido: user_id ausente'}), 401
            
            logger.info(f"Usuário autenticado: {request.user_id} ({request.user_nome})")
            
        except jwt.ExpiredSignatureError:
            logger.warning("Token expirado")
            return jsonify({'error': 'Token expirado'}), 401
        except jwt.InvalidTokenError as e:
            logger.error(f"Token inválido: {str(e)}")
            return jsonify({'error': 'Token inválido'}), 401
        except Exception as e:
            logger.error(f"Erro inesperado na autenticação: {str(e)}")
            return jsonify({'error': 'Erro interno na autenticação'}), 500
        
        return f(*args, **kwargs)
    return decorated

# Decorador para restringir acesso a gestores
def require_gestor(f):
    @wraps(f)
    @require_auth
    def decorated(*args, **kwargs):
        if request.user_tipo != 'gestor':
            logger.warning(f"Tentativa de acesso não autorizado por {request.user_id} ({request.user_nome})")
            return jsonify({'error': 'Acesso restrito a gestores'}), 403
        
        logger.info(f"Acesso de gestor autorizado: {request.user_id} ({request.user_nome})")
        return f(*args, **kwargs)
    return decorated

# Função para gerar um token de teste (apenas para desenvolvimento)
def generate_test_token(user_id, nome, telefone, tipo='normal', expiration_minutes=60):
    secret = os.getenv('JWT_SECRET', '974655')
    payload = {
        'user_id': user_id,
        'nome': nome,
        'telefone': telefone,
        'tipo': tipo,
        'exp': datetime.utcnow() + timedelta(minutes=expiration_minutes),
        'iat': datetime.utcnow()
    }
    token = jwt.encode(payload, secret, algorithm='HS256')
    logger.info(f"Token de teste gerado para {user_id} ({nome})")
    return token

# Função para validar token manualmente (útil para debugging ou testes)
def validate_token(token):
    try:
        token = token.replace('Bearer ', '')
        secret = os.getenv('JWT_SECRET', '974655')
        payload = jwt.decode(token, secret, algorithms=['HS256'])
        logger.info(f"Token validado com sucesso: user_id={payload.get('user_id')}")
        return {
            'valid': True,
            'payload': payload,
            'user_id': payload.get('user_id'),
            'nome': payload.get('nome'),
            'telefone': payload.get('telefone'),
            'tipo': payload.get('tipo', 'normal')
        }
    except jwt.ExpiredSignatureError:
        logger.warning("Validação falhou: Token expirado")
        return {'valid': False, 'error': 'Token expirado'}
    except jwt.InvalidTokenError as e:
        logger.error(f"Validação falhou: Token inválido - {str(e)}")
        return {'valid': False, 'error': 'Token inválido'}
    except Exception as e:
        logger.error(f"Erro na validação: {str(e)}")
        return {'valid': False, 'error': 'Erro interno'}

# Middleware para logar todas as requisições autenticadas
def log_request_middleware(app):
    @app.before_request
    def log_request_info():
        if hasattr(request, 'user_id'):
            logger.info(
                f"Requisição autenticada: {request.method} {request.path} "
                f"por {request.user_id} ({request.user_nome})"
            )