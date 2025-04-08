import logging
from datetime import datetime
from flask import current_app
from flask_socketio import emit
from sqlalchemy import func
from .. import db
from ..models import Queue, Ticket, SlotAgendamento, Feedback
from .queue_service import QueueService
from .slot_service import SlotService

# Configuração de logging
logger = logging.getLogger(__name__)

def setup_logging():
    if not logger.handlers:
        log_handler = logging.handlers.RotatingFileHandler(
            'integration_service.log', maxBytes=1024*1024, backupCount=10
        )
        log_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        log_handler.setLevel(logging.INFO)
        logger.addHandler(log_handler)
        logger.setLevel(logging.INFO)

setup_logging()

class IntegrationService:
    # Constantes
    CLEANUP_INTERVAL_MINUTES = 5  # Intervalo para limpeza de expirados

    @staticmethod
    def monitor_queue(queue_id):
        """Retorna dados detalhados de monitoramento de uma fila para gestores."""
        queue = Queue.query.get_or_404(queue_id)
        tickets_pending = Ticket.query.filter_by(queue_id=queue_id, status='pending').order_by(Ticket.priority.desc(), Ticket.ticket_number).all()
        tickets_attended = Ticket.query.filter_by(queue_id=queue_id, status='attended').count()
        tickets_cancelled = Ticket.query.filter_by(queue_id=queue_id, status='cancelled').count()
        feedback_avg = db.session.query(func.avg(Feedback.nota)).filter(Feedback.ticket_id.in_(
            db.session.query(Ticket.id).filter_by(queue_id=queue_id)
        )).scalar() or 0
        
        data = {
            'queue_id': queue.id,
            'service': queue.service,
            'sector': queue.sector,
            'department': queue.department,
            'institution': queue.institution,
            'active_tickets': queue.active_tickets,
            'current_ticket': queue.current_ticket,
            'daily_limit': queue.daily_limit,
            'avg_wait_time': QueueService.calculate_wait_time(queue_id, queue.current_ticket + 1, 0),  # Estimativa para próximo
            'pending_tickets': [{
                'ticket_number': t.ticket_number,
                'priority': t.priority,
                'is_physical': t.is_physical,
                'wait_time': QueueService.calculate_wait_time(queue_id, t.ticket_number, t.priority),
                'expires_at': t.expires_at.isoformat() if t.expires_at else None
            } for t in tickets_pending[:10]],  # Limite de 10 para performance
            'attended_today': tickets_attended,
            'cancelled_today': tickets_cancelled,
            'feedback_avg': round(float(feedback_avg), 1)
        }
        
        logger.info(f"Monitoramento gerado para fila {queue_id}: {data}")
        
        emit('monitor_update', {
            'queue_id': queue_id,
            'data': data,
            'message': f"Atualização de monitoramento para {queue.service}"
        }, namespace='/', broadcast=True)
        
        return data

    @staticmethod
    def monitor_slots(servico_id):
        """Retorna dados detalhados de monitoramento de slots para um serviço."""
        servico = Servico.query.get_or_404(servico_id)
        slots = SlotAgendamento.query.filter_by(servico_id=servico_id).all()
        active_slots = [s for s in slots if s.status in ['aberto', 'reservado']]
        feedback_avg = db.session.query(func.avg(Feedback.nota)).filter(Feedback.slot_id.in_(
            db.session.query(SlotAgendamento.id).filter_by(servico_id=servico_id)
        )).scalar() or 0
        
        data = {
            'servico_id': servico.id,
            'nome': servico.nome,
            'active_slots': len(active_slots),
            'total_slots': len(slots),
            'slots_details': [{
                'slot_id': s.id,
                'data_horario': s.data_horario.isoformat(),
                'capacidade_maxima': s.capacidade_maxima,
                'capacidade_atual': s.capacidade_atual,
                'status': s.status,
                'trade_available': s.trade_available
            } for s in active_slots[:10]],  # Limite de 10 para performance
            'feedback_avg': round(float(feedback_avg), 1)
        }
        
        logger.info(f"Monitoramento gerado para serviço {servico_id}: {data}")
        
        emit('monitor_update', {
            'servico_id': servico_id,
            'data': data,
            'message': f"Atualização de monitoramento para {servico.nome}"
        }, namespace='/', broadcast=True)
        
        return data

    @staticmethod
    def cleanup_expired():
        """Remove tickets e slots expirados do sistema."""
        now = datetime.utcnow()
        
        # Limpeza de tickets expirados
        expired_tickets = Ticket.query.filter(
            Ticket.status == 'pending',
            Ticket.expires_at.isnot(None),
            Ticket.expires_at < now
        ).all()
        
        for ticket in expired_tickets:
            ticket.status = 'cancelled'
            ticket.queue.active_tickets -= 1
            QueueService.send_notification(ticket.user_id, f"Sua senha #{ticket.ticket_number} expirou!")
            logger.info(f"Ticket {ticket.id} expirado e cancelado")
        
        # Limpeza de slots concluídos ou expirados
        expired_slots = SlotAgendamento.query.filter(
            SlotAgendamento.status.in_(['aberto', 'reservado']),
            SlotAgendamento.data_horario < now
        ).all()
        
        for slot in expired_slots:
            slot.status = 'concluido'
            if slot.user_id:
                SlotService.send_notification(slot.user_id, f"Seu agendamento para {slot.servico.nome} terminou.")
            logger.info(f"Slot {slot.id} marcado como concluído")
        
        if expired_tickets or expired_slots:
            db.session.commit()
            emit('cleanup_update', {
                'tickets_cancelled': len(expired_tickets),
                'slots_concluded': len(expired_slots),
                'message': "Limpeza de itens expirados concluída"
            }, namespace='/', broadcast=True)
            logger.info(f"Limpeza concluída: {len(expired_tickets)} tickets, {len(expired_slots)} slots")

    @staticmethod
    def generate_report(start_date, end_date):
        """Gera um relatório estatístico para o período especificado."""
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)
        
        if start >= end:
            logger.warning(f"Período inválido para relatório: {start_date} a {end_date}")
            raise ValueError("Data inicial deve ser anterior à data final")
        
        # Estatísticas de filas
        total_tickets = Ticket.query.filter(Ticket.issued_at.between(start, end)).count()
        attended_tickets = Ticket.query.filter(
            Ticket.status == 'attended',
            Ticket.issued_at.between(start, end)
        ).count()
        cancelled_tickets = Ticket.query.filter(
            Ticket.status == 'cancelled',
            Ticket.issued_at.between(start, end)
        ).count()
        avg_wait_time = db.session.query(func.avg(
            (Ticket.attended_at - Ticket.issued_at).cast(db.Integer) / 60
        )).filter(
            Ticket.status == 'attended',
            Ticket.issued_at.between(start, end)
        ).scalar() or 0
        
        # Estatísticas de slots
        total_slots = SlotAgendamento.query.filter(SlotAgendamento.created_at.between(start, end)).count()
        reserved_slots = SlotAgendamento.query.filter(
            SlotAgendamento.status.in_(['reservado', 'concluido']),
            SlotAgendamento.created_at.between(start, end)
        ).count()
        
        # Feedback
        feedback_avg = db.session.query(func.avg(Feedback.nota)).filter(
            Feedback.data.between(start, end)
        ).scalar() or 0
        
        report = {
            'period': {'start': start.isoformat(), 'end': end.isoformat()},
            'tickets': {
                'total': total_tickets,
                'attended': attended_tickets,
                'cancelled': cancelled_tickets,
                'avg_wait_time_minutes': round(float(avg_wait_time), 1)
            },
            'slots': {
                'total': total_slots,
                'reserved': reserved_slots,
                'occupancy_rate': round((reserved_slots / total_slots * 100) if total_slots > 0 else 0, 1)
            },
            'feedback': {
                'avg_rating': round(float(feedback_avg), 1)
            }
        }
        
        logger.info(f"Relatório gerado para {start_date} a {end_date}: {report}")
        
        emit('report_update', {
            'report': report,
            'message': f"Relatório gerado para {start_date} a {end_date}"
        }, namespace='/', broadcast=True)
        
        return report

    @staticmethod
    def get_trade_offers():
        """Retorna todos os tickets e slots disponíveis para troca."""
        trade_tickets = Ticket.query.filter_by(trade_available=True, status='pending').all()
        trade_slots = SlotAgendamento.query.filter_by(trade_available=True, status='reservado').all()
        
        offers = {
            'tickets': [{
                'ticket_id': t.id,
                'queue_service': t.queue.service,
                'ticket_number': t.ticket_number,
                'priority': t.priority,
                'user_id': t.user_id
            } for t in trade_tickets],
            'slots': [{
                'slot_id': s.id,
                'service': s.servico.nome,
                'data_horario': s.data_horario.isoformat(),
                'user_id': s.user_id
            } for s in trade_slots]
        }
        
        logger.info(f"Ofertas de troca retornadas: {len(trade_tickets)} tickets, {len(trade_slots)} slots")
        return offers