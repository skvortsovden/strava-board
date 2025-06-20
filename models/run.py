from datetime import datetime
from sqlalchemy.dialects.postgresql import JSONB
from . import db

class Run(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    strava_activity_id = db.Column(db.String, unique=True, nullable=False)
    name = db.Column(db.String)
    start_date = db.Column(db.DateTime)         # UTC time
    start_date_local = db.Column(db.DateTime)   # Local time
    distance = db.Column(db.Float)              # In meters
    moving_time = db.Column(db.Integer)            # In seconds
    club_name = db.Column(db.String)
    raw_json = db.Column(JSONB)                 # Optional: for debugging/future use

    @property
    def pace_per_km(self) -> float:
        """Calculate pace in minutes per kilometer"""
        if not self.distance or not self.moving_time:
            return 0
        kilometers = self.distance / 1000
        hours = self.moving_time / 3600
        return (hours * 60) / kilometers if kilometers else 0

    def format_duration(self) -> str:
        """Format moving time as HH:MM:SS"""
        hours = self.moving_time // 3600
        minutes = (self.moving_time % 3600) // 60
        seconds = self.moving_time % 60
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

    def format_pace(self) -> str:
        """Format pace as MM:SS per kilometer"""
        pace = self.pace_per_km
        pace_minutes = int(pace)
        pace_seconds = int((pace - pace_minutes) * 60)
        return f"{pace_minutes}:{pace_seconds:02d}"

    def detect_club_run(self):
        """Detect if this is a club run based on day and time"""
        from config import CLUB_CONFIGS
        self.club_name = None
        run_date = self.start_date_local
        if run_date is None:
            return
        run_time = run_date.time()
        for club_name, config in CLUB_CONFIGS.items():
            if run_date.weekday() in config['days']:
                start = config['start_time']
                end = config['end_time']
                if start <= run_time <= end:
                    self.club_name = club_name
                    break