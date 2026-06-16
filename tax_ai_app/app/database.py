import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from contextlib import contextmanager

# Read from environment, default to postgres as specified in docker-compose.yml
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://tax_ai:tax_ai_password@db:5432/tax_ai")

# If we run tests or local development without postgres, let it fall back or work nicely
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

@contextmanager
def get_db():
    """Context manager for database sessions, ideal for non-route contexts (e.g., workers)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_db_session():
    """FastAPI dependency yielding a db session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
