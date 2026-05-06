from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from database.connection import async_session_maker
from database.models import User
from services.chat_service import (
    get_conversation,
    get_conversations_list,
    mark_read,
    send_message,
)
from services.notification_service import notify_new_message
from services.user_service import get_user_by_id, get_user_by_telegram_id
from states import ChatState
from utils.helpers import btn
from utils.keyboards import REMOVE, chats_list_kb, exit_chat_kb, main_menu, view_portfolio_kb

router = Router()


@router.message(btn("btn_chats"))
async def handle_chats_menu(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    if not db_user:
        return
    await show_chats_list(message, i18n, db_user)


async def show_chats_list(target, i18n, db_user: User) -> None:
    async with async_session_maker() as session:
        convs = await get_conversations_list(session, db_user.id)

    if not convs:
        text = i18n("no_chats")
        if isinstance(target, Message):
            await target.answer(text)
        else:
            await target.message.edit_text(text)
        return

    text = i18n("chats")
    kb = chats_list_kb(convs, i18n)
    if isinstance(target, Message):
        await target.answer(text, reply_markup=kb)
    else:
        await target.message.edit_text(text, reply_markup=kb)


# ── Shared chat-opening helper ─────────────────────────────────────────────

async def _open_chat_for(
    callback: CallbackQuery,
    state: FSMContext,
    i18n,
    db_user: User,
    other_user_id: int,
    job_id: int,
) -> None:
    """Open a chat session with other_user_id, updating FSM and rendering history."""
    async with async_session_maker() as session:
        other = await get_user_by_id(session, other_user_id)
        if not other:
            await callback.answer(i18n("error_not_found"))
            return

        messages = await get_conversation(session, db_user.id, other_user_id, job_id or None)
        await mark_read(session, db_user.id, other_user_id)

    await state.update_data(chat_with_id=other_user_id, chat_job_id=job_id)
    await state.set_state(ChatState.messaging)

    if not messages:
        conv_text = i18n("chat_history_empty")
    else:
        lines = []
        for msg in messages[-15:]:
            who = "You" if msg.sender_id == db_user.id else other.full_name
            mtype = getattr(msg, "message_type", "text") or "text"
            if mtype == "text":
                lines.append(f"<b>{who}:</b> {msg.text or ''}")
            elif mtype == "photo":
                lines.append(f"<b>{who}:</b> 🖼 {i18n('photo_received')}" + (f" — {msg.text}" if msg.text else ""))
            elif mtype == "video":
                lines.append(f"<b>{who}:</b> 🎬 {i18n('video_received')}" + (f" — {msg.text}" if msg.text else ""))
            elif mtype == "document":
                fname = getattr(msg, "filename", None) or i18n("document_received")
                lines.append(f"<b>{who}:</b> 📎 {fname}")
        conv_text = "\n\n".join(lines)

    rating_str = f"{other.rating:.1f}" if other.rating_count else "—"
    user_info = f"⭐ {rating_str} ({other.rating_count}) · ✅ {other.completed_orders}"
    header = f"{i18n('chat_opened', name=other.full_name)}\n{user_info}"
    text = f"{header}\n\n{conv_text}"

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    if getattr(other, "portfolio_photos", None):
        builder.button(text=i18n("btn_view_portfolio"), callback_data=f"view_portfolio:{other.id}")
    builder.button(text=i18n("btn_back"), callback_data="back_to_chats")
    builder.adjust(1)

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.message.answer(i18n("chat_send_hint"), reply_markup=exit_chat_kb(i18n))
    await callback.answer()


# ── Open chat by user+job IDs ──────────────────────────────────────────────

@router.callback_query(F.data.startswith("open_chat:"))
async def cb_open_chat(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    if not db_user:
        return
    parts = callback.data.split(":")
    other_user_id = int(parts[1])
    job_id = int(parts[2]) if len(parts) > 2 else 0
    await _open_chat_for(callback, state, i18n, db_user, other_user_id, job_id)


# ── Exit chat — must be registered BEFORE generic messaging handler ────────

@router.message(ChatState.messaging, btn("chat_exit"))
async def handle_chat_exit(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    await state.clear()
    if not db_user:
        return
    await message.answer(i18n("main_menu"), reply_markup=main_menu(None, i18n))
    await show_chats_list(message, i18n, db_user)


# ── Send a chat message (text or file) ────────────────────────────────────

@router.message(ChatState.messaging)
async def handle_chat_message(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    if not db_user:
        return

    data = await state.get_data()
    other_id = data.get("chat_with_id")
    job_id = data.get("chat_job_id") or None

    if not other_id:
        await state.clear()
        return

    msg_type = "text"
    file_id = None
    filename = None
    text_content = message.text or message.caption or ""

    if message.photo:
        msg_type = "photo"
        file_id = message.photo[-1].file_id
    elif message.video:
        msg_type = "video"
        file_id = message.video.file_id
    elif message.document:
        msg_type = "document"
        file_id = message.document.file_id
        filename = message.document.file_name

    if msg_type == "text" and not text_content:
        return

    async with async_session_maker() as session:
        sender = await get_user_by_telegram_id(session, message.from_user.id)
        receiver = await get_user_by_id(session, other_id)
        if not receiver:
            await message.answer(i18n("error_not_found"))
            return

        if receiver.is_banned:
            await message.answer(i18n("chat_user_banned"))
            return

        await send_message(
            session, sender, receiver,
            text=text_content or None,
            job_id=job_id,
            message_type=msg_type,
            file_id=file_id,
            filename=filename,
        )
        receiver_tg = receiver.telegram_id
        sender_name = sender.full_name
        notif_enabled = bool(getattr(receiver, "notifications_enabled", True))

    try:
        if msg_type == "photo" and file_id:
            await message.bot.send_photo(receiver_tg, file_id, caption=text_content or None)
        elif msg_type == "video" and file_id:
            await message.bot.send_video(receiver_tg, file_id, caption=text_content or None)
        elif msg_type == "document" and file_id:
            await message.bot.send_document(receiver_tg, file_id, caption=text_content or None)
        else:
            from utils.keyboards import chat_reply_kb
            await message.bot.send_message(
                receiver_tg,
                f"<b>{sender_name}:</b> {text_content}",
                parse_mode="HTML",
                reply_markup=chat_reply_kb(db_user.id, job_id or 0, i18n),
            )
    except Exception:
        pass

    await message.answer(i18n("message_sent"))


@router.callback_query(F.data == "back_to_chats")
async def cb_back_to_chats(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    await state.clear()
    if db_user:
        await callback.message.answer(i18n("main_menu"), reply_markup=main_menu(None, i18n))
    await show_chats_list(callback, i18n, db_user)
    await callback.answer()


# ── Open chat from application (employer → freelancer) ─────────────────────

@router.callback_query(F.data.startswith("chat_from_app:"))
async def cb_chat_from_app(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    if not db_user:
        return
    app_id = int(callback.data.split(":")[1])
    async with async_session_maker() as session:
        from services.application_service import get_application
        app = await get_application(session, app_id)
        if not app:
            await callback.answer(i18n("error_not_found"))
            return
        other_id = app.freelancer_id
        job_id = app.job_id

    await _open_chat_for(callback, state, i18n, db_user, other_id, job_id)


# ── Direct chat from job listing (freelancer → employer) ───────────────────

@router.callback_query(F.data.startswith("direct_chat:"))
async def cb_direct_chat(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    if not db_user:
        return
    parts = callback.data.split(":")
    employer_db_id = int(parts[1])
    job_id = int(parts[2]) if len(parts) > 2 else 0
    await _open_chat_for(callback, state, i18n, db_user, employer_db_id, job_id)
