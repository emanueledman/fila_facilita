from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
from cachetools import TTLCache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os # Importe o módulo os

app = Flask(__name__)
CORS(app)

# Configuração de cache (mantém por 1 hora)
cache = TTLCache(maxsize=1000, ttl=3600)

# Rate limiting (100 requisições por dia por IP)
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["100 per day"]
)

# Use uma variável de ambiente para a URL da API externa
ANGOLA_API_BASE_URL = os.environ.get('ANGOLA_API_BASE_URL', 'https://angolaapi.onrender.com')

@app.route('/validate-bi/<bi_number>')
@limiter.limit("10 per minute")  # Limite adicional para esta rota
def validate_bi(bi_number):
    # Verifica no cache primeiro
    if bi_number in cache:
        return jsonify(cache[bi_number])

    try:
        # Usa a variável de ambiente para a URL
        response = requests.get(f'{ANGOLA_API_BASE_URL}/api/v1/validate/bi/{bi_number}')

        if response.status_code == 200:
            result = response.json()
            # Armazena no cache
            cache[bi_number] = result
            return jsonify(result), 200
        else:
            # Retorna o status code e a mensagem da API externa se possível
            try:
                error_data = response.json()
                message = error_data.get('message', 'Erro ao validar BI na API externa.')
            except ValueError:
                message = f'Erro ao validar BI na API externa. Status: {response.status_code}'

            return jsonify({
                'success': False,
                'message': message
            }), response.status_code # Retorna o status code original da API externa

    except requests.exceptions.RequestException as e: # Captura exceções específicas de requisições
        return jsonify({
            'success': False,
            'message': f'Erro de conexão com a API externa: {str(e)}'
        }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

if __name__ == '__main__':
    # No ambiente de produção do Render, o Render define a porta
    # Para desenvolvimento local, pode continuar com 5000
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host='0.0.0.0', port=port)