import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from loguru import logger

from broadcast.worker import auto_release_worker, broadcast_worker, dispute_auto_close_worker, promotion_cleanup_worker
from config import settings
from database.connection import init_db
from handlers import (
    admin,
    applications,
    chats,
    dashboard,
    deals,
    help_handler,
    invitations,
    jobs,
    payments_handler,
    profile,
    reviews,
    services,
    start,
)
from middleware.anti_spam import AntiSpamMiddleware
from middleware.cancel_state import CancelStateOnMenuMiddleware
from middleware.i18n import I18nMiddleware
from middleware.logging_mw import LoggingMiddleware


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logger.info("Initializing database...")
    await init_db()

    storage = MemoryStorage()   # dev: MemoryStorage; prod: switch to RedisStorage

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=storage)

    # ── Middleware (order matters: outer runs first) ────────────────────────
    dp.update.outer_middleware(LoggingMiddleware())
    dp.update.outer_middleware(AntiSpamMiddleware())
    dp.update.middleware(I18nMiddleware())
    dp.message.middleware(CancelStateOnMenuMiddleware())

    # ── Routers ────────────────────────────────────────────────────────────
    # admin and start routers first to intercept before generic handlers
    dp.include_router(admin.router)
    dp.include_router(start.router)
    dp.include_router(deals.router)
    dp.include_router(payments_handler.router)
    dp.include_router(applications.router)
    dp.include_router(jobs.router)
    dp.include_router(chats.router)
    dp.include_router(reviews.router)
    dp.include_router(profile.router)
    dp.include_router(dashboard.router)
    dp.include_router(invitations.router)
    dp.include_router(services.router)
    dp.include_router(help_handler.router)

    logger.info("Starting bot polling...")
    bcast_task = asyncio.create_task(broadcast_worker(bot))
    release_task = asyncio.create_task(auto_release_worker(bot))
    promo_task = asyncio.create_task(promotion_cleanup_worker())
    dispute_task = asyncio.create_task(dispute_auto_close_worker(bot))
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        bcast_task.cancel()
        release_task.cancel()
        promo_task.cancel()
        dispute_task.cancel()
        await bot.session.close()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
