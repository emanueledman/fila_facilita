from . import db
from datetime import datetime, time

class LocalAtendimento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    endereco = db.Column(db.String(200), nullable=False)
    tipo = db.Column(db.String(50), nullable=False)

class Servico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.String(200))
    duracao_media = db.Column(db.Integer, nullable=False)
    local_id = db.Column(db.Integer, db.ForeignKey('local_atendimento.id'), nullable=False)

class Queue(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    service = db.Column(db.String(100), nullable=False)
    servico_id = db.Column(db.Integer, db.ForeignKey('servico.id'), nullable=False)
    sector = db.Column(db.String(50), nullable=False)
    department = db.Column(db.String(100), nullable=False)
    institution = db.Column(db.String(100), nullable=False)
    open_time = db.Column(db.Time, nullable=False)
    daily_limit = db.Column(db.Integer, nullable=False)
    avg_wait_time = db.Column(db.Integer, nullable=False)
    active_tickets = db.Column(db.Integer, default=0)
    current_ticket = db.Column(db.Integer, default=0)

class SlotAgendamento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    servico_id = db.Column(db.Integer, db.ForeignKey('servico.id'), nullable=False)
    data_horario = db.Column(db.DateTime, nullable=False)
    capacidade_maxima = db.Column(db.Integer, nullable=False)
    capacidade_atual = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='aberto')  # aberto, reservado, concluido
    user_id = db.Column(db.String(50))
    trade_available = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime)
    servico = db.relationship('Servico', backref='slots')

class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    queue_id = db.Column(db.Integer, db.ForeignKey('queue.id'), nullable=False)
    user_id = db.Column(db.String(50), nullable=False)
    ticket_number = db.Column(db.Integer, nullable=False)
    qr_code = db.Column(db.String(50), nullable=False)
    issued_at = db.Column(db.DateTime, default=datetime.utcnow)
    attended_at = db.Column(db.DateTime)
    expires_at = db.Column(db.DateTime)
    priority = db.Column(db.Integer, default=0)
    is_physical = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default='pending')
    trade_available = db.Column(db.Boolean, default=False)
    receipt_data = db.Column(db.Text)
    queue = db.relationship('Queue', backref='tickets')

class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(50), nullable=False)
    ticket_id = db.Column(db.Integer, db.ForeignKey('ticket.id'), nullable=False)
    nota = db.Column(db.Integer, nullable=False)
    comentario = db.Column(db.String(200))
    data = db.Column(db.DateTime, default=datetime.utcnow)