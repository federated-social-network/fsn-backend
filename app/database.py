from sqlalchemy import create_engine
from sqlalchemy import sessionmaker,declarative_base
from app.config import settings


engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"sslmode": "require"}  # Supabase needs SSL
)

SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()
