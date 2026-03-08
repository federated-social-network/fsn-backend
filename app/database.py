from sqlalchemy import create_engine

from app.config import settings

DATABASE_URL = settings.DATABASE_URL

connect_args = {}

if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
else:
    connect_args = {
        "sslmode": "require",
        "options": "-c statement_timeout=5000",
    }

engine = create_engine(DATABASE_URL, connect_args=connect_args)
