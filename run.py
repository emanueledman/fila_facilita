# run.py
from app import create_app, db

app = create_app()

# Criar tabelas explicitamente antes de iniciar o servidor
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)