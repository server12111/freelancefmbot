from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Deal, DealStatus, Job, Transaction, TransactionStatus, TransactionType, User, UserRole


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _days_ago(n: int) -> datetime:
    return _now() - timedelta(days=n)


async def get_user_counts(session: AsyncSession) -> dict:
    today_start = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())
    month_start = today_start.replace(day=1)
    year_start = today_start.replace(month=1, day=1)

    all_users = list((await session.execute(select(User.created_at))).scalars().all())

    def _count(since):
        if since is None:
            return len(all_users)
        return sum(1 for dt in all_users if dt and dt >= since)

    return {
        "today":  _count(today_start),
        "week":   _count(week_start),
        "month":  _count(month_start),
        "year":   _count(year_start),
        "total":  _count(None),
    }


async def get_registrations_by_day(session: AsyncSession, days: int = 30) -> dict[str, int]:
    since = _days_ago(days)
    result = await session.execute(
        select(User.created_at).where(User.created_at >= since)
    )
    dates = [dt.date() if dt else None for dt in result.scalars()]
    dates = [d for d in dates if d]

    buckets: dict[str, int] = {}
    for i in range(days):
        d = (_now() - timedelta(days=days - 1 - i)).date()
        buckets[d.strftime("%m/%d")] = 0
    for d in dates:
        key = d.strftime("%m/%d")
        if key in buckets:
            buckets[key] += 1
    return buckets


async def get_revenue_by_day(session: AsyncSession, days: int = 30) -> dict[str, float]:
    since = _days_ago(days)
    result = await session.execute(
        select(Transaction.created_at, Transaction.amount).where(
            Transaction.type == TransactionType.escrow_release,
            Transaction.status == TransactionStatus.completed,
            Transaction.created_at >= since,
        )
    )
    rows = result.fetchall()

    buckets: dict[str, float] = {}
    for i in range(days):
        d = (_now() - timedelta(days=days - 1 - i)).date()
        buckets[d.strftime("%m/%d")] = 0.0
    for dt, amount in rows:
        if dt:
            key = dt.date().strftime("%m/%d")
            if key in buckets:
                buckets[key] += amount
    return buckets


async def get_platform_stats(session: AsyncSession) -> dict:
    total_users = (await session.execute(select(func.count(User.id)))).scalar() or 0
    total_jobs = (await session.execute(select(func.count(Job.id)))).scalar() or 0
    completed_deals = (await session.execute(
        select(func.count(Deal.id)).where(Deal.status == DealStatus.completed)
    )).scalar() or 0
    revenue_row = await session.execute(
        select(func.sum(Transaction.amount)).where(
            Transaction.type == TransactionType.escrow_release,
            Transaction.status == TransactionStatus.completed,
        )
    )
    total_revenue = revenue_row.scalar() or 0.0

    # Users who completed at least one deal
    users_with_deals = (await session.execute(
        select(func.count(func.distinct(Deal.employer_id))).where(Deal.status == DealStatus.completed)
    )).scalar() or 0
    conversion = (users_with_deals / total_users * 100) if total_users > 0 else 0.0

    return {
        "total_users":    total_users,
        "total_jobs":     total_jobs,
        "completed_deals": completed_deals,
        "total_revenue":  total_revenue,
        "conversion":     conversion,
    }
