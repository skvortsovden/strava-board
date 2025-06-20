from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy(app)

class Run(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    strava_activity_id = db.Column(db.String, unique=True, nullable=False)
    name = db.Column(db.String)
    start_date = db.Column(db.DateTime)
    distance = db.Column(db.Float)
    duration = db.Column(db.Integer)
    club_name = db.Column(db.String)
    raw_json = db.Column(db.JSONB)  # Store full Strava activity for flexibility
    # Add more fields as needed