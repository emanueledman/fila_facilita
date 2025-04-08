import uuid
from datetime import datetime, timedelta
import logging
from flask import current_app
from flask_socketio import emit
from sqlalchemy import desc
from .. import db
from ..models import SlotAgendamento, Servico
import os  # Adicionado o import de os

# Configuração de logging
logger = logging.getLogger(__name__)

def setup_logging():
    if not logger.handlers:
        log_handler = logging.handlers.RotatingFileHandler(
            'slot_service.log', maxBytes=1024*1024, backupCount=10
        )
        log_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        log_handler.setLevel(logging.INFO)
        logger.addHandler(log_handler)
        logger.setLevel(logging.INFO)

setup_logging()

class SlotService:
    # Constantes
    FCM_API_URL = "https://fcm.googleapis.com/fcm/send"
    FCM_API_KEY = os.getenv("FCM_API_KEY", "sua_chave_fcm")  # Carrega do .env
    NOTIFICATION_THRESHOLD_MINUTES = 15  # Notificação proativa a 15 minutos do slot

    @staticmethod
    def send_notification(user_id, message, via_websocket=True):
        """Envia notificação para o usuário via FCM e WebSocket."""
        logger.info(f"Enviando notificação para {user_id}: {message}")
        
        # Simulação de envio via FCM (substitua por integração real)
        try:
            import requests
            response = requests.post(
                SlotService.FCM_API_URL,
                json={"to": f"user-{user_id}", "notification": {"title": "Facilita 2.0", "body": message}},
                headers={"Authorization": f"key={SlotService.FCM_API_KEY}"}
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
    def create_slot(service, data_horario, capacidade_maxima, gestor_id=None):
        """Cria um novo slot de agendamento para um serviço."""
        servico = Servico.query.filter_by(nome=service).first()
        if not servico:
            logger.error(f"Serviço não encontrado: {service}")
            raise ValueError("Serviço não encontrado")
        
        # Validações
        if data_horario < datetime.utcnow():
            logger.warning(f"Tentativa de criar slot no passado: {data_horario}")
            raise ValueError("Data do slot deve ser no futuro")
        if capacidade_maxima <= 0:
            logger.warning(f"Capacidade máxima inválida: {capacidade_maxima}")
            raise ValueError("Capacidade máxima deve ser positiva")
        
        slot = SlotAgendamento(
            servico_id=servico.id,
            data_horario=data_horario,
            capacidade_maxima=capacidade_maxima,
            user_id=gestor_id if gestor_id else None  # Gestor pode criar sem reservar
        )
        db.session.add(slot)
        db.session.commit()
        
        message = f"Slot criado para {service} em {data_horario.strftime('%d/%m/%Y %H:%M')} com capacidade {capacidade_maxima}"
        if gestor_id:
            SlotService.send_notification(gestor_id, message)
        
        emit('slot_update', {
            'slot_id': slot.id,
            'service': service,
            'data_horario': slot.data_horario.isoformat(),
            'capacidade_maxima': slot.capacidade_maxima,
            'message': "Novo slot disponível"
        }, namespace='/', broadcast=True)
        
        logger.info(f"Slot {slot.id} criado para {service} por {gestor_id or 'sistema'}")
        return slot

    @staticmethod
    def reserve_slot(slot_id, user_id):
        """Reserva um slot para um usuário."""
        slot = SlotAgendamento.query.get_or_404(slot_id)
        
        if slot.status != "aberto":
            logger.warning(f"Tentativa de reservar slot {slot_id} com status {slot.status}")
            raise ValueError("Slot não está disponível")
        if slot.capacidade_atual >= slot.capacidade_maxima:
            logger.warning(f"Slot {slot_id} está lotado: {slot.capacidade_atual}/{slot.capacidade_maxima}")
            raise ValueError("Slot lotado")
        if SlotAgendamento.query.filter_by(user_id=user_id, servico_id=slot.servico_id, status='reservado').first():
            logger.warning(f"Usuário {user_id} já tem reserva para o serviço {slot.servico.nome}")
            raise ValueError("Usuário já tem um agendamento para este serviço")
        
        slot.user_id = user_id
        slot.capacidade_atual += 1
        slot.status = "reservado" if slot.capacidade_atual < slot.capacidade_maxima else "concluido"
        db.session.commit()
        
        message = f"Agendamento confirmado para {slot.servico.nome} em {slot.data_horario.strftime('%d/%m/%Y %H:%M')}"
        SlotService.send_notification(user_id, message)
        
        emit('slot_update', {
            'slot_id': slot.id,
            'service': slot.servico.nome,
            'data_horario': slot.data_horario.isoformat(),
            'capacidade_atual': slot.capacidade_atual,
            'message': f"Slot reservado por {user_id}"
        }, namespace='/', broadcast=True)
        
        logger.info(f"Slot {slot.id} reservado por {user_id}")
        return slot

    @staticmethod
    def cancel_slot_reservation(slot_id, user_id):
        """Cancela uma reserva de slot."""
        slot = SlotAgendamento.query.get_or_404(slot_id)
        
        if slot.user_id != user_id or slot.status != "reservado":
            logger.warning(f"Tentativa inválida de cancelar slot {slot_id} por {user_id}")
            raise ValueError("Você não pode cancelar este slot")
        
        slot.user_id = None
        slot.capacidade_atual -= 1
        slot.status = "aberto"
        db.session.commit()
        
        message = f"Reserva cancelada para {slot.servico.nome} em {slot.data_horario.strftime('%d/%m/%Y %H:%M')}"
        SlotService.send_notification(user_id, message)
        
        emit('slot_update', {
            'slot_id': slot.id,
            'service': slot.servico.nome,
            'data_horario': slot.data_horario.isoformat(),
            'capacidade_atual': slot.capacidade_atual,
            'message': f"Reserva cancelada por {user_id}"
        }, namespace='/', broadcast=True)
        
        logger.info(f"Reserva do slot {slot.id} cancelada por {user_id}")
        return slot

    @staticmethod
    def check_proactive_notifications():
        """Verifica e envia notificações proativas para slots próximos."""
        now = datetime.utcnow()
        reserved_slots = SlotAgendamento.query.filter_by(status='reservado').all()
        
        for slot in reserved_slots:
            time_to_slot = (slot.data_horario - now).total_seconds() / 60
            if 0 < time_to_slot <= SlotService.NOTIFICATION_THRESHOLD_MINUTES:
                message = f"Seu agendamento para {slot.servico.nome} está a {int(time_to_slot)} minutos!"
                SlotService.send_notification(slot.user_id, message)
                logger.debug(f"Notificação proativa enviada para slot {slot.id}")
            elif time_to_slot <= 0:
                slot.status = "concluido"
                db.session.commit()
                SlotService.send_notification(slot.user_id, f"Seu agendamento para {slot.servico.nome} terminou.")
                logger.info(f"Slot {slot.id} marcado como concluído")

    @staticmethod
    def offer_trade_slot(slot_id, user_id):
        """Oferece um slot para troca."""
        slot = SlotAgendamento.query.get_or_404(slot_id)
        
        if slot.user_id != user_id or slot.status != "reservado":
            logger.warning(f"Tentativa inválida de oferecer slot {slot_id} por {user_id}")
            raise ValueError("Você não pode oferecer este slot para troca")
        
        slot.trade_available = True
        db.session.commit()
        
        message = f"Seu agendamento para {slot.servico.nome} em {slot.data_horario.strftime('%d/%m/%Y %H:%M')} está disponível para troca."
        SlotService.send_notification(user_id, message)
        
        emit('trade_update', {
            'slot_id': slot.id,
            'message': f"Slot em {slot.data_horario.strftime('%d/%m/%Y %H:%M')} disponível para troca"
        }, namespace='/', broadcast=True)
        
        logger.info(f"Slot {slot.id} oferecido para troca por {user_id}")
        return slot

    @staticmethod
    def trade_slots(slot_from_id, slot_to_id, user_from_id):
        """Realiza a troca entre dois slots."""
        slot_from = SlotAgendamento.query.get_or_404(slot_from_id)
        slot_to = SlotAgendamento.query.get_or_404(slot_to_id)
        
        if slot_from.user_id != user_from_id or not slot_to.trade_available or \
           slot_from.servico_id != slot_to.servico_id or slot_from.status != "reservado" or \
           slot_to.status != "reservado":
            logger.warning(f"Tentativa inválida de troca entre slots {slot_from_id} e {slot_to_id}")
            raise ValueError("Troca inválida")
        
        user_from, user_to = slot_from.user_id, slot_to.user_id
        slot_from.user_id, slot_to.user_id = user_to, user_from
        slot_from.trade_available, slot_to.trade_available = False, False
        
        db.session.commit()
        
        SlotService.send_notification(user_from, f"Troca realizada! Novo agendamento: {slot_to.data_horario.strftime('%d/%m/%Y %H:%M')}")
        SlotService.send_notification(user_to, f"Troca realizada! Novo agendamento: {slot_from.data_horario.strftime('%d/%m/%Y %H:%M')}")
        
        emit('trade_update', {
            'slot_from_id': slot_from.id,
            'slot_to_id': slot_to.id,
            'message': f"Troca realizada entre slots em {slot_from.data_horario.strftime('%d/%m/%Y %H:%M')} e {slot_to.data_horario.strftime('%d/%m/%Y %H:%M')}"
        }, namespace='/', broadcast=True)
        
        logger.info(f"Troca realizada entre slots {slot_from_id} e {slot_to_id}")
        return {"slot_from": slot_from, "slot_to": slot_to}

    @staticmethod
    def get_slot_availability(slot_id):
        """Retorna a disponibilidade atual de um slot."""
        slot = SlotAgendamento.query.get_or_404(slot_id)
        availability = {
            'slot_id': slot.id,
            'service': slot.servico.nome,
            'data_horario': slot.data_horario.isoformat(),
            'capacidade_maxima': slot.capacidade_maxima,
            'capacidade_atual': slot.capacidade_atual,
            'status': slot.status,
            'available_spots': slot.capacidade_maxima - slot.capacidade_atual
        }
        logger.debug(f"Disponibilidade do slot {slot_id}: {availability}")
        return availability