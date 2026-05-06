from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Job, Promotion, PromotionType, Transaction, TransactionStatus, TransactionType, User

BOOST_COST = 5.0
VIP_COST = 15.0
BOOST_DAYS = 7
VIP_DAYS = 14


async def promote_job(
    session: AsyncSession,
    job: Job,
    employer: User,
    promo_type: PromotionType,
) -> bool:
    cost = BOOST_COST if promo_type == PromotionType.boost else VIP_COST
    days = BOOST_DAYS if promo_type == PromotionType.boost else VIP_DAYS

    if employer.balance < cost:
        return False

    employer.balance -= cost
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=days)

    if promo_type == PromotionType.boost:
        job.is_boosted = True
    else:
        job.is_vip = True
    job.promoted_until = expires

    promo = Promotion(
        job_id=job.id,
        employer_id=employer.id,
        type=promo_type,
        paid_amount=cost,
        expires_at=expires,
    )
    tx = Transaction(
        user_id=employer.id,
        type=TransactionType.promotion,
        amount=cost,
        status=TransactionStatus.completed,
        description=f"{promo_type.value} promotion for job #{job.id}",
    )
    session.add_all([promo, tx])
    await session.commit()
    return True


async def expire_promotions(session: AsyncSession) -> int:
    """Clear expired promotion flags. Returns number of jobs updated."""
    from sqlalchemy import select, and_
    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(Job).where(
            and_(
                Job.promoted_until != None,
                Job.promoted_until <= now,
            )
        )
    )
    jobs = list(result.scalars().all())
    for job in jobs:
        job.is_boosted = False
        job.is_vip = False
        job.promoted_until = None
    if jobs:
        await session.commit()
    return len(jobs)
