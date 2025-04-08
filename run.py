# run.py
from app import create_app, db
from app.models import Queue
from datetime import time
import uuid

app = create_app()

def populate_initial_data():
    with app.app_context():
        # Verifica se já existem dados
        if Queue.query.count() > 0:
            print("Dados iniciais já existem.")
            return
        
        # Dados fictícios
        services = [
            {
                'service': 'Vacinação Infantil',
                'sector': 'Saúde',
                'department': 'Centro de Saúde Camama',
                'institution': 'Ministério da Saúde',
                'open_time': time(7, 0),  # 07:00
                'daily_limit': 50
            },
            {
                'service': 'Emissão de Bilhete de Identidade',
                'sector': 'Documentação',
                'department': 'Posto de Identificação Civil Luanda',
                'institution': 'Ministério da Justiça',
                'open_time': time(8, 0),  # 08:00
                'daily_limit': 30
            },
            {
                'service': 'Matrícula Escolar',
                'sector': 'Educação',
                'department': 'Escola Primária Cazenga',
                'institution': 'Ministério da Educação',
                'open_time': time(7, 30),  # 07:30
                'daily_limit': 40
            },
            {
                'service': 'Pagamento de Energia',
                'sector': 'Serviços Públicos',
                'department': 'Agência ENDE Kilamba',
                'institution': 'Empresa Nacional de Distribuição de Eletricidade',
                'open_time': time(9, 0),  # 09:00
                'daily_limit': 60
            },
            {
                'service': 'Registo de Nascimento',
                'sector': 'Documentação',
                'department': 'Conservatória do Rangel',
                'institution': 'Ministério da Justiça',
                'open_time': time(8, 30),  # 08:30
                'daily_limit': 25
            },
            {
                'service': 'Consulta Médica',
                'sector': 'Saúde',
                'department': 'Hospital Municipal Viana',
                'institution': 'Ministério da Saúde',
                'open_time': time(7, 0),  # 07:00
                'daily_limit': 20
            },
            {
                'service': 'Licenciamento de Veículos',
                'sector': 'Transportes',
                'department': 'Direção Provincial de Trânsito Luanda',
                'institution': 'Ministério dos Transportes',
                'open_time': time(8, 0),  # 08:00
                'daily_limit': 35
            }
        ]

        for service_data in services:
            queue = Queue(
                id=str(uuid.uuid4()),
                service=service_data['service'],
                sector=service_data['sector'],
                department=service_data['department'],
                institution=service_data['institution'],
                open_time=service_data['open_time'],
                daily_limit=service_data['daily_limit']
            )
            db.session.add(queue)
        
        db.session.commit()
        print("Dados iniciais inseridos com sucesso!")

# Criar tabelas e popular dados iniciais
with app.app_context():
    db.create_all()
    populate_initial_data()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)