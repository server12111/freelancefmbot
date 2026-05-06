from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import Deal, Review, User
from services.user_service import update_rating


async def create_review(
    session: AsyncSession,
    deal: Deal,
    reviewer: User,
    reviewee: User,
    rating: int,
    text: str | None,
) -> Review:
    review = Review(
        deal_id=deal.id,
        reviewer_id=reviewer.id,
        reviewee_id=reviewee.id,
        rating=rating,
        text=text,
    )
    session.add(review)
    await update_rating(session, reviewee, rating)
    await session.commit()
    await session.refresh(review)
    return review


async def get_reviews_for_user(session: AsyncSession, user_id: int) -> list[Review]:
    result = await session.execute(
        select(Review)
        .where(Review.reviewee_id == user_id)
        .options(selectinload(Review.reviewer))
        .order_by(Review.created_at.desc())
    )
    return list(result.scalars().all())


async def get_reviews_by_user(session: AsyncSession, user_id: int) -> list[Review]:
    result = await session.execute(
        select(Review)
        .where(Review.reviewer_id == user_id)
        .options(selectinload(Review.reviewee))
        .order_by(Review.created_at.desc())
    )
    return list(result.scalars().all())


async def has_reviewed(session: AsyncSession, deal_id: int, reviewer_id: int) -> bool:
    result = await session.execute(
        select(Review).where(
            and_(Review.deal_id == deal_id, Review.reviewer_id == reviewer_id)
        )
    )
    return result.scalar_one_or_none() is not None
