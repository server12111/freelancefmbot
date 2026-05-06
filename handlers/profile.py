from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InputMediaPhoto, Message

from database.connection import async_session_maker
from database.models import PortfolioPhoto, User
from services.user_service import get_user_by_telegram_id, update_name
from states import PortfolioState, ProfileEditState
from utils.helpers import btn, format_date, format_rating
from utils.keyboards import (
    confirm_cancel_kb,
    main_menu,
    portfolio_manage_kb,
    profile_extended_kb,
)

router = Router()


async def show_profile(target, i18n, db_user: User) -> None:
    username = f"@{db_user.username}" if db_user.username else "—"
    notif_enabled = bool(getattr(db_user, "notifications_enabled", True))
    rating = format_rating(db_user.rating, db_user.rating_count)
    verified = " ✅" if getattr(db_user, "is_verified", False) else ""
    ton_bal = getattr(db_user, "balance_ton", 0.0)

    text = (
        f"{i18n('profile_header')}\n\n"
        f"👤 <b>{db_user.full_name}</b>{verified}  ·  {username}\n"
        f"⭐ {rating} ({db_user.rating_count})\n"
        f"💵 ${db_user.balance:.2f}  ·  ◎ {ton_bal:.4f} TON\n"
        f"📅 {format_date(db_user.created_at)}"
    )
    kb = profile_extended_kb(i18n, notifications_enabled=notif_enabled)
    if isinstance(target, Message):
        await target.answer(text, reply_markup=kb)
    else:
        await target.message.edit_text(text, reply_markup=kb)


@router.message(btn("btn_profile"))
async def msg_profile(message: Message, i18n, db_user: User | None) -> None:
    if not db_user:
        await message.answer(i18n("error_not_registered"))
        return
    async with async_session_maker() as session:
        user = await get_user_by_telegram_id(session, message.from_user.id)
    await show_profile(message, i18n, user)


# ── Edit name ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "edit_name")
async def cb_edit_name(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    if not db_user:
        await callback.answer(i18n("error_not_registered"))
        return
    await callback.message.edit_text(i18n("enter_new_name"))
    await state.set_state(ProfileEditState.name)
    await callback.answer()


@router.message(ProfileEditState.name)
async def process_new_name(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    if not db_user:
        return
    name = message.text.strip() if message.text else ""
    if not name or len(name) > 100:
        await message.answer(i18n("error_invalid_input"))
        return

    async with async_session_maker() as session:
        user = await get_user_by_telegram_id(session, message.from_user.id)
        await update_name(session, user, name)

    await state.clear()
    await message.answer(i18n("name_updated", name=name), reply_markup=main_menu(None, i18n))


# ── Notifications toggle ───────────────────────────────────────────────────

@router.callback_query(F.data == "toggle_notifications")
async def cb_toggle_notifications(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    if not db_user:
        return
    async with async_session_maker() as session:
        user = await get_user_by_telegram_id(session, callback.from_user.id)
        user.notifications_enabled = not bool(getattr(user, "notifications_enabled", True))
        await session.commit()
        enabled = bool(user.notifications_enabled)

    key = "notifications_enabled" if enabled else "notifications_disabled"
    await callback.answer(i18n(key), show_alert=True)
    async with async_session_maker() as session:
        user = await get_user_by_telegram_id(session, callback.from_user.id)
    await show_profile(callback, i18n, user)


# ── Portfolio ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "portfolio_manage")
async def cb_portfolio_manage(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    if not db_user:
        return
    async with async_session_maker() as session:
        user = await get_user_by_telegram_id(session, callback.from_user.id)
        count = len(user.portfolio_photos)
    await callback.message.edit_text(
        i18n("portfolio_manage", count=count),
        reply_markup=portfolio_manage_kb(i18n, count),
    )
    await callback.answer()


@router.callback_query(F.data == "portfolio_back")
async def cb_portfolio_back(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    if not db_user:
        return
    async with async_session_maker() as session:
        user = await get_user_by_telegram_id(session, callback.from_user.id)
    await show_profile(callback, i18n, user)
    await callback.answer()


@router.callback_query(F.data == "portfolio_add")
async def cb_portfolio_add(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    if not db_user:
        return
    await callback.message.edit_text(i18n("portfolio_add_prompt"))
    await state.set_state(PortfolioState.adding)
    await callback.answer()


@router.message(PortfolioState.adding)
async def process_portfolio_photo(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    if not db_user:
        return
    if not message.photo:
        await message.answer(i18n("error_invalid_input"))
        return
    async with async_session_maker() as session:
        user = await get_user_by_telegram_id(session, message.from_user.id)
        if len(user.portfolio_photos) >= 5:
            await state.clear()
            await message.answer(i18n("portfolio_limit"))
            return
        photo = PortfolioPhoto(user_id=user.id, file_id=message.photo[-1].file_id)
        session.add(photo)
        await session.commit()
        count = len(user.portfolio_photos) + 1
    await state.clear()
    await message.answer(i18n("portfolio_added", count=count))


@router.callback_query(F.data == "portfolio_del_last")
async def cb_portfolio_del_last(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    if not db_user:
        return
    async with async_session_maker() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(PortfolioPhoto)
            .where(PortfolioPhoto.user_id == db_user.id)
            .order_by(PortfolioPhoto.created_at.desc())
            .limit(1)
        )
        photo = result.scalar_one_or_none()
        if photo:
            session.delete(photo)
            await session.commit()
    await callback.answer(i18n("portfolio_deleted"), show_alert=True)
    async with async_session_maker() as session:
        user = await get_user_by_telegram_id(session, callback.from_user.id)
        count = len(user.portfolio_photos)
    await callback.message.edit_text(
        i18n("portfolio_manage", count=count),
        reply_markup=portfolio_manage_kb(i18n, count),
    )


@router.callback_query(F.data.startswith("view_portfolio:"))
async def cb_view_portfolio(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    user_id = int(callback.data.split(":")[1])
    async with async_session_maker() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(PortfolioPhoto).where(PortfolioPhoto.user_id == user_id)
        )
        photos = result.scalars().all()
    if not photos:
        await callback.answer(i18n("portfolio_empty"), show_alert=True)
        return
    media = [InputMediaPhoto(media=p.file_id) for p in photos]
    await callback.message.answer_media_group(media)
    await callback.answer()
