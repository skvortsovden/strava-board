import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

STRAVA_CLIENT_ID = os.environ.get('STRAVA_CLIENT_ID', 'your_client_id')
STRAVA_CLIENT_SECRET = os.environ.get('STRAVA_CLIENT_SECRET', 'your_client_secret')
STRAVA_REDIRECT_URI = os.environ.get('STRAVA_REDIRECT_URI', 'http://localhost:5555/callback')

CLUB_CONFIGS = {
    'URC Rotterdam': {
        'days': ['Sunday'],  # Day names
        'time_window': {
            'start': '10:00',  # Start a bit earlier to catch your 10:23 run
            'end': '12:30'     # Keep the end time
        },
        'description': 'Ukrainian Running Club in Rotterdam. We run & eat cakes every Sunday.'
    }
}
