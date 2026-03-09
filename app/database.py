from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

# Engine
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"sslmode": "require", "options": "-c search_path=public -c statement_timeout=5000"},
    pool_pre_ping=True,
)

# Session
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base for models
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
