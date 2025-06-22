import os
import re
import logging
from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
from cachetools import TTLCache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# --- Configurações ---
# A URL base da API externa de Angola.
# Usa a variável de ambiente 'ANGOLA_API_BASE_URL' se definida,
# caso contrário, assume 'https://angolaapi.onrender.com' (útil para desenvolvimento local).
ANGOLA_API_BASE_URL = os.environ.get('ANGOLA_API_BASE_URL', 'https://angolaapi.onrender.com')

# Tempo de vida do cache em segundos (1 hora)
CACHE_TTL = 3600
# Tamanho máximo do cache (número de entradas)
CACHE_MAXSIZE = 1000

# Expressão regular para validar o formato do BI angolano.
# Este padrão espera 9 dígitos, seguido por 2 letras maiúsculas, e depois 3 dígitos.
# Exemplo: 006151112LA041
BI_REGEX = re.compile(r'^\d{9}[A-Z]{2}\d{3}$')

# --- Mensagens de Resposta ---
MSG_INVALID_BI_FORMAT = "Formato do BI inválido. O BI deve seguir o padrão: 9 dígitos, 2 letras (maiúsculas), 3 dígitos (ex: 006151112LA041)."
MSG_EXTERNAL_API_ERROR = "Erro ao validar BI na API externa. Por favor, tente novamente mais tarde."
MSG_CONNECTION_ERROR = "Erro de conexão ou requisição com a API externa: {}"
MSG_INTERNAL_SERVER_ERROR = "Erro interno do servidor. Por favor, contacte o suporte: {}"
MSG_BI_VALID = "Este é um número de BI angolano válido."
MSG_BI_INVALID_EXTERNAL = "Número de BI inválido de acordo com a API externa."

# --- Inicialização do Flask App ---
app = Flask(__name__)
# Habilita o CORS para permitir requisições de diferentes origens (importante para frontends)
CORS(app)

# --- Configuração de Logging ---
# Configura o sistema de log para exibir mensagens INFO e superiores no console.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Configuração de Cache ---
# Cria um cache TTL (Time-To-Live) que armazena até CACHE_MAXSIZE itens
# e remove-os após CACHE_TTL segundos.
cache = TTLCache(maxsize=CACHE_MAXSIZE, ttl=CACHE_TTL)

# --- Configuração de Rate Limiting ---
# Limita o número de requisições que um IP pode fazer.
# O limite padrão é de 100 requisições por dia e 10 por minuto para todo o app.
limiter = Limiter(
    app=app,
    key_func=get_remote_address, # Usa o endereço IP remoto para identificar o cliente
    default_limits=["100 per day", "10 per minute"]
)

# --- Rota de Validação de BI ---
@app.route('/validate-bi/<bi_number>', methods=['GET'])
# Limite específico para esta rota: 10 requisições por minuto por IP.
# Este limite se aplica *além* do limite padrão.
@limiter.limit("10 per minute")
def validate_bi(bi_number):
    """
    Endpoint para validar um número de Bilhete de Identidade (BI) angolano.

    A validação segue os seguintes passos:
    1. Valida o formato do BI usando uma expressão regular.
    2. Verifica se o BI já está em cache.
    3. Se não estiver em cache, faz uma requisição para uma API externa de validação.
    4. Armazena o resultado da API externa em cache e retorna.
    5. Lida com erros da API externa e erros de conexão.
    """
    logger.info(f"Requisição recebida para validar BI: {bi_number}")

    # 1. Validação do formato do BI antes de qualquer coisa
    if not BI_REGEX.match(bi_number):
        logger.warning(f"Formato de BI inválido detectado: '{bi_number}'. Retornando erro 400.")
        return jsonify({
            'success': False,
            'message': MSG_INVALID_BI_FORMAT
        }), 400

    # 2. Verifica no cache primeiro para evitar chamadas redundantes à API externa
    if bi_number in cache:
        logger.info(f"BI '{bi_number}' encontrado no cache. Retornando resultado em cache.")
        return jsonify(cache[bi_number]), 200 # Assumimos que o cache armazena um resultado de sucesso

    try:
        # 3. Se não estiver em cache, o backend faz a requisição para a API externa
        external_api_url = f'{ANGOLA_API_BASE_URL}/api/v1/validate/bi/{bi_number}'
        logger.info(f"Chamando API externa: {external_api_url}")
        response = requests.get(external_api_url, timeout=10) # Adiciona um timeout para evitar requisições presas

        # Verifica o status da resposta da API externa
        if response.status_code == 200:
            result = response.json()
            # 4. Armazena o resultado no cache antes de retornar
            cache[bi_number] = result
            logger.info(f"BI '{bi_number}' validado com sucesso pela API externa e armazenado em cache.")
            return jsonify(result), 200
        else:
            # Tenta extrair a mensagem de erro da resposta da API externa
            try:
                error_data = response.json()
                # Prioriza a mensagem da API externa, se disponível, senão usa uma mensagem genérica
                message = error_data.get('message', MSG_EXTERNAL_API_ERROR)
            except ValueError:
                # Se a resposta não for JSON, informa o erro com o status code
                message = f'{MSG_EXTERNAL_API_ERROR} Status: {response.status_code}'

            logger.error(f"Erro da API externa para BI '{bi_number}'. Status: {response.status_code}, Mensagem: '{message}'")
            return jsonify({
                'success': False,
                'message': message
            }), response.status_code # Retorna o status code original da API externa

    except requests.exceptions.Timeout:
        # Erro específico para timeout de requisição à API externa
        logger.error(f"Timeout ao conectar com a API externa para BI '{bi_number}'.")
        return jsonify({
            'success': False,
            'message': MSG_CONNECTION_ERROR.format("A conexão com a API de validação excedeu o tempo limite.")
        }), 504 # Gateway Timeout

    except requests.exceptions.RequestException as e:
        # Captura erros de conexão, DNS, etc. com a API externa
        logger.error(f"Erro de conexão/requisição com a API externa para BI '{bi_number}': {str(e)}")
        return jsonify({
            'success': False,
            'message': MSG_CONNECTION_ERROR.format(str(e))
        }), 500 # Erro Interno do Servidor (problema com o serviço de terceiros)

    except Exception as e:
        # Captura outros erros inesperados dentro da sua aplicação
        logger.critical(f"Erro interno inesperado no servidor para BI '{bi_number}': {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': MSG_INTERNAL_SERVER_ERROR.format(str(e))
        }), 500 # Erro Interno do Servidor

# --- Execução do App ---
if __name__ == '__main__':
    # Quando executado diretamente, o servidor Flask é iniciado.
    # debug=True é útil para desenvolvimento (recarga automática, depuração detalhada).
    # Para produção, defina FLASK_ENV=production ou retire debug=True.
    app.run(debug=os.environ.get('FLASK_DEBUG', 'False') == 'True', host='0.0.0.0', port=5000)