from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import settings

DATABASE_URL = settings.DATABASE_URL

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
    )

else:
    engine = create_engine(
        DATABASE_URL,
        connect_args={
            "sslmode": "require",
            "options": "-c search_path=public -c statement_timeout=5000",
        },
        poolclass=NullPool,  # Fresh connection per request — best for Cloud Run + Supabase
    )

SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
