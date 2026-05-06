from aiogram import F, Router
from aiogram.types import CallbackQuery

from database.connection import async_session_maker
from database.models import User
from services.dashboard_service import get_user_dashboard
from services.level_service import level_badge
from utils.keyboards import dashboard_kb

router = Router()


@router.callback_query(F.data == "dashboard")
async def cb_dashboard(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    if not db_user:
        await callback.answer()
        return

    async with async_session_maker() as session:
        stats = await get_user_dashboard(session, db_user.id)

    badge = level_badge(stats["level"], i18n)
    success = f"{stats['success_rate']:.1f}%" if stats["success_rate"] is not None else "—"
    avg = f"${stats['avg_order_value']:.2f}" if stats["avg_order_value"] else "—"
    rating = f"{stats['rating']:.1f} ⭐" if stats["rating"] else "—"

    text = (
        f"{i18n('dashboard_title')}\n\n"
        f"{i18n('dashboard_level', level=badge)}\n"
        f"{i18n('dashboard_completed_orders', count=stats['completed_orders'])}\n"
        f"{i18n('dashboard_total_earned', amount=stats['total_earned'])}\n"
        f"{i18n('dashboard_total_spent', amount=stats['total_spent'])}\n"
        f"{i18n('dashboard_success_rate', pct=success)}\n"
        f"{i18n('dashboard_avg_order', avg=avg)}\n"
        f"{i18n('dashboard_rating', rating=rating)}"
    )
    await callback.message.edit_text(text, reply_markup=dashboard_kb(i18n))
    await callback.answer()


@router.callback_query(F.data == "profile_back")
async def cb_profile_back(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    from handlers.profile import show_profile
    from database.connection import async_session_maker
    from services.user_service import get_user_by_telegram_id
    async with async_session_maker() as session:
        user = await get_user_by_telegram_id(session, callback.from_user.id)
    await show_profile(callback, i18n, user)
    await callback.answer()
