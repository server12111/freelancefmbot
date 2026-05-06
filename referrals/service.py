import secrets
import string

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import ReferralLink, User


def _gen_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def create_link(session: AsyncSession, name: str, admin_telegram_id: int) -> ReferralLink:
    for _ in range(5):
        code = _gen_code()
        existing = await get_by_code(session, code)
        if not existing:
            break

    link = ReferralLink(code=code, name=name, created_by_admin_id=admin_telegram_id)
    session.add(link)
    await session.commit()
    await session.refresh(link)
    return link


async def get_by_code(session: AsyncSession, code: str) -> ReferralLink | None:
    result = await session.execute(select(ReferralLink).where(ReferralLink.code == code))
    return result.scalar_one_or_none()


async def get_all_links(session: AsyncSession) -> list[ReferralLink]:
    result = await session.execute(select(ReferralLink).order_by(ReferralLink.created_at.desc()))
    return list(result.scalars().all())


async def get_link_by_id(session: AsyncSession, link_id: int) -> ReferralLink | None:
    result = await session.execute(select(ReferralLink).where(ReferralLink.id == link_id))
    return result.scalar_one_or_none()


async def attribute_user(session: AsyncSession, user: User, link: ReferralLink) -> None:
    if user.referral_link_id:
        return
    user.referral_link_id = link.id
    link.users_count += 1
    await session.commit()


async def increment_orders(session: AsyncSession, link_id: int) -> None:
    link = await get_link_by_id(session, link_id)
    if link:
        link.orders_count += 1
        await session.commit()


async def add_revenue(session: AsyncSession, link_id: int, amount: float) -> None:
    link = await get_link_by_id(session, link_id)
    if link:
        link.revenue += amount
        await session.commit()
