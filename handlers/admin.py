import os
import sys

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, FSInputFile, Message
from loguru import logger

from analytics.charts import generate_referral_chart, generate_revenue_chart, generate_users_chart
from analytics.service import get_platform_stats, get_registrations_by_day, get_revenue_by_day, get_user_counts
from broadcast.service import create_broadcast, get_recent_broadcasts
from config import settings
from sqlalchemy import select as sa_select

from database.connection import async_session_maker
from database.models import BotSettings, User
from referrals.service import create_link, get_all_links
from services.escrow_service import get_open_disputes, resolve_dispute_to_employer, resolve_dispute_to_freelancer, resolve_dispute_split
from services.notification_service import notify
from services.user_service import ban_user, get_user_by_id, get_user_by_telegram_id, unban_user
from states import AdminState
from utils.keyboards import (
    admin_broadcast_confirm_kb,
    admin_broadcast_menu_kb,
    admin_broadcast_type_kb,
    admin_db_kb,
    admin_dispute_kb,
    admin_kb,
    admin_moderation_kb,
    admin_referrals_kb,
    admin_settings_kb,
    admin_stats_kb,
)

router = Router()


def is_admin(user_id: int) -> bool:
    return user_id in settings.ADMIN_IDS


# ── Main panel ─────────────────────────────────────────────────────────────

@router.message(Command("admin"))
async def cmd_admin(message: Message, i18n, db_user: User | None) -> None:
    if not is_admin(message.from_user.id):
        await message.answer(i18n("error_permission"))
        return
    await message.answer(i18n("admin_panel"), reply_markup=admin_kb(i18n))


