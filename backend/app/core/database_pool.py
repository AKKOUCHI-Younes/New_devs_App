import asyncio
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ..config import settings


logger = logging.getLogger(__name__)


def _asyncpg_url(database_url: str) -> str:
    """Return a PostgreSQL URL suitable for SQLAlchemy's async engine."""
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    raise ValueError("DATABASE_URL must be a PostgreSQL connection URL")


class DatabasePool:
    """Process-wide, lazily initialized asynchronous database pool."""

    def __init__(self) -> None:
        self.engine: Optional[AsyncEngine] = None
        self.session_factory: Optional[async_sessionmaker[AsyncSession]] = None
        self._initialization_lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize the pool once, including under concurrent first requests."""
        if self.session_factory is not None:
            return

        async with self._initialization_lock:
            if self.session_factory is not None:
                return

            engine = create_async_engine(
                _asyncpg_url(settings.database_url),
                pool_size=20,
                max_overflow=30,
                pool_pre_ping=True,
                pool_recycle=3600,
                echo=False,
            )
            self.engine = engine
            self.session_factory = async_sessionmaker(
                bind=engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
            logger.info("Database connection pool initialized")

    async def close(self) -> None:
        """Dispose of all pooled connections and allow later reinitialization."""
        async with self._initialization_lock:
            engine = self.engine
            self.engine = None
            self.session_factory = None
            if engine is not None:
                await engine.dispose()

    def get_session(self) -> AsyncSession:
        """Create a database session from the initialized pool."""
        if self.session_factory is None:
            raise RuntimeError("Database pool has not been initialized")
        return self.session_factory()


db_pool = DatabasePool()


async def get_db_session():
    """FastAPI dependency that provides one managed database session."""
    await db_pool.initialize()
    async with db_pool.get_session() as session:
        yield session
