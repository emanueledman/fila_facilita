import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO
from dotenv import load_dotenv
import threading
import time
from logging.handlers import RotatingFileHandler
import sqlalchemy

load_dotenv()

# Instância global de SQLAlchemy e SocketIO
db = SQLAlchemy()
socketio = SocketIO(cors_allowed_origins="*", async_mode='threading', engineio_logger=True)

def create_app():
    app = Flask(__name__)
    
    from .config import get_config
    config = get_config()
    app.config.from_object(config)
    
    # Configuração de logging
    log_formatter = logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    )
    log_handler = RotatingFileHandler(
        'facilita.log', maxBytes=1024*1024, backupCount=10
    )
    log_handler.setFormatter(log_formatter)
    log_handler.setLevel(logging.INFO)
    
    app.logger.handlers.clear()
    app.logger.addHandler(log_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info(f"Iniciando aplicação com banco de dados: {app.config['SQLALCHEMY_DATABASE_URI']}")
    
    # Teste de conexão com o banco de dados
    try:
        app.logger.info(f"Tentando criar engine com URL: {app.config['SQLALCHEMY_DATABASE_URI']}")
        engine = sqlalchemy.create_engine(app.config['SQLALCHEMY_DATABASE_URI'])
        with engine.connect() as conn:
            app.logger.info("Conexão com o banco de dados estabelecida com sucesso")
    except Exception as e:
        app.logger.error(f"Falha ao conectar ao banco de dados: {str(e)}")
        raise

    # Inicializa o db com o app
    db.init_app(app)
    
    # Importa os modelos após inicializar o db
    try:
        from .models import LocalAtendimento, Servico, Queue, Ticket, SlotAgendamento, Feedback
    except Exception as e:
        app.logger.error(f"Erro ao importar modelos: {str(e)}")
        raise
    
    # Inicializa o SocketIO
    try:
        socketio.init_app(app)
        app.logger.info("SocketIO inicializado com sucesso")
    except Exception as e:
        app.logger.error(f"Erro ao inicializar SocketIO: {str(e)}")
        raise

    # Importa e registra as rotas após modelos e db estarem prontos
    try:
        from .routes.queue_routes import init_queue_routes
        from .routes.slot_routes import init_slot_routes
        from .routes.integration_routes import init_integration_routes
        
        init_queue_routes(app)
        init_slot_routes(app)
        init_integration_routes(app)
        app.logger.info("Rotas inicializadas com sucesso")
    except Exception as e:
        app.logger.error(f"Erro ao inicializar rotas: {str(e)}")
        raise

    # Tarefa em background para notificações proativas
    def run_background_tasks():
        while True:
            try:
                with app.app_context():
                    from .services.queue_service import QueueService
                    from .services.slot_service import SlotService
                    QueueService.check_proactive_notifications()
                    SlotService.check_proactive_notifications()
                    app.logger.info("Verificação de notificações proativas executada com sucesso")
            except Exception as e:
                app.logger.error(f"Erro nas tarefas assíncronas: {str(e)}")
            time.sleep(60)

    threading.Thread(target=run_background_tasks, daemon=True).start()

    # Eventos do SocketIO
    @socketio.on('connect')
    def handle_connect():
        app.logger.info("Cliente WebSocket conectado")
        socketio.emit('status', {'message': 'Conexão estabelecida com Facilita 2.0'})

    @socketio.on('disconnect')
    def handle_disconnect():
        app.logger.info("Cliente WebSocket desconectado")

    @socketio.on('join_queue')
    def handle_join_queue(data):
        queue_id = data.get('queue_id')
        user_id = data.get('user_id')
        app.logger.info(f"Usuário {user_id} entrou na fila {queue_id} via WebSocket")
        socketio.emit('queue_update', {'queue_id': queue_id, 'message': f'Usuário {user_id} entrou na fila'}, broadcast=True)

    @socketio.on('join_slot')
    def handle_join_slot(data):
        slot_id = data.get('slot_id')
        user_id = data.get('user_id')
        app.logger.info(f"Usuário {user_id} reservou o slot {slot_id} via WebSocket")
        socketio.emit('slot_update', {'slot_id': slot_id, 'message': f'Usuário {user_id} reservou o slot'}, broadcast=True)

    return app