# app/models.py
from . import db
from datetime import datetime, time

class Queue(db.Model):
    id = db.Column(db.String(36), primary_key=True)  # UUID para filas
    service = db.Column(db.String(100), nullable=False, unique=True)  # Nome do serviço (ex.: "Vacinação Infantil")
    sector = db.Column(db.String(50), nullable=False)  # Setor (ex.: "Saúde")
    department = db.Column(db.String(100), nullable=False)  # Departamento (ex.: "Centro de Saúde Camama")
    institution = db.Column(db.String(100), nullable=False)  # Instituição (ex.: "Ministério da Saúde")
    open_time = db.Column(db.Time, nullable=False)  # Horário de abertura da fila (ex.: 07:00)
    daily_limit = db.Column(db.Integer, nullable=False)  # Limite diário de vagas
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    current_ticket = db.Column(db.Integer, default=0)
    active_tickets = db.Column(db.Integer, default=0)
    avg_wait_time = db.Column(db.Integer, default=10)  # Em minutos

class Ticket(db.Model):
    id = db.Column(db.String(36), primary_key=True)  # UUID para senhas
    queue_id = db.Column(db.String(36), db.ForeignKey('queue.id'), nullable=False)
    user_id = db.Column(db.String(36), nullable=False)  # ID do usuário logado
    ticket_number = db.Column(db.Integer, nullable=False)
    issued_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending')  # pending, called, cancelled
    queue = db.relationship('Queue', backref=db.backref('tickets', lazy=True))