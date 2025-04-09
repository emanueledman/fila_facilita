import eventlet
eventlet.monkey_patch()  # Corrige problemas com eventlet no Gunicorn
import logging
from app import create_app, db, socketio
from app.models import LocalAtendimento, Servico, Queue, SlotAgendamento, Ticket, Feedback
from app.services.queue_service import QueueService
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
        
        # Em desenvolvimento (local), recria o banco; no Render, apenas cria tabelas se necessário
        if 'RENDER' not in os.environ:
            logger.info("Recriando o banco de dados (apenas localmente)")
            db.drop_all()
            db.create_all()
        else:
            logger.info("Garantindo que as tabelas existam no Render")
            db.create_all()
        
        # Verifica se há dados na tabela Queue
        if Queue.query.count() > 0:
            logger.info("Dados iniciais já existem, pulando população.")
            return

        # Popula os dados iniciais
        logger.info("Populando dados iniciais no banco")
        
        # Mais de 10 locais de atendimento
        locais = [
            LocalAtendimento(nome="Centro de Saúde Camama", endereco="Luanda, Camama", tipo="Saúde"),
            LocalAtendimento(nome="Posto de Identificação Luanda", endereco="Luanda, Centro", tipo="Documentação"),
            LocalAtendimento(nome="Hospital Geral Kilamba", endereco="Luanda, Kilamba", tipo="Saúde"),
            LocalAtendimento(nome="Conservatória do Registo Civil", endereco="Luanda, Maianga", tipo="Documentação"),
            LocalAtendimento(nome="Posto de Vacinação Viana", endereco="Luanda, Viana", tipo="Saúde"),
            LocalAtendimento(nome="Ministério das Finanças", endereco="Luanda, Marginal", tipo="Finanças"),
            LocalAtendimento(nome="Posto Policial Cazenga", endereco="Luanda, Cazenga", tipo="Segurança"),
            LocalAtendimento(nome="Universidade Agostinho Neto", endereco="Luanda, Camama", tipo="Educação"),
            LocalAtendimento(nome="Tribunal Provincial de Luanda", endereco="Luanda, Ingombota", tipo="Justiça"),
            LocalAtendimento(nome="Posto de Passaportes", endereco="Luanda, Talatona", tipo="Documentação"),
            LocalAtendimento(nome="Clínica Sagrada Esperança", endereco="Luanda, Ilha", tipo="Saúde"),
            LocalAtendimento(nome="Câmara Municipal de Belas", endereco="Luanda, Belas", tipo="Administração"),
        ]
        db.session.add_all(locais)
        db.session.commit()
        
        # Serviços variados
        servicos = [
            Servico(nome="Vacinação Infantil", descricao="Vacinação para crianças", duracao_media=15, local_id=locais[0].id),
            Servico(nome="Emissão de BI", descricao="Emissão de bilhete de identidade", duracao_media=20, local_id=locais[1].id),
            Servico(nome="Consulta Geral", descricao="Consulta médica geral", duracao_media=30, local_id=locais[2].id),
            Servico(nome="Registo de Nascimento", descricao="Registo civil de nascimento", duracao_media=25, local_id=locais[3].id),
            Servico(nome="Vacinação Adultos", descricao="Vacinação para adultos", duracao_media=10, local_id=locais[4].id),
            Servico(nome="Pagamento de Impostos", descricao="Pagamento de impostos fiscais", duracao_media=15, local_id=locais[5].id),
            Servico(nome="Registo Criminal", descricao="Emissão de registo criminal", duracao_media=20, local_id=locais[6].id),
            Servico(nome="Matrícula Universitária", descricao="Matrícula em cursos", duracao_media=30, local_id=locais[7].id),
            Servico(nome="Audiência Judicial", descricao="Agendamento de audiências", duracao_media=60, local_id=locais[8].id),
            Servico(nome="Emissão de Passaporte", descricao="Emissão de passaporte", duracao_media=25, local_id=locais[9].id),
            Servico(nome="Exames Médicos", descricao="Exames de rotina", duracao_media=40, local_id=locais[10].id),
            Servico(nome="Licenciamento Municipal", descricao="Licenças municipais", duracao_media=20, local_id=locais[11].id),
        ]
        db.session.add_all(servicos)
        db.session.commit()
        
        # Filas para serviços
        queues = [
            Queue(service="Vacinação Infantil", servico_id=servicos[0].id, sector="Saúde", department="Centro de Saúde Camama", institution="Ministério da Saúde", open_time=time(8, 0), daily_limit=50, avg_wait_time=15, active_tickets=0, current_ticket=0),
            Queue(service="Emissão de BI", servico_id=servicos[1].id, sector="Documentação", department="Posto de Identificação Luanda", institution="Ministério da Justiça", open_time=time(9, 0), daily_limit=30, avg_wait_time=20, active_tickets=0, current_ticket=0),
            Queue(service="Consulta Geral", servico_id=servicos[2].id, sector="Saúde", department="Hospital Geral Kilamba", institution="Ministério da Saúde", open_time=time(7, 30), daily_limit=40, avg_wait_time=30, active_tickets=0, current_ticket=0),
            Queue(service="Registo de Nascimento", servico_id=servicos[3].id, sector="Documentação", department="Conservatória do Registo Civil", institution="Ministério da Justiça", open_time=time(8, 30), daily_limit=25, avg_wait_time=25, active_tickets=0, current_ticket=0),
            Queue(service="Vacinação Adultos", servico_id=servicos[4].id, sector="Saúde", department="Posto de Vacinação Viana", institution="Ministério da Saúde", open_time=time(9, 0), daily_limit=60, avg_wait_time=10, active_tickets=0, current_ticket=0),
            Queue(service="Pagamento de Impostos", servico_id=servicos[5].id, sector="Finanças", department="Ministério das Finanças", institution="Ministério das Finanças", open_time=time(8, 0), daily_limit=100, avg_wait_time=15, active_tickets=0, current_ticket=0),
            Queue(service="Registo Criminal", servico_id=servicos[6].id, sector="Segurança", department="Posto Policial Cazenga", institution="Ministério do Interior", open_time=time(8, 0), daily_limit=20, avg_wait_time=20, active_tickets=0, current_ticket=0),
            Queue(service="Licenciamento Municipal", servico_id=servicos[11].id, sector="Administração", department="Câmara Municipal de Belas", institution="Administração Local", open_time=time(9, 0), daily_limit=30, avg_wait_time=20, active_tickets=0, current_ticket=0),
        ]
        db.session.add_all(queues)
        db.session.commit()
        
        # Slots de agendamento
        slots = [
            SlotAgendamento(servico_id=servicos[7].id, data_horario=datetime.now(UTC) + timedelta(days=1, hours=9), capacidade_maxima=10, capacidade_atual=0, status="aberto"),
            SlotAgendamento(servico_id=servicos[7].id, data_horario=datetime.now(UTC) + timedelta(days=1, hours=14), capacidade_maxima=10, capacidade_atual=0, status="aberto"),
            SlotAgendamento(servico_id=servicos[8].id, data_horario=datetime.now(UTC) + timedelta(days=2, hours=10), capacidade_maxima=5, capacidade_atual=0, status="aberto"),
            SlotAgendamento(servico_id=servicos[9].id, data_horario=datetime.now(UTC) + timedelta(days=1, hours=11), capacidade_maxima=8, capacidade_atual=0, status="aberto"),
            SlotAgendamento(servico_id=servicos[9].id, data_horario=datetime.now(UTC) + timedelta(days=2, hours=9), capacidade_maxima=8, capacidade_atual=0, status="aberto"),
            SlotAgendamento(servico_id=servicos[10].id, data_horario=datetime.now(UTC) + timedelta(days=1, hours=8), capacidade_maxima=15, capacidade_atual=0, status="aberto"),
            SlotAgendamento(servico_id=servicos[10].id, data_horario=datetime.now(UTC) + timedelta(days=1, hours=13), capacidade_maxima=15, capacidade_atual=0, status="aberto"),
        ]
        db.session.add_all(slots)
        db.session.commit()
        
        # Tickets iniciais usando QueueService para consistência
        tickets = [
            QueueService.add_to_queue("Vacinação Infantil", "user1", priority=1, is_physical=False),
            QueueService.add_to_queue("Emissão de BI", "user2", priority=0, is_physical=True),
            QueueService.add_to_queue("Consulta Geral", "user3", priority=0, is_physical=False),
        ]
        
        # Feedback inicial
        feedback = [
            Feedback(user_id="user1", ticket_id=tickets[0].id, nota=4, comentario="Atendimento rápido", data=datetime.now(UTC)),
        ]
        db.session.add_all(feedback)
        db.session.commit()
        
        logger.info("Dados iniciais inseridos com sucesso: 12 locais, 12 serviços, 8 filas, 7 slots, 3 tickets, 1 feedback")

app = create_app()

with app.app_context():
    populate_initial_data()

if __name__ == '__main__':
    if 'RENDER' not in os.environ:
        logger.info("Iniciando a aplicação Facilita 2.0 com SocketIO (localmente)")
        socketio.run(app, host='0.0.0.0', port=5000, debug=True)
    else:
        logger.info("Iniciando a aplicação Facilita 2.0 no Render com gunicorn")