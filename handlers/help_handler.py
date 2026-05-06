from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.models import User
from utils.keyboards import back_kb, help_kb

router = Router()

# ── Telegraph URLs per language ────────────────────────────────────────────

from utils.telegraph_links import FAQ_URLS as _FAQ_URLS, PRIVACY_URLS as _PRIVACY_URLS


def _docs_lang_kb(i18n) -> "InlineKeyboardMarkup":
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🇺🇦 Українська", callback_data="help:docs:uk"),
        InlineKeyboardButton(text="🇷🇺 Русский",    callback_data="help:docs:ru"),
        InlineKeyboardButton(text="🇬🇧 English",    callback_data="help:docs:en"),
    )
    builder.row(InlineKeyboardButton(text=i18n("btn_back"), callback_data="help_main"))
    return builder.as_markup()


def _docs_links_kb(lang: str, i18n) -> "InlineKeyboardMarkup":
    labels = {
        "uk": ("❓ FAQ", "🔒 Політика конфіденційності"),
        "ru": ("❓ FAQ", "🔒 Политика конфиденциальности"),
        "en": ("❓ FAQ", "🔒 Privacy Policy"),
    }
    faq_label, privacy_label = labels.get(lang, labels["en"])
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=faq_label,     url=_FAQ_URLS[lang]),
        InlineKeyboardButton(text=privacy_label, url=_PRIVACY_URLS[lang]),
    )
    builder.row(InlineKeyboardButton(text=i18n("btn_back"), callback_data="help:docs"))
    return builder.as_markup()


# ── Help topics ────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("help:"))
async def cb_help_topic(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    parts = callback.data.split(":")
    topic = parts[1]

    # Documents language selector
    if topic == "docs":
        if len(parts) == 3:
            lang = parts[2]
            if lang not in _FAQ_URLS:
                await callback.answer()
                return
            lang_names = {"uk": "🇺🇦 Українська", "ru": "🇷🇺 Русский", "en": "🇬🇧 English"}
            await callback.message.edit_text(
                f"📄 {lang_names[lang]}",
                reply_markup=_docs_links_kb(lang, i18n),
            )
        else:
            await callback.message.edit_text(
                i18n("help_docs_choose_lang"),
                reply_markup=_docs_lang_kb(i18n),
            )
        await callback.answer()
        return

    # Regular help topics
    key_map = {
        "jobs":     "help_jobs",
        "payments": "help_payments",
        "escrow":   "help_escrow",
    }
    key = key_map.get(topic)
    if not key:
        await callback.answer()
        return

    await callback.message.edit_text(
        i18n(key),
        reply_markup=back_kb(i18n, "help_main"),
    )
    await callback.answer()


@router.callback_query(F.data == "help_main")
async def cb_help_main(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    await callback.message.edit_text(
        i18n("help_main"),
        reply_markup=help_kb(i18n),
    )
    await callback.answer()
