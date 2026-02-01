from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker,declarative_base
from app.config import settings


engine = create_engine(
    settings.DATABASE_URL,
    connect_args={
        "sslmode": "require",
        "options": "-c statement_timeout=5000"
    },
    pool_pre_ping=True
)

SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()