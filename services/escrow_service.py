from datetime import datetime, timedelta, timezone
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import settings
from database.models import (
    Application, Deal, DealStatus, DisputeLog, Job,
    Transaction, TransactionStatus, TransactionType, User,
)

AUTO_RELEASE_HOURS = 72
DISPUTE_AUTO_CLOSE_DAYS = 7


class ReleaseResult(NamedTuple):
    amount: float
    currency: str  # "usd" or "ton"


def _calc_fee(amount: float) -> float:
    return round(amount * settings.PLATFORM_FEE_PERCENT / 100, 2)


async def create_deal(
    session: AsyncSession,
    job: Job,
    application: Application,
) -> Deal:
    fee = _calc_fee(application.price)
    deal = Deal(
        job_id=job.id,
        application_id=application.id,
        employer_id=job.employer_id,
        freelancer_id=application.freelancer_id,
        amount=application.price,
        platform_fee=fee,
    )
    session.add(deal)
    await session.commit()
    await session.refresh(deal)
    return deal


async def get_deal(session: AsyncSession, deal_id: int) -> Deal | None:
    result = await session.execute(
        select(Deal)
        .where(Deal.id == deal_id)
        .options(
            selectinload(Deal.job),
            selectinload(Deal.employer),
            selectinload(Deal.freelancer),
            selectinload(Deal.application),
            selectinload(Deal.dispute_logs),
        )
    )
    return result.scalar_one_or_none()


async def get_deal_by_job(session: AsyncSession, job_id: int) -> Deal | None:
    result = await session.execute(
        select(Deal)
        .where(Deal.job_id == job_id)
        .options(
            selectinload(Deal.job),
            selectinload(Deal.employer),
            selectinload(Deal.freelancer),
        )
    )
    return result.scalar_one_or_none()


async def fund_escrow(session: AsyncSession, deal: Deal, employer: User) -> bool:
    """Fund escrow from USD balance."""
    if employer.balance < deal.amount:
        return False

    employer.balance -= deal.amount
    employer.total_spent = (employer.total_spent or 0.0) + deal.amount
    deal.status = DealStatus.escrow_held
    deal.escrow_currency = "usd"

    tx = Transaction(
        user_id=employer.id,
        deal_id=deal.id,
        type=TransactionType.escrow_hold,
        amount=deal.amount,
        status=TransactionStatus.completed,
        description=f"Escrow hold (USD) for deal #{deal.id}",
    )
    session.add(tx)
    await session.commit()
    return True


async def fund_escrow_ton(session: AsyncSession, deal: Deal, employer: User, ton_rate: float) -> bool:
    """Fund escrow from TON balance. ton_rate = USD per 1 TON."""
    ton_amount = round(deal.amount / ton_rate, 6)
    if employer.balance_ton < ton_amount:
        return False

    employer.balance_ton -= ton_amount
    employer.total_spent = (employer.total_spent or 0.0) + deal.amount
    deal.status = DealStatus.escrow_held
    deal.escrow_currency = "ton"
    deal.escrow_ton_amount = ton_amount

    tx = Transaction(
        user_id=employer.id,
        deal_id=deal.id,
        type=TransactionType.escrow_hold,
        amount=deal.amount,
        status=TransactionStatus.completed,
        description=f"Escrow hold (TON) for deal #{deal.id}: {ton_amount:.6f} TON",
    )
    session.add(tx)
    await session.commit()
    return True


async def submit_work(session: AsyncSession, deal: Deal, description: str) -> None:
    now = datetime.now(timezone.utc)
    deal.status = DealStatus.work_submitted
    deal.work_description = description
    deal.submission_time = now
    deal.auto_release_at = now + timedelta(hours=AUTO_RELEASE_HOURS)
    await session.commit()


