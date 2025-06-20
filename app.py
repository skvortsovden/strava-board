import os
from flask import Flask, redirect, request, session, render_template, url_for
from datetime import datetime, timedelta
import pytz
import requests
from config import STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REDIRECT_URI
from dotenv import load_dotenv
from models.activity import Activity
from functools import wraps

load_dotenv()
app = Flask(__name__)
app.secret_key = os.urandom(24)

# --- Utility Functions ---

def get_current_year():
    return datetime.now(pytz.UTC).year

def get_after_date(year):
    return int(datetime(year, 1, 1, tzinfo=pytz.UTC).timestamp())

def fetch_activities(access_token, after_date):
    headers = {'Authorization': f'Bearer {access_token}'}
    res = requests.get(
        "https://www.strava.com/api/v3/athlete/activities",
        params={'after': after_date, 'per_page': 200},
        headers=headers
    )
    if res.status_code != 200:
        return None
    return res.json()

def get_runs(activities):
    return [
        Activity.from_strava_json(act)
        for act in activities
        if act['type'] == 'Run'
    ]

def get_year_week_ranges():
    """All week ranges (Monday-Sunday) for the current year"""
    current_year = get_current_year()
    year_start = datetime(current_year, 1, 1, tzinfo=pytz.UTC)
    while year_start.weekday() != 0:
        year_start += timedelta(days=1)
    week_ranges = []
    current_start = year_start
    while current_start.year == current_year:
        week_end = current_start + timedelta(days=7)
        week_num = current_start.isocalendar()[1]
        week_ranges.append({
            'start': current_start,
            'end': week_end,
            'week_num': week_num
        })
        current_start = week_end
    return week_ranges

def group_runs_by_week(runs, week_ranges):
    """Group runs by week"""
    weekly_runs = []
    for week_range in week_ranges:
        week_runs = [
            run for run in runs
            if week_range['start'].replace(tzinfo=pytz.UTC) <= run.start_date < week_range['end'].replace(tzinfo=pytz.UTC)
        ]
        if week_runs:
            weekly_runs.append({
                'week_num': week_range['week_num'],
                'start_date': week_range['start'],
                'end_date': week_range['end'],
                'runs': week_runs
            })
    return weekly_runs

def group_runs_by_month(runs):
    """Group runs by month"""
    from collections import defaultdict
    monthly_runs = defaultdict(list)
    for run in runs:
        month_key = run.start_date.strftime('%Y-%m')
        monthly_runs[month_key].append(run)
    grouped = []
    for month in sorted(monthly_runs.keys()):
        grouped.append({
            'month': month,
            'runs': sorted(monthly_runs[month], key=lambda r: r.start_date)
        })
    return grouped

def get_unique_clubs(runs):
    """Unique club names from runs"""
    return sorted(set(run.club_name for run in runs if run.club_name))

def slug_to_name(slug):
    return slug.replace('-', ' ').title()

def name_to_slug(name):
    return name.lower().replace(' ', '-')

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('access_token'):
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# --- Routes ---

@app.route('/')
def index():
    access_token = session.get('access_token')
    if not access_token:
        return render_template('index.html', authorized=False)
    current_year = get_current_year()
    after_date = get_after_date(current_year)
    activities = fetch_activities(access_token, after_date)
    if activities is None:
        return "Failed to fetch activities", 400
    runs = get_runs(activities)
    week_ranges = get_year_week_ranges()
    weekly_runs = group_runs_by_week(runs, week_ranges)
    my_clubs = get_unique_clubs(runs)
    return render_template(
        'index.html',
        authorized=True,
        weekly_runs=weekly_runs,
        current_year=current_year,
        my_clubs=my_clubs,
        timedelta=timedelta
    )

@app.route('/login')
def login():
    return redirect(
        f"https://www.strava.com/oauth/authorize?client_id={STRAVA_CLIENT_ID}"
        f"&response_type=code&redirect_uri={STRAVA_REDIRECT_URI}"
        f"&approval_prompt=auto&scope=activity:read"
    )

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code:
        return "No code provided", 400
    token_res = requests.post("https://www.strava.com/oauth/token", data={
        'client_id': STRAVA_CLIENT_ID,
        'client_secret': STRAVA_CLIENT_SECRET,
        'code': code,
        'grant_type': 'authorization_code'
    })
    if token_res.status_code != 200:
        return "Token exchange failed", 400
    data = token_res.json()
    session['access_token'] = data['access_token']
    return redirect('/')

@app.route('/club/<club_slug>')
@login_required
def club_runs(club_slug):
    club_name = slug_to_name(club_slug)
    access_token = session.get('access_token')
    if not access_token:
        return render_template('index.html', authorized=False)
    current_year = get_current_year()
    after_date = get_after_date(current_year)
    activities = fetch_activities(access_token, after_date)
    if activities is None:
        return "Failed to fetch activities", 400
    runs = get_runs(activities)
    club_runs = [run for run in runs if run.club_name == club_name]
    if not club_runs:
        return f"No runs found for club: {club_name}", 404
    monthly_runs = group_runs_by_month(club_runs)
    return render_template(
        'club.html',
        authorized=True,
        monthly_runs=monthly_runs,
        current_year=current_year,
        club_name=club_name
    )

@app.route('/my-clubs')
@login_required
def my_clubs_page():
    access_token = session.get('access_token')
    if not access_token:
        return render_template('my-clubs.html', authorized=False, my_clubs=[])
    current_year = get_current_year()
    after_date = get_after_date(current_year)
    activities = fetch_activities(access_token, after_date)
    if activities is None:
        return "Failed to fetch activities", 400
    runs = get_runs(activities)
    my_clubs = get_unique_clubs(runs)
    return render_template(
        'my-clubs.html',
        authorized=True,
        my_clubs=my_clubs
    )

@app.route('/my-leaderboards')
@login_required
def leaderboards():
    access_token = session.get('access_token')
    if not access_token:
        return render_template('my-leaderboards.html', authorized=False, my_clubs=[])
    current_year = get_current_year()
    after_date = get_after_date(current_year)
    activities = fetch_activities(access_token, after_date)
    if activities is None:
        return "Failed to fetch activities", 400
    runs = get_runs(activities)
    my_clubs = get_unique_clubs(runs)
    return render_template(
        'my-leaderboards.html',
        authorized=True,
        my_clubs=my_clubs
    )

@app.route('/<club_slug>/leaderboard')
@login_required
def club_leaderboard(club_slug):
    club_name = slug_to_name(club_slug)
    return render_template(
        'club-leaderboard.html',
        club_name=club_name
    )

@app.template_filter('datetime')
def format_datetime(value, fmt='%B %Y'):
    from datetime import datetime
    return datetime.strptime(value, '%Y-%m').strftime(fmt)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5555)
