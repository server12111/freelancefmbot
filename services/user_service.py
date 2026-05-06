from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Language, User, UserRole


async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    username: str | None,
    full_name: str,
) -> tuple[User, bool]:
    from sqlalchemy.exc import IntegrityError

    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user:
        user.full_name = full_name
        user.username = username
        await session.commit()
        return user, False

    user = User(telegram_id=telegram_id, username=username, full_name=full_name)
    session.add(user)
    try:
        await session.commit()
        await session.refresh(user)
        return user, True
    except IntegrityError:
        await session.rollback()
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one()
        return user, False


async def set_language(session: AsyncSession, user: User, lang: str) -> None:
    user.language = Language(lang)
    await session.commit()


async def set_role(session: AsyncSession, user: User, role: str) -> None:
    user.role = UserRole(role)
    await session.commit()


async def update_name(session: AsyncSession, user: User, name: str) -> None:
    user.full_name = name
    await session.commit()


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def ban_user(session: AsyncSession, user: User, reason: str) -> None:
    user.is_banned = True
    user.ban_reason = reason
    await session.commit()


async def unban_user(session: AsyncSession, user: User) -> None:
    user.is_banned = False
    user.ban_reason = None
    await session.commit()


async def update_rating(session: AsyncSession, user: User, new_rating: int) -> None:
    total = user.rating * user.rating_count + new_rating
    user.rating_count += 1
    user.rating = total / user.rating_count
    await session.commit()


async def get_all_users(session: AsyncSession) -> list[User]:
    result = await session.execute(select(User))
    return list(result.scalars().all())


async def get_stats(session: AsyncSession) -> dict:
    from database.models import Deal, DealStatus, Job, Transaction, TransactionType, TransactionStatus

    total_users = (await session.execute(select(func.count(User.id)))).scalar() or 0
    freelancers = (await session.execute(
        select(func.count(User.id)).where(User.role == UserRole.freelancer)
    )).scalar() or 0
    employers = (await session.execute(
        select(func.count(User.id)).where(User.role == UserRole.employer)
    )).scalar() or 0
    total_jobs = (await session.execute(select(func.count(Job.id)))).scalar() or 0
    active_deals = (await session.execute(
        select(func.count(Deal.id)).where(Deal.status == DealStatus.escrow_held)
    )).scalar() or 0
    completed_deals = (await session.execute(
        select(func.count(Deal.id)).where(Deal.status == DealStatus.completed)
    )).scalar() or 0
    volume_result = await session.execute(
        select(func.sum(Transaction.amount)).where(
            Transaction.type == TransactionType.escrow_release,
            Transaction.status == TransactionStatus.completed,
        )
    )
    volume = volume_result.scalar() or 0.0

    return {
        "users": total_users,
        "freelancers": freelancers,
        "employers": employers,
        "jobs": total_jobs,
        "deals": active_deals,
        "completed": completed_deals,
        "volume": volume,
    }
