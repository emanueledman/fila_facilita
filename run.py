
from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
from cachetools import TTLCache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
import logging

app = Flask(__name__)
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration for cache (1 hour TTL for successful validations, 5 minutes for failures)
success_cache = TTLCache(maxsize=1000, ttl=3600)
failure_cache = TTLCache(maxsize=1000, ttl=300)

# Rate limiting (100 requests per day per IP, 10 per minute for BI validation)
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["100 per day"]
)

# External API URL from environment variable
ANGOLA_API_BASE_URL = os.environ.get('ANGOLA_API_BASE_URL', 'https://angolaapi.onrender.com')

@app.route('/validate-bi/<bi_number>')
@limiter.limit("10 per minute")
def validate_bi(bi_number):
    # Normalize BI number (remove spaces, convert to uppercase)
    bi_number = bi_number.strip().upper()

    # Check success cache first
    if bi_number in success_cache:
        logger.info(f"Cache hit for BI {bi_number} (success)")
        return jsonify(success_cache[bi_number]), 200

    # Check failure cache
    if bi_number in failure_cache:
        logger.info(f"Cache hit for BI {bi_number} (failure)")
        return jsonify(failure_cache[bi_number]), 404

    try:
        # Make request to external API
        response = requests.get(f'{ANGOLA_API_BASE_URL}/api/v1/validate/bi/{bi_number}', timeout=5)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success', False):
                # Cache successful validation
                success_cache[bi_number] = result
                logger.info(f"BI {bi_number} validated successfully")
                return jsonify(result), 200
            else:
                # Cache failed validation
                failure_cache[bi_number] = {
                    'success': False,
                    'message': result.get('message', 'Número de BI inválido ou não encontrado')
                }
                logger.warning(f"BI {bi_number} not found: {result.get('message')}")
                return jsonify(failure_cache[bi_number]), 404
        else:
            # Handle non-200 responses from external API
            logger.error(f"External API error for BI {bi_number}: Status {response.status_code}")
            return jsonify({
                'success': False,
                'message': f'Erro ao validar BI. Status: {response.status_code}'
            }), 502

    except requests.exceptions.Timeout:
        logger.error(f"Timeout error for BI {bi_number}")
        return jsonify({
            'success': False,
            'message': 'Erro: Tempo de resposta da API excedido. Tente novamente.'
        }), 504
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error for BI {bi_number}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Erro de conexão com a API externa: {str(e)}'
        }), 503
    except Exception as e:
        logger.error(f"Internal error for BI {bi_number}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Erro interno do servidor: {str(e)}'
        }), 500

if __name__ == '__main__':
    app.run(debug=True)
