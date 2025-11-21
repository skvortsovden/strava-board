# Architecture Documentation

## C4 Model Diagrams

### Level 1: System Context Diagram

```mermaid
C4Context
    title System Context - Strava Board Application

    Person(user, "Runner", "A person who tracks their runs on Strava")
    
    System(stravaBoard, "Strava Board", "Web application that displays running statistics, club runs, and leaderboards")
    
    System_Ext(strava, "Strava API", "Provides authentication and activity data")
    SystemDb_Ext(database, "Database", "PostgreSQL (production) / SQLite (local)")
    
    Rel(user, stravaBoard, "Views running stats, club leaderboards", "HTTPS")
    Rel(stravaBoard, strava, "Authenticates users, fetches activities", "HTTPS/OAuth2")
    Rel(stravaBoard, database, "Reads/writes user data and runs", "SQL")
```

### Level 2: Container Diagram

```mermaid
C4Container
    title Container Diagram - Strava Board Application

    Person(user, "Runner", "Uses web browser to access the application")
    
    System_Boundary(c1, "Strava Board") {
        Container(web, "Flask Web Application", "Python, Flask", "Handles HTTP requests, OAuth flow, data processing")
        Container(templates, "Web Templates", "Jinja2 HTML", "Renders views for statistics and club rankings")
        ContainerDb(db, "Database", "PostgreSQL/SQLite", "Stores user profiles, access tokens, and run data")
    }
    
    System_Ext(strava, "Strava API", "OAuth 2.0 & REST API")
    
    Rel(user, web, "Views pages, authenticates", "HTTPS")
    Rel(web, templates, "Renders", "Jinja2")
    Rel(web, db, "Reads/writes", "SQLAlchemy ORM")
    Rel(web, strava, "OAuth flow, fetch activities", "HTTPS")
```

### Level 3: Component Diagram

```mermaid
C4Component
    title Component Diagram - Flask Web Application

    Container_Boundary(c1, "Flask Web Application") {
        Component(routes, "Route Handlers", "Flask Routes", "Handle HTTP requests for different endpoints")
        Component(auth, "Authentication Manager", "OAuth2 Flow", "Manages Strava OAuth, token refresh")
        Component(clubDetection, "Club Detection Engine", "Business Logic", "Identifies club runs based on time/day patterns")
        Component(statsCalculator, "Statistics Calculator", "Business Logic", "Calculates running stats, streaks, rankings")
        Component(dataSync, "Data Synchronizer", "Background Process", "Fetches and updates activities from Strava")
        Component(models, "Data Models", "SQLAlchemy ORM", "User, Run, Activity models")
    }
    
    ContainerDb(db, "Database", "PostgreSQL/SQLite")
    System_Ext(strava, "Strava API")
    
    Rel(routes, auth, "Authenticates user", "Function call")
    Rel(routes, clubDetection, "Detects club runs", "Function call")
    Rel(routes, statsCalculator, "Calculates statistics", "Function call")
    Rel(routes, dataSync, "Triggers data refresh", "Function call")
    Rel(auth, strava, "OAuth token exchange", "HTTPS")
    Rel(dataSync, strava, "Fetch activities", "HTTPS")
    Rel(models, db, "CRUD operations", "SQLAlchemy")
    Rel(clubDetection, models, "Uses")
    Rel(statsCalculator, models, "Queries")
    Rel(dataSync, models, "Updates")
```

### Level 4: Code Diagram - Authentication Flow

```mermaid
sequenceDiagram
    participant U as User
    participant R as Routes
    participant A as Auth Manager
    participant S as Strava API
    participant D as Database
    
    U->>R: GET /login
    R->>A: Initiate OAuth
    A->>S: Redirect to authorization
    S->>U: Show authorization page
    U->>S: Grant permission
    S->>R: GET /callback?code=xxx
    R->>A: Exchange code for token
    A->>S: POST /oauth/token
    S->>A: Return access_token, refresh_token
    A->>S: GET /api/v3/athlete
    S->>A: Return user profile
    A->>D: Save/update User record
    D->>A: User ID
    A->>R: Set session tokens
    R->>U: Redirect to dashboard
```

### Level 4: Code Diagram - Data Refresh Flow

```mermaid
sequenceDiagram
    participant U as User
    participant R as Routes
    participant DS as Data Sync
    participant A as Auth Manager
    participant S as Strava API
    participant CD as Club Detection
    participant M as Models
    participant D as Database
    
    U->>R: GET /refresh-data
    R->>A: refresh_access_token(user)
    A->>S: POST /oauth/token (refresh)
    S->>A: New access token
    A->>D: Update user tokens
    R->>DS: fetch_activities(token, after_date)
    DS->>S: GET /api/v3/athlete/activities
    S->>DS: Return activities JSON
    DS->>R: Activities list
    R->>DS: store_runs(user, activities)
    loop For each activity
        DS->>CD: Activity.detect_club_run()
        CD->>CD: Check day/time patterns
        CD->>DS: Return club_name
        DS->>M: Create/update Run
        M->>D: SQL INSERT/UPDATE
    end
    R->>U: Success message with stats
```

