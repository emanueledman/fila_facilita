import logging
from flask import request, jsonify, current_app
from ..auth import require_auth, require_gestor
from ..services.slot_service import SlotService
from datetime import datetime
from ..models import Servico, SlotAgendamento

logger = logging.getLogger(__name__)

def setup_logging():
    if not logger.handlers:
        log_handler = logging.handlers.RotatingFileHandler(
            'slot_routes.log', maxBytes=1024*1024, backupCount=10
        )
        log_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        log_handler.setLevel(logging.INFO)
        logger.addHandler(log_handler)
        logger.setLevel(logging.INFO)

setup_logging()

def init_slot_routes(app):
    @app.route('/api/servico/<service>/slots', methods=['GET'])
    @require_auth
    def list_slots(service):
        try:
            servico = Servico.query.filter_by(nome=service).first()
            if not servico:
                logger.warning(f"Serviço não encontrado: {service}")
                return jsonify({'error': 'Serviço não encontrado'}), 404
            
            slots = SlotAgendamento.query.filter_by(servico_id=servico.id, status="aberto").all()
            response = [{
                'id': s.id,
                'data_horario': s.data_horario.isoformat(),
                'capacidade_maxima': s.capacidade_maxima,
                'capacidade_atual': s.capacidade_atual,
                'available_spots': s.capacidade_maxima - s.capacidade_atual
            } for s in slots]
            
            logger.info(f"Listagem de slots retornada para {service}: {len(slots)} slots")
            return jsonify(response), 200
        except Exception as e:
            logger.error(f"Erro ao listar slots para {service}: {str(e)}")
            return jsonify({'error': 'Erro interno ao listar slots'}), 500

    @app.route('/api/servico/<service>/slot', methods=['POST'])
    @require_gestor
    def create_slot(service):
        try:
            data = request.get_json() or {}
            data_horario = datetime.fromisoformat(data.get('data_horario'))
            capacidade_maxima = data.get('capacidade_maxima')
            
            if not data_horario or not capacidade_maxima:
                logger.warning(f"Dados incompletos para criar slot em {service}")
                return jsonify({'error': 'Data/hora e capacidade máxima são obrigatórios'}), 400
            
            slot = SlotService.create_slot(service, data_horario, capacidade_maxima, request.user_id)
            response = {
                'message': 'Slot criado com sucesso',
                'slot': {
                    'id': slot.id,
                    'data_horario': slot.data_horario.isoformat(),
                    'capacidade_maxima': slot.capacidade_maxima
                }
            }
            
            logger.info(f"Slot {slot.id} criado para {service} por {request.user_id}")
            return jsonify(response), 201
        except ValueError as e:
            logger.warning(f"Falha ao criar slot para {service}: {str(e)}")
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.error(f"Erro interno ao criar slot: {str(e)}")
            return jsonify({'error': 'Erro interno ao criar slot'}), 500

    @app.route('/api/slot/<slot_id>/reservar', methods=['POST'])
    @require_auth
    def reserve_slot(slot_id):
        try:
            slot = SlotService.reserve_slot(slot_id, request.user_id)
            response = {
                'message': 'Slot reservado com sucesso',
                'slot': {
                    'id': slot.id,
                    'service': slot.servico.nome,
                    'data_horario': slot.data_horario.isoformat(),
                    'capacidade_atual': slot.capacidade_atual,
                    'capacidade_maxima': slot.capacidade_maxima
                }
            }
            
            logger.info(f"Slot {slot_id} reservado por {request.user_id}")
            return jsonify(response), 201
        except ValueError as e:
            logger.warning(f"Falha ao reservar slot {slot_id}: {str(e)}")
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.error(f"Erro interno ao reservar slot {slot_id}: {str(e)}")
            return jsonify({'error': 'Erro interno ao reservar slot'}), 500

    @app.route('/api/slot/<slot_id>/cancelar', methods=['POST'])
    @require_auth
    def cancel_slot(slot_id):
        try:
            slot = SlotService.cancel_slot_reservation(slot_id, request.user_id)
            response = {
                'message': 'Reserva cancelada com sucesso',
                'slot': {
                    'id': slot.id,
                    'service': slot.servico.nome,
                    'data_horario': slot.data_horario.isoformat(),
                    'capacidade_atual': slot.capacidade_atual
                }
            }
            
            logger.info(f"Reserva do slot {slot_id} cancelada por {request.user_id}")
            return jsonify(response), 200
        except ValueError as e:
            logger.warning(f"Falha ao cancelar slot {slot_id}: {str(e)}")
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.error(f"Erro interno ao cancelar slot {slot_id}: {str(e)}")
            return jsonify({'error': 'Erro interno ao cancelar slot'}), 500

    @app.route('/api/slot/<slot_id>', methods=['GET'])
    @require_auth
    def slot_status(slot_id):
        try:
            slot = SlotAgendamento.query.get_or_404(slot_id)
            if slot.user_id != request.user_id and request.user_tipo != 'gestor':
                logger.warning(f"Tentativa não autorizada de acesso ao slot {slot_id} por {request.user_id}")
                return jsonify({'error': 'Não autorizado'}), 403
            
            response = {
                'service': slot.servico.nome,
                'data_horario': slot.data_horario.isoformat(),
                'capacidade_maxima': slot.capacidade_maxima,
                'capacidade_atual': slot.capacidade_atual,
                'status': slot.status,
                'user_id': slot.user_id,
                'trade_available': slot.trade_available,
                'created_at': slot.created_at.isoformat() if slot.created_at else None
            }
            
            logger.info(f"Status do slot {slot_id} retornado para {request.user_id}")
            return jsonify(response), 200
        except Exception as e:
            logger.error(f"Erro ao verificar status do slot {slot_id}: {str(e)}")
            return jsonify({'error': 'Erro interno ao verificar status'}), 500

    @app.route('/api/slot/trade/offer/<slot_id>', methods=['POST'])
    @require_auth
    def offer_trade_slot(slot_id):
        try:
            slot = SlotService.offer_trade_slot(slot_id, request.user_id)
            response = {
                'message': 'Slot oferecido para troca',
                'slot_id': slot.id,
                'data_horario': slot.data_horario.isoformat()
            }
            
            logger.info(f"Slot {slot_id} oferecido para troca por {request.user_id}")
            return jsonify(response), 200
        except ValueError as e:
            logger.warning(f"Falha ao oferecer slot {slot_id} para troca: {str(e)}")
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.error(f"Erro interno ao oferecer slot para troca: {str(e)}")
            return jsonify({'error': 'Erro interno ao oferecer troca'}), 500

    @app.route('/api/slot/trade/<slot_to_id>', methods=['POST'])
    @require_auth
    def trade_slot(slot_to_id):
        try:
            data = request.get_json() or {}
            slot_from_id = data.get('slot_from_id')
            if not slot_from_id:
                logger.warning(f"Slot de origem não fornecido para troca com {slot_to_id}")
                return jsonify({'error': 'Slot de origem necessário'}), 400
            
            result = SlotService.trade_slots(slot_from_id, slot_to_id, request.user_id)
            response = {
                'message': 'Troca realizada com sucesso',
                'slots': {
                    'from': {'id': result['slot_from'].id, 'data_horario': result['slot_from'].data_horario.isoformat()},
                    'to': {'id': result['slot_to'].id, 'data_horario': result['slot_to'].data_horario.isoformat()}
                }
            }
            
            logger.info(f"Troca realizada entre slots {slot_from_id} e {slot_to_id} por {request.user_id}")
            return jsonify(response), 200
        except ValueError as e:
            logger.warning(f"Falha ao realizar troca entre {slot_from_id} e {slot_to_id}: {str(e)}")
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.error(f"Erro interno ao realizar troca: {str(e)}")
            return jsonify({'error': 'Erro interno ao realizar troca'}), 500

    @app.route('/api/servico/<service>/slot/status', methods=['GET'])
    @require_auth
    def service_slot_status(service):
        try:
            servico = Servico.query.filter_by(nome=service).first()
            if not servico:
                logger.warning(f"Serviço não encontrado: {service}")
                return jsonify({'error': 'Serviço não encontrado'}), 404
            
            user_slot = SlotAgendamento.query.filter_by(
                servico_id=servico.id, user_id=request.user_id, status='reservado'
            ).first()
            
            response = {
                'service': service,
                'total_slots': SlotAgendamento.query.filter_by(servico_id=servico.id).count(),
                'open_slots': SlotAgendamento.query.filter_by(servico_id=servico.id, status='aberto').count(),
                'user_slot': {
                    'id': user_slot.id,
                    'data_horario': user_slot.data_horario.isoformat(),
                    'status': user_slot.status
                } if user_slot else None
            }
            
            logger.info(f"Status dos slots de {service} retornado para {request.user_id}")
            return jsonify(response), 200
        except Exception as e:
            logger.error(f"Erro ao verificar status dos slots de {service}: {str(e)}")
            return jsonify({'error': 'Erro interno ao verificar status'}), 500