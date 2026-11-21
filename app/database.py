import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()

# The connection string comes from .env. Without one, the app keeps using the local file.
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./scribe.db")

# Some providers write "postgres://", which SQLAlchemy no longer accepts
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if DATABASE_URL.startswith("sqlite"):
    # This setting is only needed for SQLite
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    # pool_pre_ping checks that a connection is alive before using it.
    # The timezone setting makes the server store every time in UTC.
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        connect_args={"options": "-c timezone=utc"},
    )

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()