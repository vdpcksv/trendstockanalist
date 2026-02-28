from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
import os

# Supabase PostgreSQL Connection String
# In production, set DATABASE_URL as an environment variable.
# Fallback to the hardcoded URL only for local development.
SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres.rxfxbmyotrnkcgqfzqwm:H03Y4oufkz3jDIP6@aws-1-ap-northeast-2.pooler.supabase.com:5432/postgres"
)

# For PostgreSQL, we don't need the check_same_thread connect_arg (which is for SQLite)
engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=10)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
