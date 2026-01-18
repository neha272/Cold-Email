from __future__ import annotations

from pathlib import Path

import pytest
from cold_emailer.state_store.db import create_database_engine, get_session_factory, init_database
from sqlalchemy.orm import Session


@pytest.fixture()
def db_session(tmp_path: Path) -> Session:
    """
    Provide a temporary SQLite Session for tests.

    Uses a file-based SQLite DB (not :memory:) so behavior is consistent across
    SQLAlchemy connections.
    """
    db_path = tmp_path / "test_state.db"
    engine = create_database_engine(str(db_path), echo=False)
    init_database(engine)

    SessionLocal = get_session_factory(engine)
    session = SessionLocal()
    try:
        yield session
        session.commit()
    finally:
        session.close()
        engine.dispose()
