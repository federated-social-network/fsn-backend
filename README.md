<h1 align="center">⚡ Heliix — Federated Social Network</h1>

<p align="center">
  <em>A next-generation, open-source social platform built on federation.<br/>Own your identity. Connect across boundaries. Speak freely.</em>
</p>

<p align="center">
  🌐 <a href="https://heliix.live">heliix.live</a> &nbsp;·&nbsp; ⚡ <a href="https://heliix.studio">heliix.studio</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python"/>
  <img src="https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI"/>
  <img src="https://img.shields.io/badge/PostgreSQL-4169E1?style=flat-square&logo=postgresql&logoColor=white" alt="PostgreSQL"/>
  <img src="https://img.shields.io/badge/Supabase-3ECF8E?style=flat-square&logo=supabase&logoColor=white" alt="Supabase"/>
  <img src="https://img.shields.io/badge/ActivityPub-w3c-eb5e28?style=flat-square" alt="ActivityPub"/>
  <img src="https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white" alt="Docker"/>
  <img src="https://img.shields.io/badge/License-MIT-yellow?style=flat-square" alt="MIT License"/>
</p>



## 🌐 What is Heliix?

**Heliix** is a **federated social networking application** — a full-featured, modern social platform where users can create posts, chat in real-time, make voice & video calls, and interact with each other, all while being part of the wider **fediverse**. Unlike traditional platforms like Mastodon (which focuses primarily on microblogging) or Friendica (which prioritizes protocol compatibility), Heliix goes further by combining **real-time messaging**, **WebRTC-based audio/video calls**, **AI-powered content assistance**, and **image moderation** into a single, cohesive experience — features that most fediverse applications don't offer out of the box.

Users on one Heliix instance can follow and interact with users on *any* ActivityPub-compatible server, including **Mastodon**, without leaving their home instance. Think of it like email: you have a Gmail account, your friend has Outlook, but you can still message each other seamlessly.

### 📦 About This Repository

This repository contains the **Heliix backend** — a RESTful API server built with **FastAPI** (Python 3.11+), backed by **PostgreSQL** via **SQLAlchemy ORM** with **Alembic** for database migrations. It exposes a comprehensive set of REST API endpoints for authentication, posts, user management, real-time chat (WebSockets), WebRTC call signaling, notifications, and ActivityPub federation. Media storage (avatars, post images) is handled through **Supabase Storage**, AI-powered features use the **Groq API**, and content moderation leverages **Google Cloud Vision**. The server is containerized with **Docker** and deployed on **Google Cloud Run**.

### ✨ Key Highlights

| Feature | Description |
|---|---|
| 🔗 **ActivityPub Federation** | Follow and interact with users across Mastodon and other federated platforms |
| 💬 **Real-time Chat** | WebSocket-powered instant messaging with read receipts |
| 📞 **Voice & Video Calls** | WebRTC signaling for peer-to-peer calls between connected users |
| 🤖 **AI-Powered Posting** | Groq-powered post auto-completion and elaboration |
| 🛡️ **Content Moderation** | Google Cloud Vision SafeSearch for uploaded images |
| 🖼️ **Media Uploads** | Avatars and post images stored via Supabase Storage |
| 🔐 **Secure Authentication** | JWT + Argon2 password hashing + OTP-based password reset |
| 🔔 **Notifications** | In-app notifications for follows, likes, comments, and messages |

---

## 🏗️ System Architecture

<p align="center">
  <img src="resources/architecture_diagram.png" alt="Heliix System Architecture" width="90%"/>
</p>

The architecture consists of:

