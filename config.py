import os
from datetime import datetime, time
from dotenv import load_dotenv

load_dotenv()

STRAVA_CLIENT_ID = os.environ.get('STRAVA_CLIENT_ID', 'your_client_id')
STRAVA_CLIENT_SECRET = os.environ.get('STRAVA_CLIENT_SECRET', 'your_client_secret')
STRAVA_REDIRECT_URI = os.environ.get('STRAVA_REDIRECT_URI', 'http://localhost:5555/callback')

CLUB_CONFIGS = {
    'Rotterdam': {
        'days': [6],  # Sunday = 6 (Monday = 0)
        'start_time': datetime.strptime('10:30', '%H:%M').time(),
        'end_time': datetime.strptime('12:30', '%H:%M').time(),
        'city': 'Rotterdam'
    }
}

SQLALCHEMY_DATABASE_URI = 'postgresql://strava:strava_pass@localhost:5432/strava_board'
SQLALCHEMY_TRACK_MODIFICATIONS = False
