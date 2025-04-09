import logging
from flask import app, request, jsonify, current_app
from sqlalchemy.exc import SQLAlchemyError  # Adicionado para capturar erros de banco
from ..auth import require_auth, require_gestor
from ..services.queue_service import QueueService
from datetime import datetime, time
from .. import db

# Configuração de logging
logger = logging.getLogger(__name__)

def setup_logging():
    if not logger.handlers:
        log_handler = logging.handlers.RotatingFileHandler(
            'queue_routes.log', maxBytes=1024*1024, backupCount=10
        )
        log_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        log_handler.setLevel(logging.INFO)
        logger.addHandler(log_handler)
        logger.setLevel(logging.INFO)

setup_logging()

def init_queue_routes(app):
    """Registra as rotas relacionadas a filas no aplicativo Flask."""

    @app.route('/api/queues', methods=['GET'])
    def list_queues():
        """Lista todas as filas disponíveis."""
        try:
            # Usamos Queue diretamente do modelo, já que db está disponível
            from ..models import Queue
            queues = db.session.query(Queue).all()
            now = datetime.now().time()
            response = [{
                'id': q.id,
                'service': q.service,
                'sector': q.sector,
                'department': q.department,
                'institution': q.institution,
                'open_time': q.open_time.strftime('%H:%M'),
                'daily_limit': q.daily_limit,
                'active_tickets': q.active_tickets,
                'status': ('Aberto' if now >= q.open_time and q.active_tickets < q.daily_limit else
                          'Fechado' if now < q.open_time else 'Lotado')
            } for q in queues]
            
            logger.info(f"Listagem de filas retornada com sucesso: {len(queues)} filas")
            return jsonify(response), 200
        except Exception as e:
            logger.error(f"Erro ao listar filas: {str(e)}")
            return jsonify({'error': 'Erro interno ao listar filas'}), 500

    @app.route('/api/queue/<service>/ticket', methods=['POST'])
    @require_auth
    def get_ticket(service):
        """Emite um novo ticket para a fila especificada."""
        try:
            app.logger.info(f"Tentando emitir ticket para usuário {request.user_id} na fila {service}")
            data = request.get_json() or {}
            app.logger.info(f"Dados recebidos: {data}")
            priority = data.get('priority', 0)
            is_physical = data.get('is_physical', False)
            
            app.logger.info(f"Chamando QueueService.add_to_queue com serviço: {service}, usuário: {request.user_id}")
            ticket = QueueService.add_to_queue(service, request.user_id, priority, is_physical)
            wait_time = QueueService.calculate_wait_time(ticket.queue_id, ticket.ticket_number, ticket.priority)
            
            response = {
                'message': 'Senha emitida com sucesso',
                'ticket': {
                    'id': ticket.id,
                    'number': ticket.ticket_number,
                    'qr_code': ticket.qr_code,
                    'wait_time': f'{wait_time} minutos',
                    'receipt': ticket.receipt_data,
                    'priority': ticket.priority,
                    'is_physical': ticket.is_physical,
                    'expires_at': ticket.expires_at.isoformat() if ticket.expires_at else None
                }
            }
            
            app.logger.info(f"Ticket {ticket.id} emitido com sucesso para {request.user_id}")
            return jsonify(response), 201
        
        except ValueError as e:
            app.logger.warning(f"Falha ao emitir ticket para {request.user_id} na fila {service}: {str(e)}")
            return jsonify({'error': str(e)}), 400
        
        except SQLAlchemyError as e:
            app.logger.error(f"Erro no banco de dados ao emitir ticket: {str(e)}", exc_info=True)
            return jsonify({'error': 'Erro no banco de dados', 'details': str(e)}), 500
        
        except Exception as e:
            app.logger.error(f"Erro interno ao emitir ticket (não relacionado ao banco): {str(e)}", exc_info=True)
            return jsonify({'error': 'Erro interno no servidor', 'details': str(e)}), 500

    @app.route('/api/ticket/<ticket_id>', methods=['GET'])
    @require_auth
    def ticket_status(ticket_id):
        """Retorna o status de um ticket específico."""
        try:
            ticket = QueueService.Ticket.query.get_or_404(ticket_id)
            if ticket.user_id != request.user_id and request.user_tipo != 'gestor':
                logger.warning(f"Tentativa não autorizada de acesso ao ticket {ticket_id} por {request.user_id}")
                return jsonify({'error': 'Não autorizado'}), 403
            
            wait_time = QueueService.calculate_wait_time(ticket.queue_id, ticket.ticket_number, ticket.priority)
            response = {
                'service': ticket.queue.service,
                'ticket_number': ticket.ticket_number,
                'qr_code': ticket.qr_code,
                'status': ticket.status,
                'position': max(0, ticket.ticket_number - ticket.queue.current_ticket),
                'wait_time': f'{wait_time} minutos',
                'priority': ticket.priority,
                'is_physical': ticket.is_physical,
                'issued_at': ticket.issued_at.isoformat(),
                'attended_at': ticket.attended_at.isoformat() if ticket.attended_at else None,
                'expires_at': ticket.expires_at.isoformat() if ticket.expires_at else None
            }
            
            logger.info(f"Status do ticket {ticket_id} retornado para {request.user_id}")
            return jsonify(response), 200
        except Exception as e:
            logger.error(f"Erro ao verificar status do ticket {ticket_id}: {str(e)}")
            return jsonify({'error': 'Erro interno ao verificar status'}), 500

    @app.route('/api/queue/<service>/call', methods=['POST'])
    @require_gestor
    def call_next_ticket(service):
        """Chama o próximo ticket da fila (apenas gestores)."""
        try:
            ticket = QueueService.call_next(service)
            response = {
                'message': f'Senha #{ticket.ticket_number} chamada',
                'ticket_id': ticket.id,
                'remaining': ticket.queue.active_tickets
            }
            
            logger.info(f"Ticket {ticket.id} chamado na fila {service} por {request.user_id}")
            return jsonify(response), 200
        except ValueError as e:
            logger.warning(f"Falha ao chamar próximo ticket na fila {service}: {str(e)}")
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.error(f"Erro interno ao chamar próximo ticket: {str(e)}")
            return jsonify({'error': 'Erro interno ao chamar ticket'}), 500

    @app.route('/api/ticket/trade/offer/<ticket_id>', methods=['POST'])
    @require_auth
    def offer_trade_ticket(ticket_id):
        """Oferece um ticket para troca."""
        try:
            ticket = QueueService.offer_trade_ticket(ticket_id, request.user_id)
            response = {
                'message': 'Senha oferecida para troca',
                'ticket_id': ticket.id,
                'ticket_number': ticket.ticket_number
            }
            
            logger.info(f"Ticket {ticket_id} oferecido para troca por {request.user_id}")
            return jsonify(response), 200
        except ValueError as e:
            logger.warning(f"Falha ao oferecer ticket {ticket_id} para troca: {str(e)}")
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.error(f"Erro interno ao oferecer ticket para troca: {str(e)}")
            return jsonify({'error': 'Erro interno ao oferecer troca'}), 500

    @app.route('/api/ticket/trade/<ticket_to_id>', methods=['POST'])
    @require_auth
    def trade_ticket(ticket_to_id):
        """Realiza a troca de um ticket por outro."""
        try:
            data = request.get_json() or {}
            ticket_from_id = data.get('ticket_from_id')
            if not ticket_from_id:
                logger.warning(f"Ticket de origem não fornecido para troca com {ticket_to_id}")
                return jsonify({'error': 'Ticket de origem necessário'}), 400
            
            result = QueueService.trade_tickets(ticket_from_id, ticket_to_id, request.user_id)
            response = {
                'message': 'Troca realizada com sucesso',
                'tickets': {
                    'from': {'id': result['ticket_from'].id, 'number': result['ticket_from'].ticket_number},
                    'to': {'id': result['ticket_to'].id, 'number': result['ticket_to'].ticket_number}
                }
            }
            
            logger.info(f"Troca realizada entre tickets {ticket_from_id} e {ticket_to_id} por {request.user_id}")
            return jsonify(response), 200
        except ValueError as e:
            logger.warning(f"Falha ao realizar troca entre {ticket_from_id} e {ticket_to_id}: {str(e)}")
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.error(f"Erro interno ao realizar troca: {str(e)}")
            return jsonify({'error': 'Erro interno ao realizar troca'}), 500

    @app.route('/api/queue/<service>/status', methods=['GET'])
    @require_auth
    def queue_status(service):
        """Retorna o status atual da fila para usuários."""
        try:
            queue = QueueService.Queue.query.filter_by(service=service).first()
            if not queue:
                logger.warning(f"Fila não encontrada: {service}")
                return jsonify({'error': 'Fila não encontrada'}), 404
            
            user_ticket = QueueService.Ticket.query.filter_by(
                queue_id=queue.id, user_id=request.user_id, status='pending'
            ).first()
            
            response = {
                'service': queue.service,
                'active_tickets': queue.active_tickets,
                'current_ticket': queue.current_ticket,
                'daily_limit': queue.daily_limit,
                'user_ticket': {
                    'number': user_ticket.ticket_number,
                    'position': max(0, user_ticket.ticket_number - queue.current_ticket),
                    'wait_time': f'{QueueService.calculate_wait_time(queue.id, user_ticket.ticket_number, user_ticket.priority)} minutos'
                } if user_ticket else None
            }
            
            logger.info(f"Status da fila {service} retornado para {request.user_id}")
            return jsonify(response), 200
        except Exception as e:
            logger.error(f"Erro ao verificar status da fila {service}: {str(e)}")
            return jsonify({'error': 'Erro interno ao verificar status'}), 500