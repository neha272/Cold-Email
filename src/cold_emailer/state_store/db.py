"""Database initialization and session management."""

from pathlib import Path
from typing import Any, Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from cold_emailer.state_store.models import Base


def create_database_engine(db_path: str, echo: bool = False) -> Engine:
    """
    Create SQLAlchemy engine for SQLite database.

    Args:
        db_path: Path to SQLite database file
        echo: Enable SQL query logging

    Returns:
        SQLAlchemy engine
    """
    # Ensure parent directory exists
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)

    # SQLite connection string
    # Use check_same_thread=False for SQLite (required for some use cases)
    engine = create_engine(
        f"sqlite:///{db_path}",
        echo=echo,
        connect_args={"check_same_thread": False},
    )

    # Enable foreign keys for SQLite
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn: Any, connection_record: Any) -> None:  # type: ignore
        """Enable foreign key constraints in SQLite."""
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def init_database(engine: Engine) -> None:
    """
    Initialize database schema by creating all tables.

    Args:
        engine: SQLAlchemy engine
    """
    Base.metadata.create_all(engine)


def get_session_factory(engine: Engine) -> sessionmaker[Session]:
    """
    Create session factory for database sessions.

    Args:
        engine: SQLAlchemy engine

    Returns:
        Session factory
    """
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_session(engine: Engine) -> Generator[Session, None, None]:
    """
    Get database session context manager.

    Args:
        engine: SQLAlchemy engine

    Yields:
        Database session
    """
    SessionLocal = get_session_factory(engine)
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
