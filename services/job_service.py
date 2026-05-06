from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import Application, Deal, DealStatus, Job, JobCategory, JobStatus, User


async def create_job(
    session: AsyncSession,
    employer: User,
    title: str,
    description: str,
    category: str,
    budget: float,
    deadline: str,
) -> Job:
    job = Job(
        employer_id=employer.id,
        title=title,
        description=description,
        category=JobCategory(category),
        budget=budget,
        deadline=deadline,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


async def get_job(session: AsyncSession, job_id: int) -> Job | None:
    result = await session.execute(
        select(Job)
        .where(Job.id == job_id)
        .options(selectinload(Job.employer), selectinload(Job.applications))
    )
    return result.scalar_one_or_none()


async def get_open_jobs(
    session: AsyncSession,
    category: str | None = None,
    budget_min: float | None = None,
    budget_max: float | None = None,
    keyword: str | None = None,
    funded_only: bool = False,
    min_employer_rating: float | None = None,
) -> list[Job]:
    filters = [Job.status == JobStatus.open]

    if category:
        filters.append(Job.category == JobCategory(category))
    if budget_min is not None:
        filters.append(Job.budget >= budget_min)
    if budget_max is not None:
        filters.append(Job.budget <= budget_max)
    if keyword:
        kw = f"%{keyword.lower()}%"
        filters.append(or_(
            Job.title.ilike(kw),
            Job.description.ilike(kw),
        ))

    stmt = (
        select(Job)
        .where(and_(*filters))
        .options(selectinload(Job.employer), selectinload(Job.applications))
    )

    if funded_only:
        stmt = stmt.join(Deal, Deal.job_id == Job.id).where(
            Deal.status == DealStatus.escrow_held
        )

    result = await session.execute(stmt)
    jobs = list(result.scalars().unique().all())

    if min_employer_rating is not None:
        jobs = [j for j in jobs if (j.employer.rating or 0.0) >= min_employer_rating]

    # Sort: VIP first, then boosted, then newest
    def _sort_key(j: Job):
        return (0 if j.is_vip else (1 if j.is_boosted else 2), -j.id)

    jobs.sort(key=_sort_key)
    return jobs


async def get_employer_jobs(session: AsyncSession, employer_id: int) -> list[Job]:
    result = await session.execute(
        select(Job)
        .where(Job.employer_id == employer_id)
        .options(selectinload(Job.applications))
        .order_by(Job.created_at.desc())
    )
    return list(result.scalars().all())


async def cancel_job(session: AsyncSession, job: Job) -> None:
    job.status = JobStatus.cancelled
    for app in job.applications:
        if app.status.value == "pending":
            app.status = "rejected"
    await session.commit()


async def set_job_in_progress(session: AsyncSession, job: Job) -> None:
    job.status = JobStatus.in_progress
    await session.commit()


async def complete_job(session: AsyncSession, job: Job) -> None:
    job.status = JobStatus.completed
    await session.commit()
