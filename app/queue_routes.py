# app/queue_routes.py
from flask import jsonify, request
from . import db
from .models import Queue, Ticket
from .auth import require_auth
import uuid
from datetime import datetime, time

def init_queue_routes(app):
    @app.route('/api/queues', methods=['GET'])
    def list_queues():
        queues = Queue.query.all()
        now = datetime.now().time()
        return jsonify([{
            'id': q.id,
            'service': q.service,
            'sector': q.sector,
            'department': q.department,
            'institution': q.institution,
            'open_time': q.open_time.strftime('%H:%M'),
            'daily_limit': q.daily_limit,
            'active_tickets': q.active_tickets,
            'status': 'Aberto' if now >= q.open_time and q.active_tickets < q.daily_limit else 'Fechado' if now < q.open_time else 'Lotado'
        } for q in queues])

    @app.route('/api/queue/create', methods=['POST'])
    @require_auth
    def create_queue():
        data = request.get_json()
        required_fields = ['service', 'sector', 'department', 'institution', 'open_time', 'daily_limit']
        if not data or not all(field in data for field in required_fields):
            return jsonify({'error': 'Campos obrigatórios: service, sector, department, institution, open_time, daily_limit'}), 400
        
        service = data['service']
        if Queue.query.filter_by(service=service).first():
            return jsonify({'error': 'Fila para este serviço já existe'}), 400
        
        try:
            open_time_obj = datetime.strptime(data['open_time'], '%H:%M').time()
        except ValueError:
            return jsonify({'error': 'Formato de open_time inválido (use HH:MM)'}), 400
        
        queue = Queue(
            id=str(uuid.uuid4()),
            service=service,
            sector=data['sector'],
            department=data['department'],
            institution=data['institution'],
            open_time=open_time_obj,
            daily_limit=data['daily_limit'],
            created_at=datetime.utcnow()
        )
        db.session.add(queue)
        db.session.commit()
        
        return jsonify({
            'message': f'Fila para {service} criada com sucesso',
            'queue': {
                'id': queue.id,
                'service': queue.service,
                'sector': queue.sector,
                'department': queue.department,
                'institution': queue.institution,
                'open_time': queue.open_time.strftime('%H:%M'),
                'daily_limit': queue.daily_limit,
                'created_at': queue.created_at.isoformat()
            }
        }), 201

    @app.route('/api/queue/<service>/ticket', methods=['POST'])
    @require_auth
    def get_ticket(service):
        queue = Queue.query.filter_by(service=service).first()
        if not queue:
            return jsonify({'error': 'Serviço não encontrado'}), 404
        
        now = datetime.now().time()
        if now < queue.open_time:
            return jsonify({'error': f'A fila abre às {queue.open_time.strftime("%H:%M")}'}), 400
        
        if queue.active_tickets >= queue.daily_limit:
            return jsonify({'error': 'Limite diário atingido'}), 400
        
        user_id = request.user_id
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
            'sector': queue.sector,
            'department': queue.department,
            'institution': queue.institution,
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
            'sector': queue.sector,
            'department': queue.department,
            'institution': queue.institution,
            'open_time': queue.open_time.strftime('%H:%M'),
            'daily_limit': queue.daily_limit,
            'current_ticket': queue.current_ticket,
            'active_tickets': queue.active_tickets,
            'avg_wait_time': f'{queue.avg_wait_time} minutos'
        })