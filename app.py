import os
from flask import Flask, redirect, request, session, render_template, url_for
from datetime import datetime, timedelta
import pytz
import requests
from config import STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REDIRECT_URI, CLUB_CONFIGS
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

def refresh_access_token(user):
    """Refresh access token if expired"""
    try:
        if user.token_expires_at and datetime.utcnow() < user.token_expires_at:
            return user.access_token  # Token still valid
        
        if not user.refresh_token:
            return None  # No refresh token available
        
        # Request new access token
        token_res = requests.post("https://www.strava.com/oauth/token", data={
            'client_id': STRAVA_CLIENT_ID,
            'client_secret': STRAVA_CLIENT_SECRET,
            'refresh_token': user.refresh_token,
            'grant_type': 'refresh_token'
        })
        
        if token_res.status_code != 200:
            return None
        
        data = token_res.json()
        user.access_token = data['access_token']
        user.refresh_token = data['refresh_token']
        user.token_expires_at = datetime.utcfromtimestamp(data['expires_at'])
        db.session.commit()
        
        # Update session
        session['access_token'] = user.access_token
        
        return user.access_token
    except Exception as e:
        print(f"Error refreshing token: {e}")
        return None

def create_minimal_activity_for_club_detection(run):
    """Create a minimal Activity object for club detection from a Run"""
    return Activity(
        id=int(run.strava_activity_id),
        name=run.name,
        distance=run.distance or 0,
        moving_time=run.moving_time or 0,
        elapsed_time=run.moving_time or 0,
        total_elevation_gain=0,
        type='Run',
        start_date=run.start_date,
        start_date_local=run.start_date_local,
        timezone='UTC',
        start_latlng=None,
        end_latlng=None,
        average_speed=0,
        max_speed=0,
        average_heartrate=None,
        max_heartrate=None,
        kudos_count=0,
        athlete_count=0,
        private=False,
        resource_state=2,
        athlete={},
        sport_type='Run',
        workout_type=None,
        utc_offset=0,
        location_city=None,
        location_state=None,
        location_country=None,
        achievement_count=0,
        comment_count=0,
        photo_count=0,
        map={},
        trainer=False,
        commute=False,
        manual=False,
        visibility='everyone',
        flagged=False,
        gear_id=None,
        average_cadence=None,
        average_watts=None,
        max_watts=None,
        weighted_average_watts=None,
        device_watts=False,
        kilojoules=None,
        has_heartrate=False,
        heartrate_opt_out=False,
        display_hide_heartrate_option=False,
        elev_high=None,
        elev_low=None,
        upload_id=None,
        upload_id_str=None,
        external_id=None,
        from_accepted_tag=False,
        pr_count=0,
        total_photo_count=0,
        has_kudoed=False,
        club_name=None
    )

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
    # Convert slug back to name, handling special cases
    name = slug.replace('-', ' ').title()
    
    # Handle special club name cases
    name_mappings = {
        'Urc Rotterdam': 'URC Rotterdam',
        # Add more mappings here as needed
    }
    
    return name_mappings.get(name, name)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('access_token'):
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def store_runs(user, activities):
    import json
    for act in activities:
        if act['type'] != 'Run':
            continue
        # Map to Activity dataclass
        activity = Activity.from_strava_json(act)
        activity.detect_club_run()  # Set club_name in Activity

        # Check if run already exists
        run = Run.query.filter_by(strava_activity_id=str(activity.id)).first()
        
        # Serialize JSON for SQLite compatibility
        raw_json_data = json.dumps(act) if app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite') else act
        
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
                raw_json=raw_json_data
            )
            db.session.add(run)
        else:
            run.name = activity.name
            run.start_date = activity.start_date
            run.start_date_local = activity.start_date_local
            run.distance = activity.distance
            run.moving_time = activity.moving_time
            run.club_name = activity.club_name
            run.raw_json = raw_json_data
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
    
    # Get club description from config if it exists
    club_description = None
    if club_name in CLUB_CONFIGS:
        club_description = CLUB_CONFIGS[club_name].get('description')
    
    return render_template(
        'club.html',
        authorized=True,
        monthly_runs=monthly_runs,
        current_year=get_current_year(),
        club_name=club_name,
        club_description=club_description
    )

@app.route('/my-clubs')
@login_required
def clubs():
    user_id = session.get('user_id')
    if not user_id:
        return render_template('my-clubs.html', authorized=False, my_clubs=[], club_descriptions={})
    runs = Run.query.filter_by(user_id=user_id).all()
    my_clubs = get_unique_clubs(runs)
    
    # Get club descriptions from config
    club_descriptions = {}
    for club in my_clubs:
        if club in CLUB_CONFIGS:
            club_descriptions[club] = CLUB_CONFIGS[club].get('description')
    
    return render_template(
        'my-clubs.html',
        authorized=True,
        my_clubs=my_clubs,
        club_descriptions=club_descriptions
    )

