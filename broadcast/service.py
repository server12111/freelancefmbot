from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import BroadcastJob, User


async def create_broadcast(
    session: AsyncSession,
    admin_telegram_id: int,
    content_type: str,
    text: str | None = None,
    file_id: str | None = None,
    parse_mode: str = "HTML",
) -> BroadcastJob:
    result = await session.execute(select(User.id))
    total = len(result.scalars().all())

    job = BroadcastJob(
        admin_telegram_id=admin_telegram_id,
        content_type=content_type,
        text=text,
        file_id=file_id,
        parse_mode=parse_mode,
        total_users=total,
        status="pending",
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


async def get_next_pending(session: AsyncSession) -> BroadcastJob | None:
    result = await session.execute(
        select(BroadcastJob)
        .where(BroadcastJob.status == "pending")
        .order_by(BroadcastJob.created_at.asc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def mark_running(session: AsyncSession, job: BroadcastJob) -> None:
    job.status = "running"
    await session.commit()


async def complete_broadcast(
    session: AsyncSession,
    job: BroadcastJob,
    sent: int,
    failed: int,
) -> None:
    job.status = "completed"
    job.sent_count = sent
    job.failed_count = failed
    job.completed_at = datetime.now(timezone.utc)
    await session.commit()


async def get_recent_broadcasts(session: AsyncSession, limit: int = 10) -> list[BroadcastJob]:
    result = await session.execute(
        select(BroadcastJob).order_by(BroadcastJob.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())
