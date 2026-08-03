from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from shared.db import get_async_session


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Request-scoped database session.

    Shared by every router so tests have a single ``dependency_overrides`` target
    and commit/rollback behaviour cannot differ between endpoints.
    """
    async with get_async_session() as session:
        yield session