@app.route('/my-ranks')
@login_required
def ranks():
    user_id = session.get('user_id')
    if not user_id:
        return render_template('my-ranks.html', authorized=False, my_clubs=[], club_descriptions={})
    runs = Run.query.filter_by(user_id=user_id).all()
    my_clubs = get_unique_clubs(runs)
    
    # Get club descriptions from config
    club_descriptions = {}
    for club in my_clubs:
        if club in CLUB_CONFIGS:
            club_descriptions[club] = CLUB_CONFIGS[club].get('description')
    
    return render_template(
        'my-ranks.html',
        authorized=True,
        my_clubs=my_clubs,
        club_descriptions=club_descriptions
    )

@app.route('/stats')
@login_required
def stats():
    user_id = session.get('user_id')
    if not user_id:
        return render_template('stats.html', authorized=False)
    
    runs = Run.query.filter_by(user_id=user_id).order_by(Run.start_date_local).all()
    
    if not runs:
        return render_template('stats.html', authorized=True, stats=None)
    
    # Calculate statistics
    total_runs = len(runs)
    
    # Total unique days running
    unique_days = set(r.start_date_local.date() for r in runs if r.start_date_local)
    total_days_running = len(unique_days)
    
    # Total distance in kilometers
    total_kilometers = sum(r.distance or 0 for r in runs) / 1000
    
    # Total time in hours
    total_seconds = sum(r.moving_time or 0 for r in runs)
    total_hours = total_seconds / 3600
    
    # Longest run by distance
    longest_run = max(runs, key=lambda r: r.distance or 0)
    longest_distance = (longest_run.distance or 0) / 1000
    
    # Calculate longest streak
    longest_streak = calculate_longest_streak(runs)
    
    # Current year stats
    current_year = get_current_year()
    current_year_runs = [r for r in runs if r.start_date_local and r.start_date_local.year == current_year]
    current_year_total_runs = len(current_year_runs)
    current_year_kilometers = sum(r.distance or 0 for r in current_year_runs) / 1000
    current_year_hours = sum(r.moving_time or 0 for r in current_year_runs) / 3600
    
    stats = {
        'total_runs': total_runs,
        'total_days_running': total_days_running,
        'total_kilometers': round(total_kilometers, 1),
        'total_hours': round(total_hours, 1),
        'longest_distance': round(longest_distance, 1),
        'longest_run_name': longest_run.name,
        'longest_streak': longest_streak,
        'current_year': current_year,
        'current_year_runs': current_year_total_runs,
        'current_year_kilometers': round(current_year_kilometers, 1),
        'current_year_hours': round(current_year_hours, 1)
    }
    
    return render_template('stats.html', authorized=True, stats=stats)

def calculate_longest_streak(runs):
    """Calculate the longest streak of consecutive days running"""
    if not runs:
        return 0
    
    # Get unique run dates sorted
    run_dates = sorted(set(r.start_date_local.date() for r in runs if r.start_date_local))
    
    if not run_dates:
        return 0
    
    longest_streak = 1
    current_streak = 1
    
    for i in range(1, len(run_dates)):
        # Check if dates are consecutive
        if (run_dates[i] - run_dates[i-1]).days == 1:
            current_streak += 1
            longest_streak = max(longest_streak, current_streak)
        else:
            current_streak = 1
    
    return longest_streak

@app.route('/runner/<strava_id>')
@login_required
def runner_profile(strava_id):
    """Display runner profile page"""
    runner = User.query.filter_by(strava_id=strava_id).first()
    if not runner:
        return "Runner not found", 404
    
    return render_template(
        'runner.html',
        runner=runner
    )

