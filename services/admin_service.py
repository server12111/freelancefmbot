from sqlalchemy.ext.asyncio import AsyncSession

from services.escrow_service import get_open_disputes


async def get_disputes(session: AsyncSession) -> list:
    return await get_open_disputes(session)
