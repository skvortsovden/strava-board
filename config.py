import os

STRAVA_CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
STRAVA_CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")
STRAVA_REDIRECT_URI = "http://127.0.0.1:5555/callback"

CLUB_CONFIGS = {
    'Rotterdam Ukrainian Running Club': {
        'days': ['Sunday'],
        'time_window': {
            'start': '10:30',
            'end': '12:30'
        }
    },
    # Add more clubs as needed
}

SQLALCHEMY_DATABASE_URI = 'postgresql://strava:strava_pass@localhost:5432/strava_board'
SQLALCHEMY_TRACK_MODIFICATIONS = False
