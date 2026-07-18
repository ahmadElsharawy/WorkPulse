# app.py
from workpulse import create_app
from workpulse.database import init_db, seed_data

app = create_app()

with app.app_context():
    init_db()
    seed_data()

if __name__ == '__main__':
    app.run(debug=True)