async def _release_to_freelancer(session: AsyncSession, deal: Deal) -> ReleaseResult:
    """Core release logic shared by confirm and auto-release. Returns (amount, currency)."""
    is_ton = getattr(deal, "escrow_currency", "usd") == "ton" and deal.escrow_ton_amount

    if is_ton:
        ton_fee = round(deal.escrow_ton_amount * settings.PLATFORM_FEE_PERCENT / 100, 6)
        ton_net = round(deal.escrow_ton_amount - ton_fee, 6)
        deal.freelancer.balance_ton += ton_net
        deal.freelancer.total_earned = (deal.freelancer.total_earned or 0.0) + (deal.amount - deal.platform_fee)
        deal.freelancer.completed_orders = (deal.freelancer.completed_orders or 0) + 1
        deal.employer.completed_orders = (deal.employer.completed_orders or 0) + 1
        deal.status = DealStatus.completed
        deal.completed_at = datetime.now(timezone.utc)
        deal.job.status = "completed"

        release_tx = Transaction(
            user_id=deal.freelancer_id, deal_id=deal.id,
            type=TransactionType.escrow_release, amount=ton_net,
            status=TransactionStatus.completed,
            description=f"TON payment for deal #{deal.id}: {ton_net:.6f} TON",
        )
        fee_tx = Transaction(
            user_id=deal.freelancer_id, deal_id=deal.id,
            type=TransactionType.platform_fee, amount=ton_fee,
            status=TransactionStatus.completed,
            description=f"TON platform fee for deal #{deal.id}",
        )
        session.add_all([release_tx, fee_tx])
        from services.level_service import refresh_level
        await refresh_level(session, deal.freelancer)
        await refresh_level(session, deal.employer)
        return ReleaseResult(ton_net, "ton")
    else:
        net = deal.amount - deal.platform_fee
        deal.freelancer.balance += net
        deal.freelancer.total_earned = (deal.freelancer.total_earned or 0.0) + net
        deal.freelancer.completed_orders = (deal.freelancer.completed_orders or 0) + 1
        deal.employer.completed_orders = (deal.employer.completed_orders or 0) + 1
        deal.status = DealStatus.completed
        deal.completed_at = datetime.now(timezone.utc)
        deal.job.status = "completed"

        release_tx = Transaction(
            user_id=deal.freelancer_id, deal_id=deal.id,
            type=TransactionType.escrow_release, amount=net,
            status=TransactionStatus.completed,
            description=f"Payment for deal #{deal.id}",
        )
        fee_tx = Transaction(
            user_id=deal.freelancer_id, deal_id=deal.id,
            type=TransactionType.platform_fee, amount=deal.platform_fee,
            status=TransactionStatus.completed,
            description=f"Platform fee for deal #{deal.id}",
        )
        session.add_all([release_tx, fee_tx])
        from services.level_service import refresh_level
        await refresh_level(session, deal.freelancer)
        await refresh_level(session, deal.employer)
        return ReleaseResult(net, "usd")


async def confirm_work(session: AsyncSession, deal: Deal, freelancer: User) -> ReleaseResult:
    result = await _release_to_freelancer(session, deal)
    await session.commit()
    return result


async def auto_release_deal(session: AsyncSession, deal: Deal) -> ReleaseResult:
    deal.auto_released = True
    log = DisputeLog(
        deal_id=deal.id,
        admin_telegram_id=None,
        action="auto_released",
        note=f"Auto-released after {AUTO_RELEASE_HOURS}h of inactivity",
    )
    session.add(log)
    result = await _release_to_freelancer(session, deal)
    await session.commit()
    return result


async def open_dispute(session: AsyncSession, deal: Deal, reason: str, opened_by_id: int | None = None) -> None:
    now = datetime.now(timezone.utc)
    deal.status = DealStatus.disputed
    deal.dispute_reason = reason
    deal.dispute_opened_at = now
    deal.job.status = "disputed"
    log = DisputeLog(
        deal_id=deal.id,
        admin_telegram_id=None,
        action="dispute_opened",
        note=f"Opened by user #{opened_by_id}: {reason}",
    )
    session.add(log)
    await session.commit()


async def resolve_dispute_to_employer(session: AsyncSession, deal: Deal, admin_tg_id: int | None = None) -> None:
    is_ton = getattr(deal, "escrow_currency", "usd") == "ton" and deal.escrow_ton_amount
    if is_ton:
        deal.employer.balance_ton += deal.escrow_ton_amount
        refund_amount = deal.escrow_ton_amount
    else:
        deal.employer.balance += deal.amount
        refund_amount = deal.amount

    deal.status = DealStatus.refunded
    deal.job.status = "cancelled"

    tx = Transaction(
        user_id=deal.employer_id, deal_id=deal.id,
        type=TransactionType.escrow_refund, amount=refund_amount,
        status=TransactionStatus.completed,
        description=f"Dispute resolved: refund to employer #{deal.id}",
    )
    log = DisputeLog(
        deal_id=deal.id, admin_telegram_id=admin_tg_id,
        action="resolved_employer", note="Full refund to employer",
    )
    session.add_all([tx, log])
    await session.commit()


