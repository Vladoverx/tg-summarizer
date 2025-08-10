from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session
from db.models import Base
import os
from dotenv import load_dotenv
from sqlite3 import Connection as SQLite3Connection


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is required")

sql_echo = os.getenv("SQL_ECHO", "false").lower() == "true"

if DATABASE_URL.startswith("sqlite"):
    connect_args = {}
    if os.getenv("SQLITE_DISABLE_CHECK_SAME_THREAD", "false").lower() == "true":
        connect_args["check_same_thread"] = False
    engine = create_engine(
        DATABASE_URL,
        connect_args=connect_args,
        echo=sql_echo,
    )
else:
    engine = create_engine(
        DATABASE_URL,
        echo=sql_echo,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=engine)


def create_tables():
    Base.metadata.create_all(bind=engine)


def get_session() -> Session:
    return SessionLocal()


@event.listens_for(Engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, SQLite3Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()
