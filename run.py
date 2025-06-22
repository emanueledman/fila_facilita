from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
from cachetools import TTLCache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os

app = Flask(__name__)
CORS(app)

# Configuração de cache (mantém por 1 hora)
cache = TTLCache(maxsize=1000, ttl=3600)

# Rate limiting (100 requisições por dia por IP como padrão, ajustável)
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["100 per day"]
)

# Use uma variável de ambiente para a URL da API externa
ANGOLA_API_BASE_URL = os.environ.get('ANGOLA_API_BASE_URL', 'https://angolaapi.onrender.com')

@app.route('/validate-bi/<bi_number>')
@limiter.limit("10 per minute")
def validate_bi(bi_number):
    # Verifica no cache primeiro
    if bi_number in cache:
        return jsonify(cache[bi_number])
    
    try:
        # O backend Flask faz a requisição para a API externa
        response = requests.get(f'{ANGOLA_API_BASE_URL}/api/v1/validate/bi/{bi_number}')
        
        if response.status_code == 200:
            result = response.json()
            # Armazena no cache
            cache[bi_number] = result
            return jsonify(result), 200
        else:
            # Tenta pegar a mensagem de erro da API externa, se disponível
            try:
                error_data = response.json()
                message = error_data.get('message', 'Erro ao validar BI na API externa.')
            except ValueError:
                message = f'Erro ao validar BI na API externa. Status: {response.status_code}'
            
            return jsonify({
                'success': False,  # CORRIGIDO: era 'sucess'
                'message': message
            }), response.status_code
            
    except requests.exceptions.RequestException as e:
        return jsonify({
            'success': False,  # CORRIGIDO: era 'sucess'
            'message': f'Erro de conexão ou requisição com a API externa: {str(e)}'
        }), 500
        
    except Exception as e:
        return jsonify({
            'success': False,  # CORRIGIDO: era 'sucess'
            'message': f'Erro interno do servidor: {str(e)}'
        }), 500

@app.route('/health')
def health():
    return jsonify({'status': 'healthy'}), 200

if __name__ == '__main__':
    app.run(debug=True)