async def resolve_dispute_to_freelancer(session: AsyncSession, deal: Deal, admin_tg_id: int | None = None) -> None:
    is_ton = getattr(deal, "escrow_currency", "usd") == "ton" and deal.escrow_ton_amount
    if is_ton:
        ton_fee = round(deal.escrow_ton_amount * settings.PLATFORM_FEE_PERCENT / 100, 6)
        ton_net = round(deal.escrow_ton_amount - ton_fee, 6)
        deal.freelancer.balance_ton += ton_net
        deal.freelancer.total_earned = (deal.freelancer.total_earned or 0.0) + (deal.amount - deal.platform_fee)
        release_amount = ton_net
    else:
        net = deal.amount - deal.platform_fee
        deal.freelancer.balance += net
        deal.freelancer.total_earned = (deal.freelancer.total_earned or 0.0) + net
        release_amount = net

    deal.freelancer.completed_orders = (deal.freelancer.completed_orders or 0) + 1
    deal.status = DealStatus.completed
    deal.completed_at = datetime.now(timezone.utc)
    deal.job.status = "completed"

    tx = Transaction(
        user_id=deal.freelancer_id, deal_id=deal.id,
        type=TransactionType.escrow_release, amount=release_amount,
        status=TransactionStatus.completed,
        description=f"Dispute resolved: payment to freelancer #{deal.id}",
    )
    log = DisputeLog(
        deal_id=deal.id, admin_telegram_id=admin_tg_id,
        action="resolved_freelancer", note="Full payment to freelancer",
    )
    session.add_all([tx, log])
    from services.level_service import refresh_level
    await refresh_level(session, deal.freelancer)
    await session.commit()


async def resolve_dispute_split(session: AsyncSession, deal: Deal, admin_tg_id: int | None = None) -> None:
    is_ton = getattr(deal, "escrow_currency", "usd") == "ton" and deal.escrow_ton_amount
    if is_ton:
        half_ton = round(deal.escrow_ton_amount / 2, 6)
        ton_fee_half = round(deal.escrow_ton_amount * settings.PLATFORM_FEE_PERCENT / 100 / 2, 6)
        fl_ton = round(half_ton - ton_fee_half, 6)
        deal.employer.balance_ton += half_ton
        deal.freelancer.balance_ton += max(fl_ton, 0)
        emp_amount, fl_amount = half_ton, max(fl_ton, 0)
    else:
        half = round(deal.amount / 2, 2)
        fl_half = round(half - deal.platform_fee / 2, 2)
        deal.employer.balance += half
        deal.freelancer.balance += max(fl_half, 0)
        emp_amount, fl_amount = half, max(fl_half, 0)

    deal.status = DealStatus.refunded
    deal.job.status = "cancelled"

    txs = [
        Transaction(
            user_id=deal.employer_id, deal_id=deal.id,
            type=TransactionType.escrow_refund, amount=emp_amount,
            status=TransactionStatus.completed,
            description=f"Dispute split: 50% refund to employer #{deal.id}",
        ),
        Transaction(
            user_id=deal.freelancer_id, deal_id=deal.id,
            type=TransactionType.escrow_release, amount=fl_amount,
            status=TransactionStatus.completed,
            description=f"Dispute split: 50% to freelancer #{deal.id}",
        ),
    ]
    log = DisputeLog(
        deal_id=deal.id, admin_telegram_id=admin_tg_id,
        action="resolved_split", note="50/50 split resolution",
    )
    session.add_all([*txs, log])
    await session.commit()


async def get_open_disputes(session: AsyncSession) -> list[Deal]:
    result = await session.execute(
        select(Deal)
        .where(Deal.status == DealStatus.disputed)
        .options(
            selectinload(Deal.job),
            selectinload(Deal.employer),
            selectinload(Deal.freelancer),
            selectinload(Deal.dispute_logs),
        )
        .order_by(Deal.updated_at.asc())
    )
    return list(result.scalars().all())


async def get_active_deals(session: AsyncSession) -> list[Deal]:
    result = await session.execute(
        select(Deal)
        .where(Deal.status.in_([DealStatus.escrow_held, DealStatus.work_submitted]))
        .options(selectinload(Deal.job), selectinload(Deal.employer), selectinload(Deal.freelancer))
    )
    return list(result.scalars().all())


async def get_pending_auto_releases(session: AsyncSession) -> list[Deal]:
    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(Deal)
        .where(
            Deal.status == DealStatus.work_submitted,
            Deal.auto_release_at != None,
            Deal.auto_release_at <= now,
            Deal.auto_released == False,
        )
        .options(
            selectinload(Deal.job),
            selectinload(Deal.employer),
            selectinload(Deal.freelancer),
        )
    )
    return list(result.scalars().all())


async def get_old_disputes(session: AsyncSession) -> list[Deal]:
    """Return disputed deals open longer than DISPUTE_AUTO_CLOSE_DAYS days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=DISPUTE_AUTO_CLOSE_DAYS)
    result = await session.execute(
        select(Deal)
        .where(
            Deal.status == DealStatus.disputed,
            Deal.dispute_opened_at != None,
            Deal.dispute_opened_at <= cutoff,
        )
        .options(
            selectinload(Deal.job),
            selectinload(Deal.employer),
            selectinload(Deal.freelancer),
        )
    )
    return list(result.scalars().all())
