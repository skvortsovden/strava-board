from . import db

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    strava_id = db.Column(db.String, unique=True, nullable=False)
    name = db.Column(db.String)
    profile_photo = db.Column(db.String)
    access_token = db.Column(db.String, nullable=False)
    refresh_token = db.Column(db.String, nullable=False)
    token_expires_at = db.Column(db.DateTime, nullable=False)