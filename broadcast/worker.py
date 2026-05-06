import asyncio

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from loguru import logger
from sqlalchemy import select

from broadcast.service import complete_broadcast, get_next_pending, mark_running
from database.connection import async_session_maker
from database.models import BroadcastJob, User


async def _send_one(bot: Bot, telegram_id: int, job: BroadcastJob) -> bool:
    try:
        if job.content_type == "text":
            await bot.send_message(telegram_id, job.text, parse_mode=job.parse_mode)
        elif job.content_type == "photo":
            await bot.send_photo(telegram_id, job.file_id, caption=job.text, parse_mode=job.parse_mode)
        elif job.content_type == "video":
            await bot.send_video(telegram_id, job.file_id, caption=job.text, parse_mode=job.parse_mode)
        return True
    except TelegramForbiddenError:
        return False
    except TelegramRetryAfter as e:
        await asyncio.sleep(e.retry_after + 1)
        return await _send_one(bot, telegram_id, job)
    except Exception as exc:
        logger.warning(f"Broadcast send error to {telegram_id}: {exc}")
        return False


async def _process_job(bot: Bot, job: BroadcastJob) -> None:
    async with async_session_maker() as session:
        await mark_running(session, job)
        result = await session.execute(select(User.telegram_id))
        tg_ids = list(result.scalars().all())

    sent = 0
    failed = 0
    for tg_id in tg_ids:
        ok = await _send_one(bot, tg_id, job)
        if ok:
            sent += 1
        else:
            failed += 1
        await asyncio.sleep(0.05)

    async with async_session_maker() as session:
        from sqlalchemy import select as sel
        from database.models import BroadcastJob as BJ
        fresh = (await session.execute(sel(BJ).where(BJ.id == job.id))).scalar_one()
        await complete_broadcast(session, fresh, sent, failed)

    logger.info(f"Broadcast #{job.id} done: sent={sent} failed={failed}")


async def broadcast_worker(bot: Bot) -> None:
    logger.info("Broadcast worker started.")
    while True:
        try:
            async with async_session_maker() as session:
                job = await get_next_pending(session)
            if job:
                await _process_job(bot, job)
            else:
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            logger.info("Broadcast worker stopped.")
            return
        except Exception as exc:
            logger.error(f"Broadcast worker error: {exc}")
            await asyncio.sleep(10)


async def auto_release_worker(bot: Bot) -> None:
    logger.info("Auto-release worker started.")
    while True:
        try:
            await _check_auto_releases(bot)
            await asyncio.sleep(300)  # Every 5 minutes
        except asyncio.CancelledError:
            logger.info("Auto-release worker stopped.")
            return
        except Exception as exc:
            logger.error(f"Auto-release worker error: {exc}")
            await asyncio.sleep(60)


async def _check_auto_releases(bot: Bot) -> None:
    from services.escrow_service import auto_release_deal, get_pending_auto_releases
    from services.notification_service import notify_auto_released
    from localization import get_i18n
    from sqlalchemy.orm import selectinload
    from database.models import Deal as D

    async with async_session_maker() as session:
        deals = await get_pending_auto_releases(session)

    for deal in deals:
        try:
            async with async_session_maker() as session:
                from sqlalchemy import select as sel
                fresh = (await session.execute(
                    sel(D).where(D.id == deal.id).options(
                        selectinload(D.job),
                        selectinload(D.employer),
                        selectinload(D.freelancer),
                    )
                )).scalar_one_or_none()
                if not fresh or fresh.status.value != "work_submitted":
                    continue
                result = await auto_release_deal(session, fresh)
                freelancer_tg = fresh.freelancer.telegram_id
                notif_enabled = bool(fresh.freelancer.notifications_enabled)
                lang = fresh.freelancer.language.value if fresh.freelancer.language else "en"
                escrow_cur = getattr(fresh, "escrow_currency", "usd")

            i18n = get_i18n(lang)
            if escrow_cur == "ton":
                amount_display = f"◎{result.amount:.4f} TON"
            else:
                amount_display = result.amount
            await notify_auto_released(bot, freelancer_tg, amount_display, i18n, notif_enabled, currency=escrow_cur)
            logger.info(f"Auto-released deal #{deal.id}, {escrow_cur}={result.amount}")
        except Exception as exc:
            logger.error(f"Auto-release failed for deal #{deal.id}: {exc}")


async def dispute_auto_close_worker(bot: Bot) -> None:
    logger.info("Dispute auto-close worker started.")
    while True:
        try:
            await _check_old_disputes(bot)
            await asyncio.sleep(3600 * 4)  # every 4 hours
        except asyncio.CancelledError:
            logger.info("Dispute auto-close worker stopped.")
            return
        except Exception as exc:
            logger.error(f"Dispute auto-close worker error: {exc}")
            await asyncio.sleep(600)


async def _check_old_disputes(bot: Bot) -> None:
    from services.escrow_service import get_old_disputes, resolve_dispute_to_employer
    from localization import get_i18n
    from sqlalchemy import select as sel
    from sqlalchemy.orm import selectinload
    from database.models import Deal as D

    async with async_session_maker() as session:
        deals = await get_old_disputes(session)

    for deal in deals:
        try:
            async with async_session_maker() as session:
                fresh = (await session.execute(
                    sel(D).where(D.id == deal.id).options(
                        selectinload(D.job),
                        selectinload(D.employer),
                        selectinload(D.freelancer),
                    )
                )).scalar_one_or_none()
                if not fresh or fresh.status.value != "disputed":
                    continue
                emp_tg = fresh.employer.telegram_id
                fl_tg = fresh.freelancer.telegram_id
                emp_lang = fresh.employer.language.value if fresh.employer.language else "en"
                fl_lang = fresh.freelancer.language.value if fresh.freelancer.language else "en"
                job_title = fresh.job.title
                await resolve_dispute_to_employer(session, fresh, admin_tg_id=None)

            emp_i18n = get_i18n(emp_lang)
            fl_i18n = get_i18n(fl_lang)
            try:
                await bot.send_message(emp_tg, emp_i18n("dispute_auto_closed_employer", title=job_title))
            except Exception:
                pass
            try:
                await bot.send_message(fl_tg, fl_i18n("dispute_auto_closed_freelancer", title=job_title))
            except Exception:
                pass
            logger.info(f"Auto-closed dispute for deal #{deal.id} (refunded to employer)")
        except Exception as exc:
            logger.error(f"Dispute auto-close failed for deal #{deal.id}: {exc}")


async def promotion_cleanup_worker() -> None:
    while True:
        try:
            async with async_session_maker() as session:
                from services.promotion_service import expire_promotions
                expired = await expire_promotions(session)
                if expired:
                    logger.info(f"Expired {expired} job promotion(s)")
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.error(f"Promotion cleanup error: {exc}")
            await asyncio.sleep(300)
