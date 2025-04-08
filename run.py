import logging
from app import create_app, db, socketio
from app.models import LocalAtendimento, Servico, Queue, SlotAgendamento, Ticket, Feedback
from datetime import datetime, time, timedelta, UTC
import uuid
import os

logger = logging.getLogger(__name__)

def setup_logging():
    if not logger.handlers:
        log_handler = logging.handlers.RotatingFileHandler(
            'run.log', maxBytes=1024*1024, backupCount=10
        )
        log_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        log_handler.setLevel(logging.INFO)
        logger.addHandler(log_handler)
        logger.setLevel(logging.INFO)

setup_logging()

def populate_initial_data():
    with app.app_context():
        logger.info("Iniciando população de dados iniciais")
        
        # Em desenvolvimento (local), recria o banco
        if 'RENDER' not in os.environ:
            logger.info("Recriando o banco de dados (apenas localmente)")
            db.drop_all()
            db.create_all()
        else:
            # No Render, cria as tabelas apenas se não existirem
            logger.info("Garantindo que as tabelas existam no Render")
            db.create_all()  # Não sobrescreve tabelas existentes
        
        # Verifica se há dados na tabela queue
        try:
            if Queue.query.count() > 0:
                logger.info("Dados iniciais já existem, pulando população.")
                return
        except Exception as e:
            logger.warning(f"Tabela 'queue' ainda não existe ou há um erro: {str(e)}. Prosseguindo com a criação dos dados.")

        # Popula os dados iniciais
        logger.info("Populando dados iniciais no banco")
        locais = [
            LocalAtendimento(
                nome="Centro de Saúde Camama",
                endereco="Luanda, Camama",
                tipo="Saúde"
            ),
            LocalAtendimento(
                nome="Posto de Identificação Luanda",
                endereco="Luanda, Centro",
                tipo="Documentação"
            ),
        ]
        db.session.add_all(locais)
        db.session.commit()
        
        servicos = [
            Servico(
                nome="Vacinação Infantil",
                descricao="Vacinação para crianças",
                duracao_media=15,
                local_id=locais[0].id
            ),
            Servico(
                nome="Emissão de BI",
                descricao="Emissão de bilhete de identidade",
                duracao_media=20,
                local_id=locais[1].id
            ),
        ]
        db.session.add_all(servicos)
        db.session.commit()
        
        queues = [
            Queue(
                service="Vacinação Infantil",
                servico_id=servicos[0].id,
                sector="Saúde",
                department="Centro de Saúde Camama",
                institution="Ministério da Saúde",
                open_time=time(8, 0),
                daily_limit=50,
                avg_wait_time=15
            ),
            Queue(
                service="Emissão de BI",
                servico_id=servicos[1].id,
                sector="Documentação",
                department="Posto de Identificação Luanda",
                institution="Ministério da Justiça",
                open_time=time(9, 0),
                daily_limit=30,
                avg_wait_time=20
            ),
        ]
        db.session.add_all(queues)
        db.session.commit()
        
        slots = [
            SlotAgendamento(
                servico_id=servicos[0].id,
                data_horario=datetime.now(UTC) + timedelta(days=1, hours=9),
                capacidade_maxima=5
            ),
            SlotAgendamento(
                servico_id=servicos[1].id,
                data_horario=datetime.now(UTC) + timedelta(days=1, hours=10),
                capacidade_maxima=3
            ),
        ]
        db.session.add_all(slots)
        db.session.commit()
        
        tickets = [
            Ticket(
                queue_id=queues[0].id,
                user_id="user1",
                ticket_number=1,
                qr_code=f"QR-{uuid.uuid4().hex[:8]}",
                issued_at=datetime.now(UTC) - timedelta(minutes=10),
                priority=1,
                is_physical=False
            ),
            Ticket(
                queue_id=queues[1].id,
                user_id="user2",
                ticket_number=1,
                qr_code=f"QR-{uuid.uuid4().hex[:8]}",
                issued_at=datetime.now(UTC) - timedelta(minutes=5),
                priority=0,
                is_physical=True,
                expires_at=datetime.now(UTC) + timedelta(minutes=25)
            ),
        ]
        queues[0].active_tickets += 1
        queues[1].active_tickets += 1
        db.session.add_all(tickets)
        db.session.commit()
        
        feedback = [
            Feedback(
                user_id="user1",
                ticket_id=tickets[0].id,
                nota=4,
                comentario="Atendimento rápido",
                data=datetime.now(UTC)
            ),
        ]
        db.session.add_all(feedback)
        db.session.commit()
        
        logger.info("Dados iniciais inseridos com sucesso: 2 locais, 2 serviços, 2 filas, 2 slots, 2 tickets, 1 feedback")

app = create_app()

with app.app_context():
    populate_initial_data()

if __name__ == '__main__':
    if 'RENDER' not in os.environ:
        logger.info("Iniciando a aplicação Facilita 2.0 com SocketIO (localmente)")
        socketio.run(app, host='0.0.0.0', port=5000, debug=True)
    else:
        logger.info("Iniciando a aplicação Facilita 2.0 no Render com gunicorn")