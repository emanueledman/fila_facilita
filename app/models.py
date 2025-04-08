from . import db
from datetime import datetime, time
import uuid

class LocalAtendimento(db.Model):
    __tablename__ = 'local_atendimento'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    nome = db.Column(db.String(100), nullable=False)
    endereco = db.Column(db.String(255), nullable=False)
    tipo = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    servicos = db.relationship('Servico', backref='local', lazy='dynamic')
    __table_args__ = (db.Index('idx_local_nome', 'nome'),)
    def __repr__(self):
        return f"<LocalAtendimento {self.nome} ({self.tipo})>"

class Servico(db.Model):
    __tablename__ = 'servico'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    nome = db.Column(db.String(100), nullable=False, unique=True)
    descricao = db.Column(db.String(255))
    duracao_media = db.Column(db.Integer, nullable=False, default=10)
    local_id = db.Column(db.String(36), db.ForeignKey('local_atendimento.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    queues = db.relationship('Queue', backref='servico', lazy='dynamic')
    slots = db.relationship('SlotAgendamento', backref='servico', lazy='dynamic')
    __table_args__ = (db.Index('idx_servico_nome', 'nome'),)
    def __repr__(self):
        return f"<Servico {self.nome}>"

class Queue(db.Model):
    __tablename__ = 'queue'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    service = db.Column(db.String(100), nullable=False, unique=True)
    servico_id = db.Column(db.String(36), db.ForeignKey('servico.id'), nullable=False)
    sector = db.Column(db.String(50), nullable=False)
    department = db.Column(db.String(100), nullable=False)
    institution = db.Column(db.String(100), nullable=False)
    open_time = db.Column(db.Time, nullable=False)
    daily_limit = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    current_ticket = db.Column(db.Integer, default=0)
    active_tickets = db.Column(db.Integer, default=0)
    avg_wait_time = db.Column(db.Integer, default=10)
    tickets = db.relationship('Ticket', backref='queue', lazy='dynamic')
    __table_args__ = (
        db.Index('idx_queue_service', 'service'),
        db.Index('idx_queue_servico_id', 'servico_id'),
    )
    def __repr__(self):
        return f"<Queue {self.service} (Ativos: {self.active_tickets}/{self.daily_limit})>"

class Ticket(db.Model):
    __tablename__ = 'ticket'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    queue_id = db.Column(db.String(36), db.ForeignKey('queue.id'), nullable=False)
    user_id = db.Column(db.String(36), nullable=False)
    ticket_number = db.Column(db.Integer, nullable=False)
    qr_code = db.Column(db.String(50), unique=True)
    issued_at = db.Column(db.DateTime, default=datetime.utcnow)
    attended_at = db.Column(db.DateTime)
    expires_at = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='pending')
    trade_available = db.Column(db.Boolean, default=False)
    priority = db.Column(db.Integer, default=0)
    is_physical = db.Column(db.Boolean, default=False)
    receipt_data = db.Column(db.Text)
    __table_args__ = (
        db.Index('idx_ticket_queue_id', 'queue_id'),
        db.Index('idx_ticket_user_id', 'user_id'),
        db.Index('idx_ticket_status', 'status'),
    )
    def __repr__(self):
        return f"<Ticket #{self.ticket_number} (Queue: {self.queue_id}, Status: {self.status})>"

class SlotAgendamento(db.Model):
    __tablename__ = 'slot_agendamento'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    servico_id = db.Column(db.String(36), db.ForeignKey('servico.id'), nullable=False)
    data_horario = db.Column(db.DateTime, nullable=False)
    capacidade_maxima = db.Column(db.Integer, nullable=False)
    capacidade_atual = db.Column(db.Integer, default=0)
    user_id = db.Column(db.String(36))
    status = db.Column(db.String(20), default="aberto")
    trade_available = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (
        db.Index('idx_slot_servico_id', 'servico_id'),
        db.Index('idx_slot_data_horario', 'data_horario'),
        db.Index('idx_slot_status', 'status'),
    )
    def __repr__(self):
        return f"<SlotAgendamento {self.id} (Serviço: {self.servico_id}, {self.data_horario})>"

class Feedback(db.Model):
    __tablename__ = 'feedback'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), nullable=False)
    ticket_id = db.Column(db.String(36), db.ForeignKey('ticket.id'), nullable=True)
    slot_id = db.Column(db.String(36), db.ForeignKey('slot_agendamento.id'), nullable=True)
    nota = db.Column(db.Integer, nullable=False)
    comentario = db.Column(db.Text)
    data = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (
        db.Index('idx_feedback_user_id', 'user_id'),
        db.Index('idx_feedback_ticket_id', 'ticket_id'),
        db.Index('idx_feedback_slot_id', 'slot_id'),
    )
    def __repr__(self):
        return f"<Feedback {self.id} (Nota: {self.nota})>"