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

# Rate limiting (100 requisições por dia por IP como padrão, ajustável)
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["100 per day"] # Limite padrão para todas as rotas
)

# Use uma variável de ambiente para a URL da API externa
# Se a variável ANGOLA_API_BASE_URL não estiver definida (ex: local), usa o valor padrão
ANGOLA_API_BASE_URL = os.environ.get('ANGOLA_API_BASE_URL', 'https://angolaapi.onrender.com')

@app.route('/validate-bi/<bi_number>')
@limiter.limit("10 per minute")  # Limite adicional específico para esta rota
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
            except ValueError: # Caso a resposta não seja um JSON válido
                message = f'Erro ao validar BI na API externa. Status: {response.status_code}'

            return jsonify({
                'success': False,
                'message': message
            }), response.status_code # Retorna o status code original da API externa
            
    except requests.exceptions.RequestException as e: # Captura erros de conexão ou requisição
        return jsonify({
            'success': False,
            'message': f'Erro de conexão ou requisição com a API externa: {str(e)}'
        }), 500
    except Exception as e: # Captura outros erros inesperados
        return jsonify({
            'success': False,
            'message': f'Erro interno do servidor: {str(e)}'
        }), 500

if __name__ == '__main__':
    # Este bloco é apenas para desenvolvimento local.
    # No Render, o Gunicorn iniciará o aplicativo.
    port = int(os.environ.get("PORT", 5000)) # Pega a porta do ambiente ou usa 5000
    app.run(debug=True, host='0.0.0.0', port=port)