from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Any
import pytz
from config import CLUB_CONFIGS

@dataclass
class Activity:
    id: int
    name: str
    distance: float
    moving_time: int
    elapsed_time: int
    total_elevation_gain: float
    type: str
    start_date: datetime
    start_date_local: datetime
    timezone: str
    start_latlng: Optional[List[float]]
    end_latlng: Optional[List[float]]
    average_speed: float
    max_speed: float
    average_heartrate: Optional[float]
    max_heartrate: Optional[float]
    kudos_count: int
    athlete_count: int
    private: bool
    # Additional required fields
    resource_state: int
    athlete: dict
    sport_type: str
    workout_type: Optional[int]
    utc_offset: float
    location_city: Optional[str]
    location_state: Optional[str]
    location_country: Optional[str]
    achievement_count: int
    comment_count: int
    photo_count: int
    map: dict
    trainer: bool
    commute: bool
    manual: bool
    visibility: str
    flagged: bool
    gear_id: Optional[str]
    average_cadence: Optional[float]
    average_watts: Optional[float]
    max_watts: Optional[float]
    weighted_average_watts: Optional[float]
    device_watts: bool
    kilojoules: Optional[float]
    has_heartrate: bool
    heartrate_opt_out: bool
    display_hide_heartrate_option: bool
    elev_high: Optional[float]
    elev_low: Optional[float]
    upload_id: Optional[int]
    upload_id_str: Optional[str]
    external_id: Optional[str]
    from_accepted_tag: bool
    pr_count: int
    total_photo_count: int
    has_kudoed: bool
    club_name: Optional[str] = None

    @classmethod
    def from_strava_json(cls, data: dict) -> 'Activity':
        activity = cls(
            id=data['id'],
            name=data['name'],
            distance=data['distance'],
            moving_time=data['moving_time'],
            elapsed_time=data['elapsed_time'],
            total_elevation_gain=data['total_elevation_gain'],
            type=data['type'],
            start_date=datetime.strptime(data['start_date'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.UTC),
            start_date_local=datetime.strptime(data['start_date_local'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.UTC),
            timezone=data['timezone'],
            start_latlng=data.get('start_latlng'),
            end_latlng=data.get('end_latlng'),
            average_speed=data['average_speed'],
            max_speed=data['max_speed'],
            average_heartrate=data.get('average_heartrate'),
            max_heartrate=data.get('max_heartrate'),
            kudos_count=data.get('kudos_count', 0),
            athlete_count=data.get('athlete_count', 1),
            private=data.get('private', False),
            # Additional fields with defaults
            resource_state=data.get('resource_state', 2),
            athlete=data.get('athlete', {}),
            sport_type=data.get('sport_type', 'Run'),
            workout_type=data.get('workout_type'),
            utc_offset=data.get('utc_offset', 0),
            location_city=data.get('location_city'),
            location_state=data.get('location_state'),
            location_country=data.get('location_country'),
            achievement_count=data.get('achievement_count', 0),
            comment_count=data.get('comment_count', 0),
            photo_count=data.get('photo_count', 0),
            map=data.get('map', {}),
            trainer=data.get('trainer', False),
            commute=data.get('commute', False),
            manual=data.get('manual', False),
            visibility=data.get('visibility', 'everyone'),
            flagged=data.get('flagged', False),
            gear_id=data.get('gear_id'),
            average_cadence=data.get('average_cadence'),
            average_watts=data.get('average_watts'),
            max_watts=data.get('max_watts'),
            weighted_average_watts=data.get('weighted_average_watts'),
            device_watts=data.get('device_watts', False),
            kilojoules=data.get('kilojoules'),
            has_heartrate=data.get('has_heartrate', False),
            heartrate_opt_out=data.get('heartrate_opt_out', False),
            display_hide_heartrate_option=data.get('display_hide_heartrate_option', False),
            elev_high=data.get('elev_high'),
            elev_low=data.get('elev_low'),
            upload_id=data.get('upload_id'),
            upload_id_str=data.get('upload_id_str'),
            external_id=data.get('external_id'),
            from_accepted_tag=data.get('from_accepted_tag', False),
            pr_count=data.get('pr_count', 0),
            total_photo_count=data.get('total_photo_count', 0),
            has_kudoed=data.get('has_kudoed', False),
            club_name=None
        )
        activity.detect_club_run()
        return activity

    @property
    def pace_per_km(self) -> float:
        """Calculate pace in minutes per kilometer"""
        kilometers = self.distance / 1000
        hours = self.moving_time / 3600
        return (hours * 60) / kilometers

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
        pace_minutes = int(self.pace_per_km)
        pace_seconds = int((self.pace_per_km - pace_minutes) * 60)
        return f"{pace_minutes}:{pace_seconds:02d}"

    def detect_club_run(self) -> None:
        """Detect if this is a club run based on day and time"""
        self.club_name = None
        run_date = self.start_date_local
        if run_date is None:
            return
        run_time = run_date.time()

        for club_name, config in CLUB_CONFIGS.items():
            # Check if run is on configured day
            if run_date.strftime('%A') in config['days']:
                # Convert time window to time objects
                start_time = datetime.strptime(config['time_window']['start'], '%H:%M').time()
                end_time = datetime.strptime(config['time_window']['end'], '%H:%M').time()
                
                # Check if run time is within window
                if start_time <= run_time <= end_time:
                    self.club_name = club_name
                    break