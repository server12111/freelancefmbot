from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from database.connection import async_session_maker
from database.models import User
from localization import get_i18n
from services.user_service import get_or_create_user, set_language
from utils.keyboards import (
    REMOVE,
    lang_keyboard,
    main_menu,
    welcome_docs_kb,
)

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext, db_user: User | None) -> None:
    await state.clear()

    # Extract referral code from /start ref_CODE deep link
    args = message.text.split()
    ref_code = None
    if len(args) > 1 and args[1].startswith("ref_"):
        ref_code = args[1][4:]

    async with async_session_maker() as session:
        user, is_new = await get_or_create_user(
            session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
        )

        # Attribute referral only for genuinely new users
        if is_new and ref_code:
            from referrals.service import attribute_user, get_by_code
            link = await get_by_code(session, ref_code)
            if link:
                await attribute_user(session, user, link)

    i18n = get_i18n(user.language.value if user.language else "en")

    if is_new or not user.language:
        await message.answer(i18n("welcome"), reply_markup=lang_keyboard())
        return

    await message.answer(i18n("main_menu"), reply_markup=main_menu(None, i18n))


# ── Language selection ─────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("lang:"))
async def cb_select_language(callback: CallbackQuery, state: FSMContext) -> None:
    lang = callback.data.split(":")[1]
    i18n = get_i18n(lang)

    async with async_session_maker() as session:
        user, _ = await get_or_create_user(
            session,
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            full_name=callback.from_user.full_name,
        )
        await set_language(session, user, lang)

    await callback.message.edit_text(i18n("language_set"))
    await callback.message.answer(i18n("welcome_docs_text"), reply_markup=welcome_docs_kb(lang, i18n))
    await callback.message.answer(i18n("main_menu"), reply_markup=main_menu(None, i18n))
    await callback.answer()


# ── /help command ──────────────────────────────────────────────────────────

@router.message(Command("help"))
async def cmd_help(message: Message, i18n, db_user: User | None) -> None:
    from utils.keyboards import help_kb
    await message.answer(i18n("help_main"), reply_markup=help_kb(i18n))