- **Frontend** — React app hosted on [heliix.live](https://heliix.live) via Cloudflare Pages
- **Backend** — FastAPI server hosted on [heliix.studio](https://heliix.studio) via Google Cloud Run
- **Database** — PostgreSQL for relational data (users, posts, connections, messages)
- **Object Storage** — Supabase Storage for avatars and post images
- **Real-time** — WebSockets for chat, WebRTC signaling for voice/video calls
- **Federation** — ActivityPub protocol for cross-instance communication (Mastodon, etc.)
- **AI** — Groq API for intelligent post completion & elaboration
- **Moderation** — Google Cloud Vision for image safety analysis
- **Caching** — Redis for post caching and performance

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.11+**
- **PostgreSQL** database
- **Supabase** project (for file storage)
- **Gmail OAuth2** credentials (for email/OTP functionality)
- **Groq API key** (for AI features)

### Installation

```bash
# Clone the repository
git clone https://github.com/federated-social-platform/fsn-backend.git
cd fsn-backend

# Install dependencies
make install

# Or for development (includes linting & formatting tools)
make dev
```

### Environment Configuration

Create a `.env` file in the project root:

```env
# ─── Core ────────────────────────────────────
INSTANCE_NAME=InstanceA
DATABASE_URL=postgresql://user:password@localhost:5432/fsn_db
SECRET_KEY=your-secret-key-here
ALGORITHM=HS256
BASE_URL=http://localhost:8000

# ─── Federation ──────────────────────────────
SEND_TO_OTHER_INSTANCE=false
REMOTE_INBOX_URL=http://localhost:8001/inbox

# ─── Supabase (File Storage) ────────────────
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-supabase-service-key

# ─── AI (Groq) ──────────────────────────────
GROQ_API_KEY=your-groq-api-key

# ─── Email / OTP ────────────────────────────
EMAIL_PROVIDER=gmail_oauth
FROM_EMAIL=your-email@gmail.com
OTP_EXPIRY_MINUTES=10

# ─── Gmail OAuth2 ───────────────────────────
GMAIL_CLIENT_ID=your-client-id
GMAIL_CLIENT_SECRET=your-client-secret
GMAIL_REFRESH_TOKEN=your-refresh-token
```

### Database Setup

```bash
# Run Alembic migrations
alembic upgrade head

# Or create tables directly
make migrate
```

### Run the Server

```bash
# Development server with hot-reload (port 8000)
make run

# Or run specific instances for federation testing
make run-instance-a   # Port 8000
make run-instance-b   # Port 8001
```

The API docs are available at `http://localhost:8000/docs` (Swagger UI).

---

## 📡 API Reference

### 🔐 Authentication (`/auth`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/auth/register` | Register a new user |
| `POST` | `/auth/login` | Login and receive JWT tokens |
| `POST` | `/auth/forgot-password` | Request a password reset OTP |
| `POST` | `/auth/verify-otp` | Verify the OTP code |
| `POST` | `/auth/reset-password` | Reset password with verified OTP |

### 📝 Posts

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/posts` | Create a new post (text and/or image) |
| `GET` | `/get_posts` | Get all public posts |
| `GET` | `/timeline` | Get personalized timeline |
| `GET` | `/timeline_connected_users` | Get posts from connected/followed users |
| `DELETE` | `/delete/{post_id}` | Delete a post |
| `POST` | `/like/{post_id}` | Like a post |
| `DELETE` | `/unlike/{post_id}` | Unlike a post |
| `POST` | `/comments/{post_id}` | Add a comment to a post |
| `GET` | `/comments/{post_id}` | Get comments on a post |
| `DELETE` | `/comments/{comment_id}` | Delete a comment |

### 🤖 AI Features

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/complete_post` | AI-powered post auto-completion |
| `POST` | `/eloborate_post` | AI-powered post elaboration |

### 👤 Users

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/get_current_user` | Get current authenticated user |
| `GET` | `/get_user/{username}` | Get a user's profile |
| `GET` | `/search_users?q=` | Search local & remote users |
| `GET` | `/random_users` | Get random user suggestions |
| `POST` | `/connect/{username}` | Send a connection request |
| `POST` | `/connect/accept/{id}` | Accept a connection request |
| `GET` | `/connections/pending` | Get pending connection requests |
| `GET` | `/list_connections` | List all connections |
| `POST` | `/remove_connection/{username}` | Remove a connection |
| `POST` | `/upload_avatar` | Upload a profile picture |
| `PUT` | `/update_profile` | Update bio, display name, avatar |

### 💬 Chat & Calls

| Method | Endpoint | Description |
|--------|----------|-------------|
| `WS` | `/ws/chat/{user_id}` | WebSocket for real-time chat & WebRTC signaling |
| `GET` | `/messages/{user1}/{user2}` | Get message history between two users |
| `GET` | `/conversations` | Get all conversations for current user |

### 🔔 Notifications

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/notifications` | Get notifications for current user |

### 🛡️ Content Moderation

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/moderate-image` | Analyze image for unsafe content |

### 🌍 Federation (ActivityPub)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/.well-known/webfinger` | WebFinger discovery for actor lookup |
| `GET` | `/users/{username}` | ActivityPub actor profile (JSON-LD) |
| `POST` | `/users/{username}/inbox` | Per-user inbox for incoming activities |
| `POST` | `/inbox` | Shared inbox for federated activities |
| `GET` | `/users/{username}/outbox` | Outbox — user's public posts (OrderedCollection) |
| `POST` | `/sync-remote-posts` | Manually sync posts from followed remote users |

---

## 📁 Project Structure

```
fsn-backend/
├── app/
│   ├── routers/                  # API route handlers
│   │   ├── auth.py               #   Authentication & password reset
│   │   ├── posts.py              #   Posts, likes, comments, AI features
│   │   ├── users.py              #   Profiles, connections, search, avatars
│   │   ├── chat.py               #   WebSocket chat & WebRTC signaling
│   │   ├── federation.py         #   ActivityPub protocol endpoints
│   │   ├── notifications.py      #   In-app notifications
│   │   └── moderation.py         #   Image safety analysis
│   ├── services/
│   │   ├── federation.py         #   Activity building & delivery
│   │   ├── crypto.py             #   HTTP signature signing (RSA)
│   │   ├── connection_manager.py #   WebSocket connection manager
│   │   └── supabase_client.py    #   Supabase storage client
│   ├── main.py                   # FastAPI app entry point
│   ├── models.py                 # SQLAlchemy ORM models
│   ├── database.py               # Database engine & session
│   ├── config.py                 # Environment settings (Pydantic)
│   ├── dependencies.py           # Auth dependency injection
│   ├── auth.py                   # JWT token utilities
│   └── email_service.py          # Gmail OAuth2 / SMTP email service
├── alembic/                      # Database migrations
├── tests/                        # Pytest test suite
│   ├── auth/                     #   Auth endpoint tests
│   ├── posts/                    #   Post endpoint tests
│   ├── users/                    #   User endpoint tests
│   ├── chat/                     #   Chat endpoint tests
│   └── notifications/            #   Notification tests
├── resources/
│   └── architecture_diagram.png  # System architecture diagram
├── Dockerfile                    # Container build
├── Makefile                      # Development commands (Linux/macOS)
├── run.ps1                       # Development commands (Windows)
├── requirements.txt              # Python dependencies
├── pyproject.toml                # Tool configuration (black, isort, pytest)
├── alembic.ini                   # Alembic configuration
└── LICENSE                       # MIT License
```

---

## 🧪 Testing

```bash
# Run all tests
make test

# Run with coverage report
make test-coverage

# Run a specific test file
pytest tests/auth/ -v
```

---

## 🐳 Docker

```bash
# Build the image
make docker-build

# Run the container
make docker-run
```

Or manually:
```bash
docker build -t heliix-backend .
docker run -p 8080:8080 --env-file .env heliix-backend
```

---

## 🛠️ Development Commands

| Command | Description |
|---------|-------------|
| `make install` | Install production dependencies |
| `make dev` | Install dev dependencies (+ black, flake8, isort) |
| `make run` | Start dev server with hot-reload |
| `make test` | Run test suite |
| `make test-coverage` | Run tests with coverage report |
| `make lint` | Run flake8 linting |
| `make format` | Auto-format code with black & isort |
| `make clean` | Remove cache & build files |
| `make migrate` | Create database tables |
| `make create-token` | Generate Gmail OAuth refresh token |

> **Windows users:** Replace `make` with `.\run.ps1` (PowerShell).

---

## 🤝 Federation — How It Works

Heliix implements the **ActivityPub** protocol (W3C standard), enabling interoperability with thousands of federated servers:

1. **WebFinger Discovery** — Remote servers look up users via `/.well-known/webfinger`
2. **Actor Profiles** — Each user has a JSON-LD actor profile with public keys
3. **HTTP Signatures** — All server-to-server requests are cryptographically signed with RSA
4. **Activity Types** — Supports `Create`, `Delete`, `Follow`, `Accept`, and `Undo`
5. **Inbox/Outbox** — Standard ActivityPub inbox for receiving and outbox for publishing activities

**Example:** A Mastodon user can follow `alice@heliix.studio` and see her posts directly in their Mastodon timeline — and vice versa.

---

## 🔗 Links

| | |
|---|---|
| 🌐 **Frontend** | [heliix.live](https://heliix.live) |
| ⚡ **Backend API** | [heliix.studio](https://heliix.studio) |
| 📖 **API Docs** | [heliix.studio/docs](https://heliix.studio/docs) |
| 🐙 **GitHub** | [github.com/federated-social-platform](https://github.com/federated-social-platform) |

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.
