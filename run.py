
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
    # Normalize BI number
    bi_number = bi_number.strip().upper()
    
    # Verificação básica do formato do BI angolano
    if not re.match(r'^\d{9}[A-Z]{2}\d{3}$', bi_number):
        failure_cache[bi_number] = {
            'success': False,
            'message': 'Formato de BI inválido. Use: 123456789LA042'
        }
        return jsonify(failure_cache[bi_number]), 400

    try:
        # Simulação de validação - substitua por sua lógica real
        # Esta é apenas uma verificação de exemplo
        is_valid = True  # Substitua por sua lógica de validação real
        
        if is_valid:
            result = {
                'success': True,
                'message': 'BI válido',
                'data': {
                    'number': bi_number,
                    'valid': True
                }
            }
            success_cache[bi_number] = result
            return jsonify(result), 200  # Sempre retorne 200 para BI válido
        else:
            result = {
                'success': False,
                'message': 'Número de BI não encontrado'
            }
            failure_cache[bi_number] = result
            return jsonify(result), 404

    except Exception as e:
        logger.error(f"Error validating BI {bi_number}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Erro interno: {str(e)}'
        }), 500

if __name__ == '__main__':
    app.run(debug=True)
