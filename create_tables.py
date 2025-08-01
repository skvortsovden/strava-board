import os
from flask import Flask
from models import db

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///local.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# Import all models so SQLAlchemy is aware of them
from models.user import User
from models.run import Run

with app.app_context():
    db.create_all()
    print("All tables created successfully.")