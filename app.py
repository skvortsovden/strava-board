import os
from flask import Flask, redirect, request, session, render_template, url_for
from datetime import datetime, timedelta
import pytz
import requests
from config import STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REDIRECT_URI
from dotenv import load_dotenv
from models.activity import Activity
from models.run import Run
from models import db
from models.user import User
from functools import wraps
from collections import defaultdict
from sqlalchemy import extract

load_dotenv()
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))

# Configure PostgreSQL (works with Render's DATABASE_URL)
database_url = os.environ.get('DATABASE_URL', 'sqlite:///local.db')
# Fix postgres:// to postgresql:// for SQLAlchemy compatibility
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
# Force use of psycopg (not psycopg2) driver
if database_url.startswith('postgresql://') and '+psycopg' not in database_url:
    database_url = database_url.replace('postgresql://', 'postgresql+psycopg://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# Create tables on startup
with app.app_context():
    db.create_all()


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

def make_aware(dt):
    if dt.tzinfo is None:
        return dt.replace(tzinfo=pytz.UTC)
    return dt

def group_runs_by_week(runs, week_ranges):
    """Group runs by week"""
    weekly_runs = []
    for week_range in week_ranges:
        week_start = make_aware(week_range['start'])
        week_end = make_aware(week_range['end'])
        week_runs = []
        for run in runs:
            run_start = make_aware(run.start_date)
            if week_start <= run_start < week_end:
                week_runs.append(run)
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

def store_runs(user, activities):
    for act in activities:
        if act['type'] != 'Run':
            continue
        # Map to Activity dataclass
        activity = Activity.from_strava_json(act)
        activity.detect_club_run()  # Set club_name in Activity

        # Check if run already exists
        run = Run.query.filter_by(strava_activity_id=str(activity.id)).first()
        if not run:
            run = Run(
                user_id=user.id,
                strava_activity_id=str(activity.id),
                name=activity.name,
                start_date=activity.start_date,
                start_date_local=activity.start_date_local,
                distance=activity.distance,
                moving_time=activity.moving_time,
                club_name=activity.club_name,
                raw_json=act
            )
            db.session.add(run)
        else:
            run.name = activity.name
            run.start_date = activity.start_date
            run.start_date_local = activity.start_date_local
            run.distance = activity.distance
            run.moving_time = activity.moving_time
            run.club_name = activity.club_name
            run.raw_json = act
    db.session.commit()

# --- Routes ---

@app.route('/')
def index():
    access_token = session.get('access_token')
    user_id = session.get('user_id')
    if not access_token or not user_id:
        return render_template('index.html', authorized=False)
    
    user = User.query.get(user_id)
    # Use PostgreSQL query instead of Firestore
    runs = Run.query.filter_by(user_id=user.id).order_by(Run.start_date).all()
    week_ranges = get_year_week_ranges()
    weekly_runs = group_runs_by_week(runs, week_ranges)
    my_clubs = get_unique_clubs(runs)
    return render_template(
        'index.html',
        authorized=True,
        weekly_runs=weekly_runs,
        current_year=get_current_year(),
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
    try:
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
            return f"Token exchange failed: {token_res.text}", 400
        
        data = token_res.json()
        access_token = data['access_token']
        refresh_token = data['refresh_token']
        expires_at = datetime.utcfromtimestamp(data['expires_at'])

        # Fetch user profile from Strava
        profile_res = requests.get(
            "https://www.strava.com/api/v3/athlete",
            headers={'Authorization': f'Bearer {access_token}'}
        )
        if profile_res.status_code != 200:
            return f"Failed to fetch user profile: {profile_res.text}", 400
        
        profile = profile_res.json()
        strava_id = str(profile['id'])
        name = profile.get('firstname', '') + ' ' + profile.get('lastname', '')
        profile_photo = profile.get('profile', '')  # Strava's profile photo URL

        user = User.query.filter_by(strava_id=strava_id).first()
        if not user:
            user = User(
                strava_id=strava_id,
                name=name,
                profile_photo=profile_photo,  # Save photo
                access_token=access_token,
                refresh_token=refresh_token,
                token_expires_at=expires_at
            )
            db.session.add(user)
        else:
            user.name = name
            user.profile_photo = profile_photo  # Update photo
            user.access_token = access_token
            user.refresh_token = refresh_token
            user.token_expires_at = expires_at
        db.session.commit()

        session['access_token'] = access_token
        session['user_id'] = user.id

        # Fetch all activities for the user (e.g., for the last 2 years)
        after_date = get_after_date(get_current_year() - 1)
        activities = fetch_activities(access_token, after_date)
        if activities:
            store_runs(user, activities)

        return redirect('/')
    
    except Exception as e:
        return f"Callback error: {str(e)}", 500

@app.route('/club/<club_slug>')
@login_required
def club_runs(club_slug):
    club_name = slug_to_name(club_slug)
    user_id = session.get('user_id')
    if not user_id:
        return render_template('index.html', authorized=False)
    runs = Run.query.filter_by(user_id=user_id, club_name=club_name).order_by(Run.start_date).all()
    if not runs:
        return f"No runs found for club: {club_name}", 404
    monthly_runs = group_runs_by_month(runs)
    return render_template(
        'club.html',
        authorized=True,
        monthly_runs=monthly_runs,
        current_year=get_current_year(),
        club_name=club_name
    )

@app.route('/my-clubs')
@login_required
def my_clubs_page():
    user_id = session.get('user_id')
    if not user_id:
        return render_template('my-clubs.html', authorized=False, my_clubs=[])
    runs = Run.query.filter_by(user_id=user_id).all()
    my_clubs = get_unique_clubs(runs)
    return render_template(
        'my-clubs.html',
        authorized=True,
        my_clubs=my_clubs
    )

@app.route('/my-leaderboards')
@login_required
def leaderboards():
    user_id = session.get('user_id')
    if not user_id:
        return render_template('my-leaderboards.html', authorized=False, my_clubs=[])
    runs = Run.query.filter_by(user_id=user_id).all()
    my_clubs = get_unique_clubs(runs)
    return render_template(
        'my-leaderboards.html',
        authorized=True,
        my_clubs=my_clubs
    )

@app.route('/<club_slug>/leaderboard')
@login_required
def club_leaderboard(club_slug):
    from sqlalchemy import extract
    club_name = slug_to_name(club_slug)
    current_year = get_current_year()
    # Query all runs for this club
    runs = (
        db.session.query(Run, User)
        .join(User, Run.user_id == User.id)
        .filter(
            Run.club_name == club_name,
            extract('year', Run.start_date_local) == current_year
        )
        .all()
    )

    # Group by user and month
    leaderboard = defaultdict(lambda: defaultdict(list))  # {user: {month: [runs]}}

    for run, user in runs:
        month = run.start_date_local.strftime('%Y-%m') if run.start_date_local else 'unknown'
        leaderboard[user][month].append(run)

    # Prepare leaderboard data
    leaderboard_data = []
    for user, months in leaderboard.items():
        for month, user_runs in months.items():
            total_runs = len(user_runs)
            total_km = sum(r.distance or 0 for r in user_runs) / 1000
            total_time = sum(r.moving_time or 0 for r in user_runs)
            avg_pace = (
                (total_time / 60) / total_km if total_km > 0 else 0
            )  # min/km
            leaderboard_data.append({
                'runner': user,
                'month': month,
                'total_runs': total_runs,
                'total_km': total_km,
                'total_time': total_time,
                'avg_pace': avg_pace,
            })

    # Sort by month, then by total_km descending
    leaderboard_data.sort(key=lambda x: (x['month'], -x['total_km']))

    # Group leaderboard_data by month for the template
    month_groups = defaultdict(lambda: defaultdict(list))  # {month: {user: [runs]}}

    for run, user in runs:
        month = run.start_date_local.strftime('%Y-%m')
        month_groups[month][user].append(run)

    leaderboard_data_grouped = []
    for month, user_runs in month_groups.items():
        rows = []
        for user, runs_list in user_runs.items():
            run_days = set(r.start_date_local.date() for r in runs_list if r.start_date_local)
            total_run_days = len(run_days)
            total_km = sum(r.distance or 0 for r in runs_list) / 1000
            total_time = sum(r.moving_time or 0 for r in runs_list)
            avg_pace = (total_time / 60) / total_km if total_km > 0 else 0
            rows.append({
                'runner': user,
                'total_runs': len(runs_list),
                'total_run_days': total_run_days,
                'total_km': total_km,
                'total_time': total_time,
                'avg_pace': avg_pace,
            })
        # Sort: first by total_run_days desc, then by total_km desc
        rows.sort(key=lambda x: (-x['total_run_days'], -x['total_km']))
        leaderboard_data_grouped.append({
            'month': month,
            'rows': rows
        })

    # Sort months reverse (latest first)
    leaderboard_data_grouped.sort(key=lambda x: x['month'], reverse=True)

    return render_template(
        'club-leaderboard.html',
        club_name=club_name,
        leaderboard_data=leaderboard_data_grouped
    )

@app.route('/debug')
def debug():
    try:
        # Test database connection
        user_count = User.query.count()
        run_count = Run.query.count()
        return f"Database OK - Users: {user_count}, Runs: {run_count}"
    except Exception as e:
        return f"Database Error: {str(e)}", 500

@app.template_filter('datetime')
def format_datetime(value, fmt='%B %Y'):
    from datetime import datetime
    return datetime.strptime(value, '%Y-%m').strftime(fmt)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Create tables if they don't exist
    app.run(debug=True, host='0.0.0.0', port=5555)
