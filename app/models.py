# app/models.py
from . import db
from datetime import datetime

class Queue(db.Model):
    id = db.Column(db.String(36), primary_key=True)  # UUID para filas
    service = db.Column(db.String(100), nullable=False, unique=True)
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