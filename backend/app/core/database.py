from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

engine = create_async_engine(settings.database_url, echo=settings.app_env == "development")
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Sync engine for Alembic and Celery (which doesn't support async)
sync_engine = create_engine(settings.database_url_sync, echo=settings.app_env == "development")
sync_session_factory = sessionmaker(sync_engine, expire_on_commit=False)


async def get_db() -> AsyncSession:  # type: ignore[misc]
    async with async_session_factory() as session:
        yield session


# Helper for sync operations (used in Celery tasks)
def SessionLocal():  # noqa: N802 (沿用 SQLAlchemy 的命名习惯，全仓库都在用这个名字)
    """Create a new sync database session."""
    return sync_session_factory()
