# app/queue_routes.py
from flask import jsonify, request
from . import db
from .models import Queue, Ticket
from .auth import require_auth
import uuid
from datetime import datetime

def init_queue_routes(app):
    @app.route('/api/queue/create', methods=['POST'])
    @require_auth
    def create_queue():
        data = request.get_json()
        if not data or 'service' not in data:
            return jsonify({'error': 'O campo "service" é obrigatório'}), 400
        
        service = data['service']
        if Queue.query.filter_by(service=service).first():
            return jsonify({'error': 'Fila para este serviço já existe'}), 400
        
        queue = Queue(
            id=str(uuid.uuid4()),
            service=service,
            created_at=datetime.utcnow()
        )
        db.session.add(queue)
        db.session.commit()
        
        return jsonify({
            'message': f'Fila para {service} criada com sucesso',
            'queue': {
                'id': queue.id,
                'service': queue.service,
                'created_at': queue.created_at.isoformat()
            }
        }), 201

    @app.route('/api/queue/<service>/ticket', methods=['POST'])
    @require_auth
    def get_ticket(service):
        queue = Queue.query.filter_by(service=service).first()
        if not queue:
            return jsonify({'error': 'Serviço não encontrado'}), 404
        
        user_id = request.user_id
        # Verifica se o usuário já tem uma senha ativa
        existing_ticket = Ticket.query.filter_by(
            user_id=user_id, queue_id=queue.id, status='pending'
        ).first()
        if existing_ticket:
            return jsonify({'error': 'Você já possui uma senha ativa para este serviço'}), 400
        
        ticket_number = queue.active_tickets + 1
        ticket = Ticket(
            id=str(uuid.uuid4()),
            queue_id=queue.id,
            user_id=user_id,
            ticket_number=ticket_number,
            issued_at=datetime.utcnow()
        )
        queue.active_tickets += 1
        db.session.add(ticket)
        db.session.commit()
        
        wait_time = ticket_number * queue.avg_wait_time
        return jsonify({
            'message': 'Senha emitida com sucesso',
            'ticket': {
                'id': ticket.id,
                'number': ticket.ticket_number,
                'wait_time': f'{wait_time} minutos'
            }
        }), 201

    @app.route('/api/ticket/<ticket_id>', methods=['GET'])
    @require_auth
    def ticket_status(ticket_id):
        ticket = Ticket.query.get(ticket_id)
        if not ticket or ticket.user_id != request.user_id:
            return jsonify({'error': 'Senha não encontrada ou não autorizada'}), 404
        
        queue = ticket.queue
        position = ticket.ticket_number - queue.current_ticket
        wait_time = max(0, position * queue.avg_wait_time)
        
        return jsonify({
            'service': queue.service,
            'ticket_number': ticket.ticket_number,
            'status': ticket.status,
            'position': max(0, position),
            'wait_time': f'{wait_time} minutos'
        })

    @app.route('/api/queue/<service>/call', methods=['POST'])
    @require_auth
    def call_next_ticket(service):
        # TODO: Adicionar verificação de permissão de admin
        queue = Queue.query.filter_by(service=service).first()
        if not queue:
            return jsonify({'error': 'Serviço não encontrado'}), 404
        
        if queue.active_tickets == 0:
            return jsonify({'error': 'Não há senhas na fila'}), 400
        
        queue.current_ticket += 1
        queue.active_tickets -= 1
        
        ticket = Ticket.query.filter_by(
            queue_id=queue.id, ticket_number=queue.current_ticket
        ).first()
        if ticket:
            ticket.status = 'called'
        
        db.session.commit()
        
        return jsonify({
            'message': f'Senha {queue.current_ticket} chamada',
            'remaining_tickets': queue.active_tickets
        })

    @app.route('/api/queue/<service>', methods=['GET'])
    def queue_status(service):
        queue = Queue.query.filter_by(service=service).first()
        if not queue:
            return jsonify({'error': 'Serviço não encontrado'}), 404
        
        return jsonify({
            'service': queue.service,
            'current_ticket': queue.current_ticket,
            'active_tickets': queue.active_tickets,
            'avg_wait_time': f'{queue.avg_wait_time} minutos'
        })