@app.route('/<club_slug>/rank')
@login_required
def club_rank(club_slug):
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
    rank = defaultdict(lambda: defaultdict(list))  # {user: {month: [runs]}}

    for run, user in runs:
        month = run.start_date_local.strftime('%Y-%m') if run.start_date_local else 'unknown'
        rank[user][month].append(run)

    # Prepare rank data
    rank_data = []
    for user, months in rank.items():
        for month, user_runs in months.items():
            total_runs = len(user_runs)
            total_km = sum(r.distance or 0 for r in user_runs) / 1000
            total_time = sum(r.moving_time or 0 for r in user_runs)
            avg_pace = (
                (total_time / 60) / total_km if total_km > 0 else 0
            )  # min/km
            rank_data.append({
                'runner': user,
                'month': month,
                'total_runs': total_runs,
                'total_km': total_km,
                'total_time': total_time,
                'avg_pace': avg_pace,
            })

    # Sort by month, then by total_km descending
    rank_data.sort(key=lambda x: (x['month'], -x['total_km']))

    # Group rank_data by month for the template
    month_groups = defaultdict(lambda: defaultdict(list))  # {month: {user: [runs]}}

    for run, user in runs:
        month = run.start_date_local.strftime('%Y-%m')
        month_groups[month][user].append(run)

    rank_data_grouped = []
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
        rank_data_grouped.append({
            'month': month,
            'rows': rows
        })

    # Sort months reverse (latest first)
    rank_data_grouped.sort(key=lambda x: x['month'], reverse=True)

    return render_template(
        'club-rank.html',
        club_name=club_name,
        rank_data=rank_data_grouped
    )

@app.route('/reprocess-clubs')
@login_required
def reprocess_clubs():
    """Re-run club detection on all existing runs"""
    try:
        user_id = session.get('user_id')
        runs = Run.query.filter_by(user_id=user_id).all()
        
        updated_count = 0
        for run in runs:
            # Use the existing raw_json data if available, or create minimal data
            if run.raw_json:
                try:
                    # Try to parse existing JSON data
                    import json
                    if isinstance(run.raw_json, str):
                        raw_data = json.loads(run.raw_json)
                    else:
                        raw_data = run.raw_json
                    
                    # Create activity from existing data
                    temp_activity = Activity.from_strava_json(raw_data)
                except:
                    # Fallback: create minimal activity for club detection
                    temp_activity = create_minimal_activity_for_club_detection(run)
            else:
                # Create minimal activity for club detection
                temp_activity = create_minimal_activity_for_club_detection(run)
            
            old_club = run.club_name
            temp_activity.detect_club_run()
            new_club = temp_activity.club_name
            
            if old_club != new_club:
                run.club_name = new_club
                updated_count += 1
        
        db.session.commit()
        return f"Reprocessed {len(runs)} runs. Updated {updated_count} club assignments. <br><a href='/debug'>Check debug</a> | <a href='/'>Go home</a>"
        
    except Exception as e:
        return f"Error reprocessing clubs: {str(e)}", 500

@app.route('/refresh-data')
@login_required
def refresh_data():
    """Refresh all data from Strava and reprocess clubs"""
    try:
        user_id = session.get('user_id')
        
        user = User.query.get(user_id)
        if not user:
            return "User not found.", 400
        
        # Refresh access token if needed
        access_token = refresh_access_token(user)
        if not access_token:
            return "Failed to refresh access token. Please <a href='/login'>log in again</a>.", 400
        
        # Fetch activities from Strava (last 2 years)
        after_date = get_after_date(get_current_year() - 1)
        activities = fetch_activities(access_token, after_date)
        
        if not activities:
            return "Failed to fetch activities from Strava. Please try again.", 400
        
        # Store/update runs (this will update existing runs and add new ones)
        old_run_count = Run.query.filter_by(user_id=user_id).count()
        store_runs(user, activities)
        new_run_count = Run.query.filter_by(user_id=user_id).count()
        
        added_runs = new_run_count - old_run_count
        
        # Reprocess club assignments for all runs
        runs = Run.query.filter_by(user_id=user_id).all()
        club_updated_count = 0
        
        for run in runs:
            # Use the existing raw_json data if available, or create minimal data
            if run.raw_json:
                try:
                    # Try to parse existing JSON data
                    import json
                    if isinstance(run.raw_json, str):
                        raw_data = json.loads(run.raw_json)
                    else:
                        raw_data = run.raw_json
                    
                    # Create activity from existing data
                    temp_activity = Activity.from_strava_json(raw_data)
                except:
                    # Fallback: create minimal activity for club detection
                    temp_activity = create_minimal_activity_for_club_detection(run)
            else:
                # Create minimal activity for club detection
                temp_activity = create_minimal_activity_for_club_detection(run)
            
            old_club = run.club_name
            temp_activity.detect_club_run()
            new_club = temp_activity.club_name
            
            if old_club != new_club:
                run.club_name = new_club
                club_updated_count += 1
        
        db.session.commit()
        
        return f"""
        <style>
            body {{ font-family: 'Titillium Web', sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; background: #e4e2dd; }}
            .success {{ background: #d4edda; border: 1px solid #c3e6cb; color: #155724; padding: 15px; border-radius: 4px; margin: 10px 0; }}
            .links {{ margin-top: 20px; }}
            .links a {{ display: inline-block; background: #2d6da3; color: white; padding: 10px 15px; margin: 5px; text-decoration: none; border-radius: 4px; }}
            .links a:hover {{ background: #3a7fd6; }}
        </style>
        <h2>✅ Data Refresh Complete!</h2>
        <div class="success">
            <p><strong>Results:</strong></p>
            <ul>
                <li>Fetched {len(activities)} activities from Strava</li>
                <li>Added {added_runs} new runs to database</li>
                <li>Updated {len(runs)} total runs in database</li>
                <li>Reprocessed club assignments: {club_updated_count} runs updated</li>
            </ul>
        </div>
        <div class="links">
            <a href='/'>← Back to Dashboard</a>
            <a href='/debug-clubs'>🔍 View Club Debug</a>
            <a href='/stats'>📊 View Stats</a>
        </div>
        """
        
    except Exception as e:
        return f"Error refreshing data: {str(e)}", 500

