# Federated Social Network - Backend

A federated social network backend built with FastAPI, supporting ActivityPub-like federation.

## Features

- User authentication with JWT tokens
- Password reset with OTP via Gmail OAuth2
- Post creation and deletion
- User connections (follow/unfollow)
- Federation support for cross-instance communication
- PostgreSQL database with SQLAlchemy ORM

## Prerequisites

- Python 3.11+
- PostgreSQL database
- Gmail OAuth2 credentials (for email functionality)

## Installation

### Linux/macOS

```bash
# Install dependencies
make install

# Or for development
make dev
```

### Windows

**Using Batch Script:**
```cmd
run.bat install
```

**Using PowerShell:**
```powershell
.\run.ps1 install
```

## Configuration

1. Copy `.env.example` to `.env` (if available) or create a `.env` file with:

```env
INSTANCE_NAME=InstanceA
DATABASE_URL=postgresql://user:password@localhost:5432/fsn_db
SECRET_KEY=your-secret-key-here
ALGORITHM=HS256
BASE_URL=http://localhost:8000
SEND_TO_OTHER_INSTANCE=false
REMOTE_INBOX_URL=http://localhost:8001/inbox

# Email settings
EMAIL_PROVIDER=gmail_oauth
FROM_EMAIL=your-email@gmail.com
OTP_EXPIRY_MINUTES=10

# Gmail OAuth2
GMAIL_CLIENT_ID=your-client-id
GMAIL_CLIENT_SECRET=your-client-secret
GMAIL_REFRESH_TOKEN=your-refresh-token
```

2. Create database tables:

**Linux/macOS:**
```bash
make migrate
```

**Windows:**
```cmd
run.bat migrate
# or
.\run.ps1 migrate
```

## Running the Application

### Linux/macOS

```bash
# Run development server
make run

# Run specific instance
make run-instance-a  # Port 8000
make run-instance-b  # Port 8001
```

### Windows

**Using Batch Script:**
```cmd
run.bat run
run.bat run-instance-a
run.bat run-instance-b
```

**Using PowerShell:**
```powershell
.\run.ps1 run
.\run.ps1 run-instance-a
.\run.ps1 run-instance-b
```

## Testing

### Linux/macOS
```bash
make test
```

### Windows
```cmd
run.bat test
# or
.\run.ps1 test
```

## Docker

### Build and Run

**Linux/macOS:**
```bash
make docker-build
make docker-run
```

**Windows:**
```cmd
run.bat docker-build
run.bat docker-run
```

## Development Commands

### Linux/macOS

| Command | Description |
|---------|-------------|
| `make install` | Install production dependencies |
| `make dev` | Install development dependencies |
| `make run` | Run development server |
| `make test` | Run tests |
| `make clean` | Remove cache files |
| `make migrate` | Create database tables |
| `make lint` | Run code linting |
| `make format` | Format code |
| `make create-token` | Generate Gmail OAuth token |

### Windows

Replace `make` with `run.bat` or `.\run.ps1`:

```cmd
run.bat install
run.bat dev
run.bat run
run.bat test
run.bat clean
```

Or with PowerShell:

```powershell
.\run.ps1 install
.\run.ps1 dev
.\run.ps1 run
.\run.ps1 test
.\run.ps1 clean
```

## API Endpoints

### Authentication
- `POST /auth/register` - Register new user
- `POST /auth/login` - Login user
- `POST /auth/forgot-password` - Request password reset OTP
- `POST /auth/verify-otp` - Verify OTP
- `POST /auth/reset-password` - Reset password

### Posts
- `POST /posts` - Create post
- `GET /get_posts` - Get all posts
- `GET /timeline` - Get timeline
- `GET /timeline_connected_users` - Get posts from connected users
- `DELETE /delete/{post_id}` - Delete post

### Users
- `GET /get_current_user` - Get current user info
- `GET /get_user/{username}` - Get user profile
- `GET /search_users` - Search users
- `GET /random_users` - Get random user suggestions
- `POST /connect/{username}` - Send connection request
- `POST /connect/accept/{connection_id}` - Accept connection
- `GET /connections/pending` - Get pending connections
- `GET /list_connections` - List all connections
- `POST /remove_connection/{username}` - Remove connection

### Federation
- `POST /inbox` - Receive federated activities
- `POST /users/{username}/outbox` - Send federated activities

## Project Structure

```
fsn-backend/
├── app/
│   ├── routers/
│   │   ├── auth.py
│   │   ├── posts.py
│   │   ├── users.py
│   │   └── federation.py
│   ├── services/
│   │   └── federation.py
│   ├── auth.py
│   ├── config.py
│   ├── database.py
│   ├── dependencies.py
│   ├── email_service.py
│   ├── main.py
│   └── models.py
├── tests/
├── .env
├── requirements.txt
├── Makefile (Linux/macOS)
├── run.bat (Windows)
├── run.ps1 (Windows PowerShell)
└── Dockerfile


## License

[Your License Here]
