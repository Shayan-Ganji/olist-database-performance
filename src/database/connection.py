"""
Database connection and session lifecycle management.
Provides thread-safe SQLAlchemy engine, connection context managers,
and ensures strict disposal of lingering database connections.
"""

import os
from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine, Engine, Connection

# Default connection settings targeting local high-performance PostgreSQL instance
DEFAULT_DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres@127.0.0.1:5432/olist_db"
)

_ENGINE: Engine | None = None


def get_engine(url: str = DEFAULT_DB_URL) -> Engine:
    """Singleton getter for SQLAlchemy Engine configured with connection pooling."""
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = create_engine(
            url,
            pool_size=10,
            max_overflow=20,
            pool_timeout=30,
            pool_pre_ping=True,  # Proactively validates socket liveness
        )
    return _ENGINE


@contextmanager
def get_connection(url: str = DEFAULT_DB_URL) -> Generator[Connection, None, None]:
    """
    Explicit connection context manager.
    Guarantees immediate socket return to pool upon block exit or unhandled exception,
    strictly preventing connection leaks in long-running notebooks.
    """
    engine = get_engine(url)
    connection = engine.connect()
    try:
        yield connection
    finally:
        connection.close()
