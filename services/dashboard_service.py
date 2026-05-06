from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Deal, DealStatus, Transaction, TransactionStatus, TransactionType, User


async def get_user_dashboard(session: AsyncSession, user_id: int) -> dict:
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        return {}

    completed = user.completed_orders or 0
    total_earned = user.total_earned or 0.0
    total_spent = user.total_spent or 0.0

    # Count all deals as employer to compute success rate
    total_employer_deals = (await session.execute(
        select(func.count(Deal.id)).where(
            Deal.employer_id == user_id,
            Deal.status.in_([DealStatus.completed, DealStatus.refunded, DealStatus.disputed]),
        )
    )).scalar() or 0

    total_freelancer_deals = (await session.execute(
        select(func.count(Deal.id)).where(
            Deal.freelancer_id == user_id,
            Deal.status.in_([DealStatus.completed, DealStatus.refunded, DealStatus.disputed]),
        )
    )).scalar() or 0

    total_closed = total_employer_deals + total_freelancer_deals
    success_rate = (completed / total_closed * 100) if total_closed > 0 else 0.0
    avg_order = (total_earned / completed) if completed > 0 else 0.0

    return {
        "completed_orders": completed,
        "total_earned": total_earned,
        "total_spent": total_spent,
        "success_rate": success_rate,
        "avg_order_value": avg_order,
        "rating": user.rating,
        "rating_count": user.rating_count,
        "level": user.level or "newbie",
    }
