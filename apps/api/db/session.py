"""Database connection pool, session lifecycle, and automatic schema initialization.

Guarantees that on a clean clone, pgvector extension and all tables/indexes
are created automatically without manual SQL execution.
"""

from typing import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from apps.api.config import get_settings
from apps.api.db.models import Base

settings = get_settings()

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args={"connect_timeout": 2} if "psycopg" in settings.database_url else {},
    echo=False,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def init_db(target_engine=None) -> None:
    """Initialize database extension and tables.

    Executes 'CREATE EXTENSION IF NOT EXISTS vector' on PostgreSQL
    followed by creating all tables and indexes. Safe to run repeatedly.
    """
    db_engine = target_engine or engine
    # In PostgreSQL, initialize pgvector extension before creating vector columns
    if db_engine.dialect.name == "postgresql":
        with db_engine.connect() as conn:
            conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))

    Base.metadata.create_all(bind=db_engine)


def get_db() -> Generator[Session, None, None]:
    """Dependency that yields a database session and safely closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