@router.callback_query(F.data == "admin_back")
async def cb_admin_back(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    await state.clear()
    await callback.message.edit_text(i18n("admin_panel"), reply_markup=admin_kb(i18n))
    await callback.answer()


# ── Statistics ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:stats")
async def cb_admin_stats(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer(i18n("error_permission"))
        return

    async with async_session_maker() as session:
        counts = await get_user_counts(session)
        stats = await get_platform_stats(session)

    lines = [
        i18n("admin_stats_title"),
        i18n("admin_users_today",     count=counts["today"]),
        i18n("admin_users_week",      count=counts["week"]),
        i18n("admin_users_month",     count=counts["month"]),
        i18n("admin_users_year",      count=counts["year"]),
        i18n("admin_users_total",     count=counts["total"]),
        "",
        i18n("admin_total_orders",    count=stats["total_jobs"]),
        i18n("admin_completed_deals", count=stats["completed_deals"]),
        i18n("admin_total_revenue",   amount=stats["total_revenue"]),
        i18n("admin_conversion",      pct=stats["conversion"]),
    ]
    await callback.message.edit_text("\n".join(lines), reply_markup=admin_stats_kb(i18n))
    await callback.answer()


@router.callback_query(F.data == "admin:stats_users_chart")
async def cb_users_chart(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer(i18n("error_permission"))
        return
    async with async_session_maker() as session:
        data = await get_registrations_by_day(session, days=30)

    buf = generate_users_chart(data)
    photo = BufferedInputFile(buf.read(), filename="users_chart.png")
    await callback.message.answer_photo(photo, caption="📈 User Growth — Last 30 Days")
    await callback.answer()


@router.callback_query(F.data == "admin:stats_revenue_chart")
async def cb_revenue_chart(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer(i18n("error_permission"))
        return
    async with async_session_maker() as session:
        data = await get_revenue_by_day(session, days=30)

    buf = generate_revenue_chart(data)
    photo = BufferedInputFile(buf.read(), filename="revenue_chart.png")
    await callback.message.answer_photo(photo, caption="💰 Revenue — Last 30 Days")
    await callback.answer()


# ── Referral links ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:referrals")
async def cb_admin_referrals(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer(i18n("error_permission"))
        return

    async with async_session_maker() as session:
        links = await get_all_links(session)

    if not links:
        text = f"{i18n('admin_referrals_title')}\n\n{i18n('admin_no_referrals')}"
    else:
        items = [i18n("admin_referral_item", name=l.name, users=l.users_count, orders=l.orders_count, revenue=l.revenue) for l in links]
        text = f"{i18n('admin_referrals_title')}\n\n" + "\n\n".join(items)

    await callback.message.edit_text(text, reply_markup=admin_referrals_kb(links, i18n))
    await callback.answer()


@router.callback_query(F.data == "admin:create_referral")
async def cb_create_referral(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer(i18n("error_permission"))
        return
    await state.set_state(AdminState.referral_name)
    await callback.message.edit_text(i18n("admin_referral_enter_name"))
    await callback.answer()


@router.message(AdminState.referral_name)
async def handle_referral_name(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    if not is_admin(message.from_user.id):
        return
    name = message.text.strip()
    if not name:
        await message.answer(i18n("error_invalid_input"))
        return

    async with async_session_maker() as session:
        link = await create_link(session, name, message.from_user.id)

    await state.clear()
    bot_info = await message.bot.get_me()

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text=i18n("btn_back"), callback_data="admin:referrals")

    await message.answer(
        i18n("admin_referral_created", name=link.name, username=bot_info.username, code=link.code),
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data == "admin:referral_chart")
async def cb_referral_chart(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer(i18n("error_permission"))
        return

    async with async_session_maker() as session:
        links = await get_all_links(session)

    if not links:
        await callback.answer(i18n("admin_no_referrals"), show_alert=True)
        return

    names = [l.name for l in links]
    users = [l.users_count for l in links]
    orders = [l.orders_count for l in links]

    buf = generate_referral_chart(names, users, orders)
    photo = BufferedInputFile(buf.read(), filename="referral_chart.png")
    await callback.message.answer_photo(photo, caption="📊 Referral Performance")
    await callback.answer()


# ── Broadcast ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:broadcast")
async def cb_admin_broadcast_menu(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer(i18n("error_permission"))
        return
    await callback.message.edit_text(i18n("admin_broadcast_title"), reply_markup=admin_broadcast_menu_kb(i18n))
    await callback.answer()


@router.callback_query(F.data == "bcast_new")
async def cb_bcast_new(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer(i18n("error_permission"))
        return
    await callback.message.edit_text(
        i18n("admin_broadcast_select_type"),
        reply_markup=admin_broadcast_type_kb(i18n),
    )
    await callback.answer()


@router.callback_query(F.data == "bcast_history")
async def cb_bcast_history(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer(i18n("error_permission"))
        return

    async with async_session_maker() as session:
        jobs = await get_recent_broadcasts(session, limit=10)

    if not jobs:
        text = i18n("admin_broadcast_history_empty")
    else:
        lines = []
        for j in jobs:
            lines.append(i18n(
                "admin_broadcast_status",
                id=j.id, status=j.status, sent=j.sent_count,
                failed=j.failed_count, total=j.total_users,
            ))
        text = "\n\n".join(lines)

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text=i18n("btn_back"), callback_data="admin:broadcast")
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("bcast_type:"))
async def cb_bcast_select_type(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer(i18n("error_permission"))
        return
    content_type = callback.data.split(":")[1]
    await state.update_data(bcast_type=content_type)

    if content_type == "text":
        await state.set_state(AdminState.broadcast_text)
        await callback.message.edit_text(i18n("admin_broadcast_enter_text"))
    elif content_type == "photo":
        await state.set_state(AdminState.broadcast_photo)
        await callback.message.edit_text(i18n("admin_broadcast_enter_photo"))
    else:
        await state.set_state(AdminState.broadcast_video)
        await callback.message.edit_text(i18n("admin_broadcast_enter_video"))
    await callback.answer()


@router.message(AdminState.broadcast_text)
async def handle_bcast_text(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    if not is_admin(message.from_user.id):
        return
    await state.update_data(bcast_text=message.text or "", bcast_file_id=None)
    await _show_bcast_preview(message, state, i18n)


@router.message(AdminState.broadcast_photo)
async def handle_bcast_photo(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    if not is_admin(message.from_user.id):
        return
    if not message.photo:
        await message.answer(i18n("error_invalid_input"))
        return
    await state.update_data(bcast_text=message.caption or "", bcast_file_id=message.photo[-1].file_id)
    await _show_bcast_preview(message, state, i18n)


@router.message(AdminState.broadcast_video)
async def handle_bcast_video(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    if not is_admin(message.from_user.id):
        return
    if not message.video:
        await message.answer(i18n("error_invalid_input"))
        return
    await state.update_data(bcast_text=message.caption or "", bcast_file_id=message.video.file_id)
    await _show_bcast_preview(message, state, i18n)


async def _show_bcast_preview(message: Message, state: FSMContext, i18n) -> None:
    data = await state.get_data()
    await state.set_state(AdminState.broadcast_confirm)

    async with async_session_maker() as session:
        from services.user_service import get_stats
        stats = await get_stats(session)

    text = i18n(
        "admin_broadcast_confirm",
        type=data.get("bcast_type", "text"),
        count=stats.get("users", 0),
    )
    await message.answer(text, reply_markup=admin_broadcast_confirm_kb(i18n))


@router.callback_query(F.data == "bcast_do_send")
async def cb_bcast_do_send(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer(i18n("error_permission"))
        return

    data = await state.get_data()
    await state.clear()

    async with async_session_maker() as session:
        await create_broadcast(
            session,
            admin_telegram_id=callback.from_user.id,
            content_type=data.get("bcast_type", "text"),
            text=data.get("bcast_text") or None,
            file_id=data.get("bcast_file_id") or None,
        )

    await callback.message.edit_text(i18n("admin_broadcast_queued"))
    await callback.answer()


@router.callback_query(F.data == "bcast_cancel")
async def cb_bcast_cancel(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    await state.clear()
    await callback.message.edit_text(i18n("admin_broadcast_title"), reply_markup=admin_broadcast_menu_kb(i18n))
    await callback.answer()


# ── Moderation ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:moderation")
async def cb_admin_moderation(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer(i18n("error_permission"))
        return
    await callback.message.edit_text(i18n("btn_admin_moderation"), reply_markup=admin_moderation_kb(i18n))
    await callback.answer()


@router.callback_query(F.data == "admin:ban")
async def cb_admin_ban(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer(i18n("error_permission"))
        return
    await callback.message.edit_text(i18n("admin_enter_user_id"))
    await state.set_state(AdminState.ban_user_id)
    await callback.answer()


@router.message(AdminState.ban_user_id)
async def process_ban_user_id(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    if not is_admin(message.from_user.id):
        return
    try:
        user_id = int(message.text.strip())
    except ValueError:
        await message.answer(i18n("error_invalid_input"))
        return
    await state.update_data(ban_target_id=user_id)
    await message.answer(i18n("admin_enter_ban_reason"))
    await state.set_state(AdminState.ban_reason)


@router.message(AdminState.ban_reason)
async def process_ban_reason(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    reason = message.text.strip()
    data = await state.get_data()
    user_id = data["ban_target_id"]
    await state.clear()

    async with async_session_maker() as session:
        user = await get_user_by_id(session, user_id)
        if not user:
            await message.answer(i18n("admin_user_not_found"))
            return
        await ban_user(session, user, reason)

    await message.answer(i18n("admin_user_banned", user_id=user_id, reason=reason))


@router.callback_query(F.data == "admin:unban")
async def cb_admin_unban(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer(i18n("error_permission"))
        return
    await callback.message.edit_text(i18n("admin_enter_user_id"))
    await state.set_state(AdminState.unban_user_id)
    await callback.answer()


@router.message(AdminState.unban_user_id)
async def process_unban(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    if not is_admin(message.from_user.id):
        return
    try:
        user_id = int(message.text.strip())
    except ValueError:
        await message.answer(i18n("error_invalid_input"))
        return
    await state.clear()

    async with async_session_maker() as session:
        user = await get_user_by_id(session, user_id)
        if not user:
            await message.answer(i18n("admin_user_not_found"))
            return
        await unban_user(session, user)

    await message.answer(i18n("admin_user_unbanned", user_id=user_id))


# ── Database management ────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:db")
async def cb_admin_db(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer(i18n("error_permission"))
        return
    await callback.message.edit_text(i18n("admin_db_title"), reply_markup=admin_db_kb(i18n))
    await callback.answer()


@router.callback_query(F.data == "admin:db_export")
async def cb_db_export(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer(i18n("error_permission"))
        return

    db_url = settings.DATABASE_URL
    if "sqlite" not in db_url:
        await callback.message.edit_text(i18n("admin_db_not_sqlite"), reply_markup=admin_db_kb(i18n))
        await callback.answer()
        return

    db_path = db_url.replace("sqlite+aiosqlite:///", "")
    if not os.path.exists(db_path):
        await callback.answer("Database file not found", show_alert=True)
        return

    document = FSInputFile(db_path, filename="freelance_bot_backup.db")
    await callback.message.answer_document(document, caption="📥 Database backup")
    await callback.answer()


@router.callback_query(F.data == "admin:db_import")
async def cb_db_import(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer(i18n("error_permission"))
        return
    await state.set_state(AdminState.db_import_file)
    await callback.message.edit_text(i18n("admin_db_send_file"))
    await callback.answer()


@router.message(AdminState.db_import_file)
async def handle_db_import(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    if not is_admin(message.from_user.id):
        return
    if not message.document or not message.document.file_name.endswith(".db"):
        await message.answer(i18n("admin_db_import_error"))
        return

    db_url = settings.DATABASE_URL
    if "sqlite" not in db_url:
        await message.answer(i18n("admin_db_not_sqlite"))
        await state.clear()
        return

    db_path = db_url.replace("sqlite+aiosqlite:///", "")

    try:
        tg_file = await message.bot.get_file(message.document.file_id)
        file_bytes = await message.bot.download_file(tg_file.file_path)

        header = file_bytes.read(16)
        if not header.startswith(b"SQLite format 3"):
            await message.answer(i18n("admin_db_import_error"))
            await state.clear()
            return

        file_bytes.seek(0)
        with open(db_path, "wb") as f:
            f.write(file_bytes.read())

        await state.clear()
        await message.answer(i18n("admin_db_imported"))
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as exc:
        logger.error(f"DB import failed: {exc}")
        await message.answer(i18n("admin_db_import_error"))
        await state.clear()


# ── Disputes ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:disputes")
async def cb_admin_disputes(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer(i18n("error_permission"))
        return

    async with async_session_maker() as session:
        disputes = await get_open_disputes(session)

    if not disputes:
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()
        builder.button(text=i18n("btn_back"), callback_data="admin_back")
        await callback.message.edit_text(i18n("admin_disputes_list", count=0), reply_markup=builder.as_markup())
        await callback.answer()
        return

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    for d in disputes:
        label = f"⚠️ Deal #{d.id} — {d.job.title[:30]}"
        builder.button(text=label, callback_data=f"admin_dispute:{d.id}")
    builder.button(text=i18n("btn_back"), callback_data="admin_back")
    builder.adjust(1)

    await callback.message.edit_text(
        i18n("admin_disputes_list", count=len(disputes)),
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_dispute:"))
async def cb_admin_dispute_detail(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    deal_id = int(callback.data.split(":")[1])
    async with async_session_maker() as session:
        from services.escrow_service import get_deal
        deal = await get_deal(session, deal_id)

    if not deal:
        await callback.answer(i18n("error_not_found"))
        return

    text = i18n(
        "admin_dispute_details",
        deal_id=deal.id,
        title=deal.job.title,
        employer=deal.employer.full_name,
        freelancer=deal.freelancer.full_name,
        amount=deal.amount,
        reason=deal.dispute_reason or "—",
    )
    await callback.message.edit_text(text, reply_markup=admin_dispute_kb(deal_id, i18n))
    await callback.answer()


@router.callback_query(F.data.startswith("resolve:employer:"))
async def cb_resolve_employer(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer(i18n("error_permission"))
        return
    deal_id = int(callback.data.split(":")[2])
    employer_tg = None
    async with async_session_maker() as session:
        from services.escrow_service import get_deal
        deal = await get_deal(session, deal_id)
        if deal:
            await resolve_dispute_to_employer(session, deal, admin_tg_id=callback.from_user.id)
            employer_tg = deal.employer.telegram_id

    if employer_tg:
        await notify(callback.bot, employer_tg, i18n("dispute_resolved_employer"))
    await callback.message.edit_text(i18n("admin_dispute_resolved", action=i18n("dispute_action_refund")))
    await callback.answer()


@router.callback_query(F.data.startswith("resolve:freelancer:"))
async def cb_resolve_freelancer(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer(i18n("error_permission"))
        return
    deal_id = int(callback.data.split(":")[2])
    freelancer_tg = None
    async with async_session_maker() as session:
        from services.escrow_service import get_deal
        deal = await get_deal(session, deal_id)
        if deal:
            await resolve_dispute_to_freelancer(session, deal, admin_tg_id=callback.from_user.id)
            freelancer_tg = deal.freelancer.telegram_id

    if freelancer_tg:
        await notify(callback.bot, freelancer_tg, i18n("dispute_resolved_freelancer"))
    await callback.message.edit_text(i18n("admin_dispute_resolved", action=i18n("dispute_action_paid")))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_dispute_chat:"))
async def cb_admin_dispute_chat(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer(i18n("error_permission"))
        return

    deal_id = int(callback.data.split(":")[1])

    from sqlalchemy import and_, or_, select
    from database.models import Message as Msg
    from services.escrow_service import get_deal

    async with async_session_maker() as session:
        deal = await get_deal(session, deal_id)
        if not deal:
            await callback.answer(i18n("error_not_found"))
            return

        emp_id = deal.employer_id
        fl_id = deal.freelancer_id
        job_id = deal.job_id
        emp_name = deal.employer.full_name
        fl_name = deal.freelancer.full_name

        result = await session.execute(
            select(Msg)
            .where(
                Msg.job_id == job_id,
                or_(
                    and_(Msg.sender_id == emp_id, Msg.receiver_id == fl_id),
                    and_(Msg.sender_id == fl_id, Msg.receiver_id == emp_id),
                ),
            )
            .order_by(Msg.created_at.asc())
            .limit(20)
        )
        messages = list(result.scalars().all())

    if not messages:
        text = i18n("admin_dispute_chat_header", deal_id=deal_id) + i18n("admin_no_messages")
    else:
        lines = [i18n("admin_dispute_chat_header", deal_id=deal_id)]
        for msg in messages:
            sender = emp_name if msg.sender_id == emp_id else fl_name
            time_str = msg.created_at.strftime("%d.%m %H:%M") if msg.created_at else ""
            content = msg.text[:120] if msg.text else f"[{msg.message_type}]"
            lines.append(f"<b>{sender}</b> <i>{time_str}</i>\n{content}")
        text = "\n\n".join(lines)

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text=i18n("btn_back"), callback_data=f"admin_dispute:{deal_id}")
    await callback.message.edit_text(text[:4000], parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()


# ── Settings ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:settings")
async def cb_admin_settings(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer(i18n("error_permission"))
        return

    async with async_session_maker() as session:
        result = await session.execute(
            sa_select(BotSettings).where(BotSettings.key == "service_promo_price")
        )
        row = result.scalar_one_or_none()
    price = float(row.value) if row else 5.0

    await callback.message.edit_text(
        i18n("admin_settings_panel", service_promo_price=price),
        reply_markup=admin_settings_kb(i18n),
    )
    await callback.answer()


@router.callback_query(F.data == "admin:set_service_promo_price")
async def cb_set_service_promo_price(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer(i18n("error_permission"))
        return
    await state.set_state(AdminState.service_promo_price)
    await callback.message.edit_text(i18n("admin_enter_service_promo_price"))
    await callback.answer()


@router.message(AdminState.service_promo_price)
async def handle_set_service_promo_price(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    if not is_admin(message.from_user.id):
        return
    from utils.helpers import safe_float
    price = safe_float(message.text)
    if price is None or price <= 0:
        await message.answer(i18n("invalid_amount"))
        return

    async with async_session_maker() as session:
        result = await session.execute(
            sa_select(BotSettings).where(BotSettings.key == "service_promo_price")
        )
        row = result.scalar_one_or_none()
        if row:
            row.value = str(price)
        else:
            session.add(BotSettings(key="service_promo_price", value=str(price)))
        await session.commit()

    await state.clear()
    await message.answer(i18n("admin_service_promo_price_set", price=price))


# ── Verify user ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:verify_user")
async def cb_admin_verify_user(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer(i18n("error_permission"))
        return
    await state.set_state(AdminState.verify_user_id)
    await callback.message.edit_text(i18n("admin_enter_verify_id"))
    await callback.answer()


@router.message(AdminState.verify_user_id)
async def handle_verify_user(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    if not is_admin(message.from_user.id):
        return
    text = (message.text or "").strip()
    try:
        tg_id = int(text)
    except ValueError:
        await message.answer(i18n("error_invalid_input"))
        return

    await state.clear()
    from services.user_service import get_user_by_telegram_id
    async with async_session_maker() as session:
        target = await get_user_by_telegram_id(session, tg_id)
        if not target:
            await message.answer(i18n("error_not_found"))
            return
        target.is_verified = not bool(getattr(target, "is_verified", False))
        new_status = target.is_verified
        await session.commit()

    if new_status:
        await message.answer(i18n("user_verified", name=target.full_name))
    else:
        await message.answer(i18n("user_unverified", name=target.full_name))


@router.callback_query(F.data.startswith("resolve:split:"))
async def cb_resolve_split(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer(i18n("error_permission"))
        return
    deal_id = int(callback.data.split(":")[2])
    employer_tg = freelancer_tg = None
    async with async_session_maker() as session:
        from services.escrow_service import get_deal
        deal = await get_deal(session, deal_id)
        if deal:
            await resolve_dispute_split(session, deal, admin_tg_id=callback.from_user.id)
            employer_tg = deal.employer.telegram_id
            freelancer_tg = deal.freelancer.telegram_id

    if employer_tg:
        await notify(callback.bot, employer_tg, "⚖️ Dispute resolved: 50% refunded to you.")
    if freelancer_tg:
        await notify(callback.bot, freelancer_tg, "⚖️ Dispute resolved: 50% payment released to you.")
    await callback.message.edit_text(i18n("dispute_split_done"))
    await callback.answer()
