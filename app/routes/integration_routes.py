import logging
from flask import request, jsonify, current_app
from ..auth import require_auth, require_gestor
from ..services.integration_service import IntegrationService
from datetime import datetime

# Configuração de logging
logger = logging.getLogger(__name__)

def setup_logging():
    if not logger.handlers:
        log_handler = logging.handlers.RotatingFileHandler(
            'integration_routes.log', maxBytes=1024*1024, backupCount=10
        )
        log_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        log_handler.setLevel(logging.INFO)
        logger.addHandler(log_handler)
        logger.setLevel(logging.INFO)

setup_logging()

def init_integration_routes(app):
    """Registra as rotas de integração no aplicativo Flask."""

    @app.route('/api/queue/<queue_id>/monitor', methods=['GET'])
    @require_gestor
    def monitor_queue(queue_id):
        """Retorna dados de monitoramento de uma fila (apenas gestores)."""
        try:
            data = IntegrationService.monitor_queue(queue_id)
            logger.info(f"Monitoramento da fila {queue_id} retornado para {request.user_id}")
            return jsonify(data), 200
        except ValueError as e:
            logger.warning(f"Falha ao monitorar fila {queue_id}: {str(e)}")
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.error(f"Erro interno ao monitorar fila {queue_id}: {str(e)}")
            return jsonify({'error': 'Erro interno ao monitorar fila'}), 500

    @app.route('/api/servico/<servico_id>/slots/monitor', methods=['GET'])
    @require_gestor
    def monitor_slots(servico_id):
        """Retorna dados de monitoramento dos slots de um serviço (apenas gestores)."""
        try:
            data = IntegrationService.monitor_slots(servico_id)
            logger.info(f"Monitoramento dos slots do serviço {servico_id} retornado para {request.user_id}")
            return jsonify(data), 200
        except ValueError as e:
            logger.warning(f"Falha ao monitorar slots do serviço {servico_id}: {str(e)}")
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.error(f"Erro interno ao monitorar slots do serviço {servico_id}: {str(e)}")
            return jsonify({'error': 'Erro interno ao monitorar slots'}), 500

    @app.route('/api/cleanup', methods=['POST'])
    @require_gestor
    def cleanup_expired():
        """Executa a limpeza de tickets e slots expirados (apenas gestores)."""
        try:
            IntegrationService.cleanup_expired()
            response = {'message': 'Limpeza de itens expirados concluída com sucesso'}
            logger.info(f"Limpeza de itens expirados executada por {request.user_id}")
            return jsonify(response), 200
        except Exception as e:
            logger.error(f"Erro interno ao executar limpeza: {str(e)}")
            return jsonify({'error': 'Erro interno ao executar limpeza'}), 500

    @app.route('/api/report', methods=['POST'])
    @require_gestor
    def generate_report():
        """Gera um relatório estatístico para um período especificado (apenas gestores)."""
        try:
            data = request.get_json() or {}
            start_date = data.get('start_date')
            end_date = data.get('end_date')
            
            if not start_date or not end_date:
                logger.warning(f"Dados incompletos para gerar relatório: {data}")
                return jsonify({'error': 'Data inicial e final são obrigatórias'}), 400
            
            report = IntegrationService.generate_report(start_date, end_date)
            logger.info(f"Relatório gerado para {start_date} a {end_date} por {request.user_id}")
            return jsonify(report), 200
        except ValueError as e:
            logger.warning(f"Falha ao gerar relatório: {str(e)}")
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.error(f"Erro interno ao gerar relatório: {str(e)}")
            return jsonify({'error': 'Erro interno ao gerar relatório'}), 500

    @app.route('/api/trade/offers', methods=['GET'])
    @require_auth
    def get_trade_offers():
        """Lista todas as ofertas de troca de tickets e slots disponíveis."""
        try:
            offers = IntegrationService.get_trade_offers()
            logger.info(f"Ofertas de troca retornadas para {request.user_id}: {len(offers['tickets'])} tickets, {len(offers['slots'])} slots")
            return jsonify(offers), 200
        except Exception as e:
            logger.error(f"Erro ao listar ofertas de troca: {str(e)}")
            return jsonify({'error': 'Erro interno ao listar ofertas de troca'}), 500

    @app.route('/api/feedback', methods=['POST'])
    @require_auth
    def submit_feedback():
        """Permite que usuários enviem feedback sobre tickets ou slots."""
        try:
            data = request.get_json() or {}
            ticket_id = data.get('ticket_id')
            slot_id = data.get('slot_id')
            nota = data.get('nota')
            comentario = data.get('comentario', '')
            
            if not nota or nota not in range(1, 6):
                logger.warning(f"Nota inválida fornecida por {request.user_id}: {nota}")
                return jsonify({'error': 'Nota deve estar entre 1 e 5'}), 400
            
            if not ticket_id and not slot_id:
                logger.warning(f"Feedback sem ticket ou slot especificado por {request.user_id}")
                return jsonify({'error': 'Ticket ou slot deve ser especificado'}), 400
            
            feedback = IntegrationService.Feedback(
                user_id=request.user_id,
                ticket_id=ticket_id,
                slot_id=slot_id,
                nota=nota,
                comentario=comentario
            )
            IntegrationService.db.session.add(feedback)
            IntegrationService.db.session.commit()
            
            response = {
                'message': 'Feedback enviado com sucesso',
                'feedback_id': feedback.id
            }
            logger.info(f"Feedback {feedback.id} enviado por {request.user_id} para ticket {ticket_id} ou slot {slot_id}")
            return jsonify(response), 201
        except Exception as e:
            logger.error(f"Erro ao enviar feedback: {str(e)}")
            return jsonify({'error': 'Erro interno ao enviar feedback'}), 500

    @app.route('/api/system/status', methods=['GET'])
    @require_gestor
    def system_status():
        """Retorna o status geral do sistema (apenas gestores)."""
        try:
            total_queues = IntegrationService.Queue.query.count()
            total_slots = IntegrationService.SlotAgendamento.query.count()
            active_tickets = IntegrationService.Ticket.query.filter_by(status='pending').count()
            reserved_slots = IntegrationService.SlotAgendamento.query.filter_by(status='reservado').count()
            feedback_count = IntegrationService.Feedback.query.count()
            
            response = {
                'total_queues': total_queues,
                'total_slots': total_slots,
                'active_tickets': active_tickets,
                'reserved_slots': reserved_slots,
                'feedback_count': feedback_count,
                'last_cleanup': datetime.utcnow().isoformat()  # Simulação, pode ser ajustado
            }
            
            logger.info(f"Status do sistema retornado para {request.user_id}")
            return jsonify(response), 200
        except Exception as e:
            logger.error(f"Erro ao verificar status do sistema: {str(e)}")
            return jsonify({'error': 'Erro interno ao verificar status do sistema'}), 500