from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

# Supabase PostgreSQL Connection String
# Please replace <YOUR_PASSWORD> with your actual database password!
SQLALCHEMY_DATABASE_URL = "postgresql://postgres.rxfxbmyotrnkcgqfzqwm:H03Y4oufkz3jDIP6@aws-1-ap-northeast-2.pooler.supabase.com:5432/postgres"

# For PostgreSQL, we don't need the check_same_thread connect_arg (which is for SQLite)
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