### Level 4: Code Diagram - Club Ranking Flow

```mermaid
sequenceDiagram
    participant U as User
    participant R as Routes
    participant SC as Stats Calculator
    participant M as Models
    participant D as Database
    
    U->>R: GET /club-slug/rank
    R->>R: slug_to_name(club_slug)
    R->>M: Query runs by club & year
    M->>D: SQL JOIN Run, User
    D->>M: Return runs with user data
    M->>R: List of (run, user) tuples
    R->>SC: group_by_user_and_month()
    loop For each user/month
        SC->>SC: Calculate total_runs
        SC->>SC: Calculate total_km
        SC->>SC: Calculate avg_pace
        SC->>SC: Count unique run_days
    end
    SC->>R: Ranked data by month
    R->>R: Sort by run_days, then km
    R->>U: Render club-rank.html
```

### Data Model Diagram

```mermaid
erDiagram
    USER ||--o{ RUN : creates
    USER {
        int id PK
        string strava_id UK
        string name
        string profile_photo
        string access_token
        string refresh_token
        datetime token_expires_at
    }
    RUN {
        int id PK
        int user_id FK
        string strava_activity_id UK
        string name
        datetime start_date
        datetime start_date_local
        float distance
        int moving_time
        string club_name
        json raw_json
    }
    ACTIVITY {
        note "Dataclass - not persisted"
        int id
        string name
        float distance
        int moving_time
        datetime start_date
        string club_name
    }
    RUN ||--|| ACTIVITY : "maps to"
```

### Deployment Diagram

```mermaid
C4Deployment
    title Deployment Diagram - Production Environment

    Deployment_Node(render, "Render.com", "Cloud Platform") {
        Deployment_Node(web_service, "Web Service", "Container") {
            Container(app, "Strava Board", "Flask + Gunicorn", "Python web application")
        }
        Deployment_Node(db_service, "PostgreSQL Service", "Managed Database") {
            ContainerDb(postgres, "PostgreSQL", "Database", "Persistent data storage")
        }
    }
    
    Deployment_Node(strava_cloud, "Strava", "External Service") {
        System_Ext(strava_api, "Strava API", "OAuth & Activity Data")
    }
    
    Deployment_Node(client, "User Device", "Browser") {
        Container(browser, "Web Browser", "Chrome/Safari/Firefox", "User interface")
    }
    
    Rel(browser, app, "HTTPS requests", "443")
    Rel(app, postgres, "SQL queries", "5432")
    Rel(app, strava_api, "API calls", "443")
```

### Technology Stack

```mermaid
graph TB
    subgraph "Frontend"
        HTML[HTML Templates<br/>Jinja2]
        CSS[CSS Styling<br/>style.css]
    end
    
    subgraph "Backend"
        Flask[Flask 3.0.0<br/>Web Framework]
        SQLAlchemy[SQLAlchemy 3.0.5<br/>ORM]
        Gunicorn[Gunicorn 21.2.0<br/>WSGI Server]
    end
    
    subgraph "Data Layer"
        PostgreSQL[(PostgreSQL<br/>Production DB)]
        SQLite[(SQLite<br/>Local Dev DB)]
        psycopg[psycopg 3.2.9<br/>DB Driver]
    end
    
    subgraph "External"
        StravaAPI[Strava API<br/>OAuth + REST]
        Requests[requests 2.31.0<br/>HTTP Client]
    end
    
    subgraph "Utilities"
        pytz[pytz 2.23.3<br/>Timezone handling]
        dotenv[python-dotenv 1.0.1<br/>Config management]
    end
    
    HTML --> Flask
    CSS --> Flask
    Flask --> SQLAlchemy
    Flask --> Gunicorn
    SQLAlchemy --> psycopg
    psycopg --> PostgreSQL
    psycopg --> SQLite
    Flask --> Requests
    Requests --> StravaAPI
    Flask --> pytz
    Flask --> dotenv
```

## Key Architectural Decisions

### 1. Database Strategy
- **Production**: PostgreSQL with psycopg driver
- **Development**: SQLite for simplicity
- **Rationale**: Easy local development, robust production deployment

### 2. Authentication
- **OAuth 2.0** flow with Strava
- Token refresh mechanism for long-lived sessions
- Session-based user state management

### 3. Club Detection
- Time-window based pattern matching
- Configurable per club (days, time ranges)
- Reprocessable for historical data

### 4. Data Synchronization
- Manual refresh trigger (`/refresh-data`)
- Initial sync on OAuth callback
- Fetches last 2 years of activities

### 5. Ranking Algorithm
- Primary: Unique run days (encourages consistency)
- Secondary: Total kilometers (rewards volume)
- Grouped by month for temporal comparison

