import uuid
from datetime import datetime, timedelta
import logging
from flask import current_app
from flask_socketio import emit
from sqlalchemy import desc
from sqlalchemy.exc import SQLAlchemyError  # Adicionado para capturar erros de banco
from .. import db
from ..models import Queue, Ticket

# Configuração de logging
logger = logging.getLogger(__name__)

def setup_logging():
    if not logger.handlers:
        log_handler = logging.handlers.RotatingFileHandler(
            'queue_service.log', maxBytes=1024*1024, backupCount=10
        )
        log_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        log_handler.setLevel(logging.INFO)
        logger.addHandler(log_handler)
        logger.setLevel(logging.INFO)

setup_logging()

class QueueService:
    # Constantes
    FCM_API_URL = "https://fcm.googleapis.com/fcm/send"
    FCM_API_KEY = "sua_chave_fcm"  # Substitua pela chave real no .env
    DEFAULT_EXPIRATION_MINUTES = 30  # Tempo de expiração padrão para tickets

    @staticmethod
    def generate_qr_code():
        """Gera um código QR único para cada ticket."""
        qr_code = f"QR-{uuid.uuid4().hex[:8]}"
        logger.debug(f"QR Code gerado: {qr_code}")
        return qr_code

    @staticmethod
    def generate_receipt(ticket):
        """Gera o texto do comprovante em papel para o ticket."""
        queue = ticket.queue
        receipt = (
            "=== Comprovante Facilita 2.0 ===\n"
            f"Serviço: {queue.service}\n"
            f"Setor: {queue.sector}\n"
            f"Departamento: {queue.department}\n"
            f"Instituição: {queue.institution}\n"
            f"Senha: #{ticket.ticket_number}\n"
            f"Tipo: {'Física' if ticket.is_physical else 'Virtual'}\n"
            f"QR Code: {ticket.qr_code}\n"
            f"Prioridade: {ticket.priority}\n"
            f"Data de Emissão: {ticket.issued_at.strftime('%d/%m/%Y %H:%M')}\n"
            f"Expira em: {ticket.expires_at.strftime('%d/%m/%Y %H:%M') if ticket.expires_at else 'N/A'}\n"
            "=== Guarde este comprovante ==="
        )
        logger.debug(f"Comprovante gerado para ticket {ticket.id}: {receipt}")
        return receipt

    @staticmethod
    def update_wait_time(queue_id):
        """Atualiza o tempo médio de espera da fila com base em tickets atendidos."""
        queue = Queue.query.get_or_404(queue_id)
        attended_tickets = Ticket.query.filter_by(queue_id=queue_id, status='attended').all()
        
        if attended_tickets:
            total_time = sum(
                (t.attended_at - t.issued_at).total_seconds() / 60
                for t in attended_tickets if t.attended_at
            )
            new_avg = max(5, int(total_time / len(attended_tickets)))  # Mínimo de 5 minutos
            queue.avg_wait_time = new_avg
            db.session.commit()
            logger.info(f"Tempo médio de espera atualizado para fila {queue_id}: {new_avg} minutos")
        return queue.avg_wait_time

    @staticmethod
    def calculate_wait_time(queue_id, ticket_number, priority):
        """Calcula o tempo estimado de espera para um ticket."""
        queue = Queue.query.get_or_404(queue_id)
        QueueService.update_wait_time(queue_id)
        
        position = max(0, ticket_number - queue.current_ticket)
        wait_time = position * queue.avg_wait_time
        
        # Ajuste por prioridade
        if priority > 0:
            wait_time = max(0, wait_time - (priority * 5))  # 5 minutos por nível
        
        # Ajuste por volume de tickets ativos
        if queue.active_tickets > 10:
            wait_time += int(queue.active_tickets * 0.5)
        
        logger.debug(f"Tempo de espera calculado para ticket {ticket_number} na fila {queue_id}: {wait_time} minutos")
        return wait_time

    @staticmethod
    def send_notification(user_id, message, via_websocket=True):
        """Envia notificação para o usuário via FCM e WebSocket."""
        logger.info(f"Enviando notificação para {user_id}: {message}")
        
        # Simulação de envio via FCM (substitua por integração real)
        try:
            import requests
            response = requests.post(
                QueueService.FCM_API_URL,
                json={"to": f"user-{user_id}", "notification": {"title": "Facilita 2.0", "body": message}},
                headers={"Authorization": f"key={QueueService.FCM_API_KEY}"}
            )
            if response.status_code != 200:
                logger.error(f"Falha ao enviar notificação FCM: {response.text}")
        except Exception as e:
            logger.error(f"Erro ao enviar notificação FCM: {str(e)}")
        
        # Envio via WebSocket
        if via_websocket:
            try:
                emit('notification', {'user_id': user_id, 'message': message}, namespace='/', broadcast=True)
                logger.debug(f"Notificação enviada via WebSocket para {user_id}")
            except Exception as e:
                logger.error(f"Erro ao enviar notificação via WebSocket: {str(e)}")

    @staticmethod
    def add_to_queue(service, user_id, priority=0, is_physical=False):
        """Adiciona um usuário a uma fila, gerando ticket e comprovante."""
        try:
            queue = Queue.query.filter_by(service=service).first()
            if not queue:
                logger.error(f"Fila não encontrada para serviço: {service}")
                raise ValueError("Fila não encontrada")
            if queue.active_tickets >= queue.daily_limit:
                logger.warning(f"Fila {service} atingiu o limite diário: {queue.daily_limit}")
                raise ValueError("Fila lotada")
            if Ticket.query.filter_by(user_id=user_id, queue_id=queue.id, status='pending').first():
                logger.warning(f"Usuário {user_id} já está na fila {service}")
                raise ValueError("Usuário já está na fila")
            
            ticket_number = queue.active_tickets + 1
            qr_code = QueueService.generate_qr_code()
            expires_at = datetime.utcnow() + timedelta(minutes=QueueService.DEFAULT_EXPIRATION_MINUTES) if is_physical else None
            
            ticket = Ticket(
                queue_id=queue.id,
                user_id=user_id,
                ticket_number=ticket_number,
                qr_code=qr_code,
                priority=priority,
                is_physical=is_physical,
                expires_at=expires_at
            )
            ticket.receipt_data = QueueService.generate_receipt(ticket)
            
            queue.active_tickets += 1
            db.session.add(ticket)
            logger.debug(f"Antes do commit: ticket={ticket.__dict__}, queue.active_tickets={queue.active_tickets}")
            db.session.commit()
            
            wait_time = QueueService.calculate_wait_time(queue.id, ticket_number, priority)
            message = f"Senha #{ticket_number} emitida. QR: {qr_code}. Espera: {wait_time} min"
            QueueService.send_notification(user_id, message)
            
            emit('queue_update', {
                'queue_id': queue.id,
                'active_tickets': queue.active_tickets,
                'message': f"Nova senha emitida: #{ticket_number}"
            }, namespace='/', broadcast=True)
            
            logger.info(f"Ticket {ticket.id} adicionado à fila {service} para {user_id}")
            return ticket
        
        except SQLAlchemyError as e:
            logger.error(f"Erro no banco de dados ao adicionar ticket: {str(e)}", exc_info=True)
            db.session.rollback()  # Desfaz alterações em caso de erro
            raise  # Propaga o erro para a rota tratar
        
        except Exception as e:
            logger.error(f"Erro interno ao adicionar ticket (não relacionado ao banco): {str(e)}", exc_info=True)
            db.session.rollback()  # Desfaz alterações em caso de erro
            raise  # Propaga o erro para a rota tratar

    @staticmethod
    def call_next(service):
        """Chama o próximo ticket da fila, considerando prioridades."""
        queue = Queue.query.filter_by(service=service).first()
        if not queue:
            logger.error(f"Fila não encontrada para serviço: {service}")
            raise ValueError("Fila não encontrada")
        if queue.active_tickets == 0:
            logger.warning(f"Fila {service} está vazia")
            raise ValueError("Fila vazia")
        
        next_ticket = Ticket.query.filter_by(queue_id=queue.id, status='pending')\
            .order_by(desc(Ticket.priority), Ticket.ticket_number).first()
        if not next_ticket:
            logger.warning(f"Nenhum ticket pendente na fila {service}")
            raise ValueError("Nenhum ticket pendente")
        
        now = datetime.utcnow()
        if next_ticket.expires_at and next_ticket.expires_at < now:
            next_ticket.status = 'cancelled'
            queue.active_tickets -= 1
            db.session.commit()
            logger.info(f"Ticket {next_ticket.id} expirou e foi cancelado")
            return QueueService.call_next(service)  # Chama o próximo recursivamente
        
        queue.current_ticket = next_ticket.ticket_number
        queue.active_tickets -= 1
        next_ticket.status = 'called'
        next_ticket.attended_at = now
        db.session.commit()
        
        message = f"Sua senha #{next_ticket.ticket_number} foi chamada!"
        QueueService.send_notification(next_ticket.user_id, message)
        
        emit('queue_update', {
            'queue_id': queue.id,
            'current_ticket': queue.current_ticket,
            'active_tickets': queue.active_tickets,
            'message': f"Senha #{next_ticket.ticket_number} chamada"
        }, namespace='/', broadcast=True)
        
        logger.info(f"Ticket {next_ticket.id} chamado na fila {service}")
        return next_ticket

    @staticmethod
    def check_proactive_notifications():
        """Verifica e envia notificações proativas para tickets próximos de serem chamados."""
        now = datetime.utcnow()
        pending_tickets = Ticket.query.filter_by(status='pending').all()
        
        for ticket in pending_tickets:
            if ticket.expires_at and ticket.expires_at < now:
                ticket.status = 'cancelled'
                ticket.queue.active_tickets -= 1
                db.session.commit()
                QueueService.send_notification(ticket.user_id, f"Sua senha #{ticket.ticket_number} expirou!")
                logger.info(f"Ticket {ticket.id} expirou e foi cancelado")
                continue
            
            wait_time = QueueService.calculate_wait_time(ticket.queue_id, ticket.ticket_number, ticket.priority)
            if wait_time <= 5:
                message = f"Faltam {wait_time} minutos para sua vez na fila {ticket.queue.service}!"
                QueueService.send_notification(ticket.user_id, message)
                logger.debug(f"Notificação proativa enviada para ticket {ticket.id}")

    @staticmethod
    def offer_trade_ticket(ticket_id, user_id):
        """Oferece um ticket para troca."""
        ticket = Ticket.query.get_or_404(ticket_id)
        if ticket.user_id != user_id or ticket.status != 'pending':
            logger.warning(f"Tentativa inválida de oferecer ticket {ticket_id} por {user_id}")
            raise ValueError("Você não pode oferecer este ticket para troca")
        
        ticket.trade_available = True
        db.session.commit()
        
        message = f"Sua senha #{ticket.ticket_number} está disponível para troca."
        QueueService.send_notification(user_id, message)
        
        emit('trade_update', {
            'ticket_id': ticket.id,
            'message': f"Ticket #{ticket.ticket_number} disponível para troca"
        }, namespace='/', broadcast=True)
        
        logger.info(f"Ticket {ticket.id} oferecido para troca por {user_id}")
        return ticket

    @staticmethod
    def trade_tickets(ticket_from_id, ticket_to_id, user_from_id):
        """Realiza a troca entre dois tickets."""
        ticket_from = Ticket.query.get_or_404(ticket_from_id)
        ticket_to = Ticket.query.get_or_404(ticket_to_id)
        
        if ticket_from.user_id != user_from_id or not ticket_to.trade_available or \
           ticket_from.queue_id != ticket_to.queue_id or ticket_from.status != 'pending' or \
           ticket_to.status != 'pending':
            logger.warning(f"Tentativa inválida de troca entre {ticket_from_id} e {ticket_to_id}")
            raise ValueError("Troca inválida")
        
        user_from, user_to = ticket_from.user_id, ticket_to.user_id
        num_from, num_to = ticket_from.ticket_number, ticket_to.ticket_number
        
        ticket_from.user_id, ticket_from.ticket_number = user_to, num_to
        ticket_to.user_id, ticket_to.ticket_number = user_from, num_from
        ticket_from.trade_available, ticket_to.trade_available = False, False
        
        db.session.commit()
        
        QueueService.send_notification(user_from, f"Troca realizada! Nova senha: #{ticket_to.ticket_number}")
        QueueService.send_notification(user_to, f"Troca realizada! Nova senha: #{ticket_from.ticket_number}")
        
        emit('trade_update', {
            'ticket_from_id': ticket_from.id,
            'ticket_to_id': ticket_to.id,
            'message': f"Troca realizada entre #{ticket_from.ticket_number} e #{ticket_to.ticket_number}"
        }, namespace='/', broadcast=True)
        
        logger.info(f"Troca realizada entre tickets {ticket_from_id} e {ticket_to_id}")
        return {"ticket_from": ticket_from, "ticket_to": ticket_to}