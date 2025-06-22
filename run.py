from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
from cachetools import TTLCache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
import logging
import json

app = Flask(__name__)
CORS(app)

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuração de cache (mantém por 1 hora)
cache = TTLCache(maxsize=1000, ttl=3600)

# Rate limiting
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["100 per day"]
)

ANGOLA_API_BASE_URL = os.environ.get('ANGOLA_API_BASE_URL', 'https://angolaapi.onrender.com')

def parse_malformed_response(response_text):
    """Tenta extrair informações de uma resposta JSON malformada"""
    try:
        # Tenta fazer parse normal primeiro
        return json.loads(response_text)
    except json.JSONDecodeError:
        logger.warning(f"Resposta JSON malformada recebida: {response_text}")
        
        # Tenta extrair informações da resposta malformada
        if 'sucesstruemessage' in response_text.lower():
            # Procura por padrões conhecidos
            if 'valid identity card' in response_text.lower():
                return {
                    'success': True,
                    'message': 'This is an Angola valid identity card'
                }
            elif 'invalid' in response_text.lower():
                return {
                    'success': False,
                    'message': 'Invalid identity card'
                }
        
        # Se não conseguir extrair, retorna erro
        return {
            'success': False,
            'message': 'Resposta da API externa inválida'
        }

@app.route('/validate-bi/<bi_number>')
@limiter.limit("10 per minute")
def validate_bi(bi_number):
    # Log da requisição
    logger.info(f"Validando BI: {bi_number}")
    
    # Verifica no cache primeiro
    if bi_number in cache:
        logger.info(f"BI {bi_number} encontrado no cache")
        return jsonify(cache[bi_number])
    
    try:
        # Faz a requisição para a API externa
        api_url = f'{ANGOLA_API_BASE_URL}/api/v1/validate/bi/{bi_number}'
        logger.info(f"Fazendo requisição para: {api_url}")
        
        response = requests.get(api_url, timeout=30)
        logger.info(f"Status da resposta: {response.status_code}")
        logger.info(f"Resposta bruta: {response.text}")
        
        if response.status_code == 200:
            # Tenta fazer parse da resposta
            try:
                result = response.json()
                logger.info(f"Resposta parsed com sucesso: {result}")
            except json.JSONDecodeError:
                # Se falhar, usa o parser customizado
                logger.warning("Falhou ao fazer parse JSON, usando parser customizado")
                result = parse_malformed_response(response.text)
            
            # Normaliza a resposta (corrige 'sucess' para 'success')
            normalized_result = {
                'success': result.get('sucess', result.get('success', False)),
                'message': result.get('message', 'BI processado')
            }
            
            logger.info(f"Resultado normalizado: {normalized_result}")
            
            # Armazena no cache
            cache[bi_number] = normalized_result
            return jsonify(normalized_result), 200
            
        elif response.status_code == 503:
            # Serviço indisponível
            logger.error(f"API externa indisponível (503) para BI: {bi_number}")
            return jsonify({
                'success': False,
                'message': 'Serviço de validação temporariamente indisponível. Tente novamente em alguns minutos.'
            }), 503
            
        else:
            # Outros erros
            logger.error(f"Erro na API externa: Status {response.status_code}, Resposta: {response.text}")
            
            try:
                error_data = response.json()
                message = error_data.get('message', f'Erro na API externa (Status: {response.status_code})')
            except json.JSONDecodeError:
                message = f'Erro na API externa (Status: {response.status_code})'
            
            return jsonify({
                'success': False,
                'message': message
            }), response.status_code
            
    except requests.exceptions.Timeout:
        logger.error(f"Timeout na validação do BI: {bi_number}")
        return jsonify({
            'success': False,
            'message': 'Timeout na validação. Tente novamente.'
        }), 504
        
    except requests.exceptions.ConnectionError:
        logger.error(f"Erro de conexão na validação do BI: {bi_number}")
        return jsonify({
            'success': False,
            'message': 'Erro de conexão com o serviço de validação.'
        }), 503
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro de requisição na validação do BI {bi_number}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Erro na requisição: {str(e)}'
        }), 500
        
    except Exception as e:
        logger.error(f"Erro interno na validação do BI {bi_number}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Erro interno do servidor: {str(e)}'
        }), 500

@app.route('/health')
def health():
    return jsonify({'status': 'healthy'}), 200

@app.route('/cache-stats')
def cache_stats():
    """Endpoint para monitorar o cache"""
    return jsonify({
        'cache_size': len(cache),
        'max_size': cache.maxsize,
        'ttl': cache.ttl
    }), 200

if __name__ == '__main__':
    app.run(debug=True)