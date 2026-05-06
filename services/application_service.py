from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import Application, ApplicationStatus, Job, User


async def create_application(
    session: AsyncSession,
    job: Job,
    freelancer: User,
    price: float,
    timeframe: str,
    comment: str | None,
) -> Application:
    app = Application(
        job_id=job.id,
        freelancer_id=freelancer.id,
        price=price,
        timeframe=timeframe,
        comment=comment or "",
    )
    session.add(app)
    await session.commit()
    await session.refresh(app)
    return app


async def get_application(session: AsyncSession, app_id: int) -> Application | None:
    result = await session.execute(
        select(Application)
        .where(Application.id == app_id)
        .options(
            selectinload(Application.job).selectinload(Job.employer),
            selectinload(Application.freelancer),
        )
    )
    return result.scalar_one_or_none()


async def get_freelancer_applications(
    session: AsyncSession, freelancer_id: int
) -> list[Application]:
    result = await session.execute(
        select(Application)
        .where(Application.freelancer_id == freelancer_id)
        .options(selectinload(Application.job))
        .order_by(Application.created_at.desc())
    )
    return list(result.scalars().all())


async def get_job_applications(
    session: AsyncSession, job_id: int
) -> list[Application]:
    result = await session.execute(
        select(Application)
        .where(
            and_(
                Application.job_id == job_id,
                Application.status == ApplicationStatus.pending,
            )
        )
        .options(selectinload(Application.freelancer))
        .order_by(Application.created_at.asc())
    )
    return list(result.scalars().all())


async def has_applied(
    session: AsyncSession, job_id: int, freelancer_id: int
) -> bool:
    result = await session.execute(
        select(Application).where(
            and_(
                Application.job_id == job_id,
                Application.freelancer_id == freelancer_id,
                Application.status != ApplicationStatus.withdrawn,
            )
        )
    )
    return result.scalar_one_or_none() is not None


async def accept_application(session: AsyncSession, app: Application) -> None:
    app.status = ApplicationStatus.accepted
    # Reject other pending applications for same job
    others = await session.execute(
        select(Application).where(
            and_(
                Application.job_id == app.job_id,
                Application.id != app.id,
                Application.status == ApplicationStatus.pending,
            )
        )
    )
    for other in others.scalars():
        other.status = ApplicationStatus.rejected
    await session.commit()


async def reject_application(session: AsyncSession, app: Application) -> None:
    app.status = ApplicationStatus.rejected
    await session.commit()


async def withdraw_application(session: AsyncSession, app: Application) -> None:
    app.status = ApplicationStatus.withdrawn
    await session.commit()