@app.route('/debug-clubs')
@login_required
def debug_clubs():
    try:
        from config import CLUB_CONFIGS
        user_id = session.get('user_id')
        runs = Run.query.filter_by(user_id=user_id).order_by(Run.start_date_local.desc()).all()
        
        debug_info = ["<h2>Club Configuration Debug</h2>"]
        
        # Show current club configs
        debug_info.append("<h3>Current Club Configurations:</h3>")
        for club_name, config in CLUB_CONFIGS.items():
            days_names = [['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][d] for d in config['days']]
            debug_info.append(f"<b>{club_name}:</b> {', '.join(days_names)} {config['start_time']} - {config['end_time']}")
        
        # Analyze runs by day/time
        debug_info.append("<h3>Your Recent Runs Analysis:</h3>")
        day_time_stats = {}
        for run in runs[:50]:  # Last 50 runs
            day = run.start_date_local.weekday()
            hour = run.start_date_local.hour
            day_name = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][day]
            key = f"{day_name} {hour:02d}:xx"
            day_time_stats[key] = day_time_stats.get(key, 0) + 1
        
        # Sort by frequency
        sorted_stats = sorted(day_time_stats.items(), key=lambda x: x[1], reverse=True)
        debug_info.append("<p>Most common run times (to help configure clubs):</p>")
        for time_slot, count in sorted_stats[:10]:
            debug_info.append(f"• {time_slot}: {count} runs<br>")
            
        # Show club runs found
        club_runs = [r for r in runs if r.club_name]
        debug_info.append(f"<h3>Club Runs Found: {len(club_runs)}</h3>")
        for run in club_runs[:10]:
            day_name = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][run.start_date_local.weekday()]
            run_time = run.start_date_local.strftime('%H:%M')
            debug_info.append(f"• {run.name} - {day_name} {run_time} - Club: {run.club_name}<br>")
        
        return "".join(debug_info)
    except Exception as e:
        return f"Debug error: {str(e)}", 500

@app.route('/debug')
def debug():
    try:
        # Test database connection
        user_count = User.query.count()
        run_count = Run.query.count()
        
        # Get current user's runs if logged in
        user_id = session.get('user_id')
        debug_info = [f"Database OK - Users: {user_count}, Runs: {run_count}"]
        
        if user_id:
            user = User.query.get(user_id)
            runs = Run.query.filter_by(user_id=user_id).order_by(Run.start_date_local.desc()).limit(10).all()
            debug_info.append(f"<br><br>User: {user.name if user else 'Unknown'}")
            debug_info.append(f"Total runs for user: {len(Run.query.filter_by(user_id=user_id).all())}")
            
            if runs:
                debug_info.append("<br><br>Recent runs:")
                for run in runs:
                    day_name = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][run.start_date_local.weekday()]
                    run_time = run.start_date_local.strftime('%H:%M')
                    club_status = f"Club: {run.club_name}" if run.club_name else "No club"
                    debug_info.append(f"<br>• {run.name} - {day_name} {run_time} - {club_status}")
            else:
                debug_info.append("<br><br>No runs found for current user")
        else:
            debug_info.append("<br><br>Not logged in")
            
        return "<br>".join(debug_info)
    except Exception as e:
        return f"Database Error: {str(e)}", 500

@app.template_filter('datetime')
def format_datetime(value, fmt='%B %Y'):
    from datetime import datetime
    return datetime.strptime(value, '%Y-%m').strftime(fmt)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Create tables if they don't exist
    host = os.environ.get('FLASK_RUN_HOST', '0.0.0.0')
    # Try PORT first (for platforms like Render), then FLASK_RUN_PORT, default to 5555
    try:
        port = int(os.environ.get('PORT', os.environ.get('FLASK_RUN_PORT', '5555')))
    except (ValueError, TypeError):
        port = 5555
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() in ('1', 'true', 'yes')
    app.run(debug=debug, host=host, port=port)
