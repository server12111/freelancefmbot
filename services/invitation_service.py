from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import Application, ApplicationStatus, Invitation, InvitationStatus, Job, User


async def send_invitation(
    session: AsyncSession,
    employer: User,
    freelancer: User,
    job: Job,
    message: str | None = None,
) -> Invitation:
    inv = Invitation(
        employer_id=employer.id,
        freelancer_id=freelancer.id,
        job_id=job.id,
        message=message,
    )
    session.add(inv)
    await session.commit()
    await session.refresh(inv)
    return inv


async def get_invitation(session: AsyncSession, inv_id: int) -> Invitation | None:
    result = await session.execute(
        select(Invitation)
        .where(Invitation.id == inv_id)
        .options(
            selectinload(Invitation.employer),
            selectinload(Invitation.freelancer),
            selectinload(Invitation.job),
        )
    )
    return result.scalar_one_or_none()


async def get_pending_invitations(session: AsyncSession, freelancer_id: int) -> list[Invitation]:
    result = await session.execute(
        select(Invitation)
        .where(
            Invitation.freelancer_id == freelancer_id,
            Invitation.status == InvitationStatus.pending,
        )
        .options(selectinload(Invitation.employer), selectinload(Invitation.job))
        .order_by(Invitation.created_at.desc())
    )
    return list(result.scalars().all())


async def accept_invitation(session: AsyncSession, inv: Invitation) -> Application:
    inv.status = InvitationStatus.accepted
    app = Application(
        job_id=inv.job_id,
        freelancer_id=inv.freelancer_id,
        price=inv.job.budget,
        timeframe="As agreed",
        comment=f"Accepted invitation from {inv.employer.full_name}",
        status=ApplicationStatus.pending,
    )
    session.add(app)
    await session.commit()
    await session.refresh(app)
    return app


async def decline_invitation(session: AsyncSession, inv: Invitation) -> None:
    inv.status = InvitationStatus.declined
    await session.commit()


async def already_invited(session: AsyncSession, employer_id: int, freelancer_id: int, job_id: int) -> bool:
    result = await session.execute(
        select(Invitation).where(
            and_(
                Invitation.employer_id == employer_id,
                Invitation.freelancer_id == freelancer_id,
                Invitation.job_id == job_id,
                Invitation.status == InvitationStatus.pending,
            )
        )
    )
    return result.scalar_one_or_none() is not None
