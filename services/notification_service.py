from datetime import datetime, timezone

from aiogram import Bot
from loguru import logger

# Simple in-memory debounce: {(user_id, event_key): last_sent_ts}
_debounce: dict[tuple, float] = {}
DEBOUNCE_SECONDS = 60


def _should_send(user_id: int, event_key: str) -> bool:
    key = (user_id, event_key)
    now = datetime.now(timezone.utc).timestamp()
    last = _debounce.get(key, 0)
    if now - last >= DEBOUNCE_SECONDS:
        _debounce[key] = now
        return True
    return False


async def notify(bot: Bot, telegram_id: int, text: str, notifications_enabled: bool = True, **kwargs) -> None:
    if not notifications_enabled:
        return
    try:
        await bot.send_message(chat_id=telegram_id, text=text, **kwargs)
    except Exception as exc:
        logger.warning(f"Failed to notify user {telegram_id}: {exc}")


async def notify_application_accepted(
    bot: Bot, freelancer_tg_id: int, job_title: str, i18n,
    notifications_enabled: bool = True,
) -> None:
    if not _should_send(freelancer_tg_id, "app_accepted"):
        return
    await notify(
        bot, freelancer_tg_id,
        i18n("application_accepted_freelancer", title=job_title),
        notifications_enabled=notifications_enabled,
    )


async def notify_application_rejected(
    bot: Bot, freelancer_tg_id: int, job_title: str, i18n,
    notifications_enabled: bool = True,
) -> None:
    if not _should_send(freelancer_tg_id, "app_rejected"):
        return
    await notify(
        bot, freelancer_tg_id,
        i18n("application_rejected_freelancer", title=job_title),
        notifications_enabled=notifications_enabled,
    )


async def notify_work_submitted(
    bot: Bot,
    employer_tg_id: int,
    freelancer_name: str,
    job_title: str,
    description: str,
    deal_id: int,
    i18n,
    notifications_enabled: bool = True,
) -> None:
    from utils.keyboards import deal_employer_confirm_kb
    await notify(
        bot,
        employer_tg_id,
        i18n("work_submitted_employer", freelancer=freelancer_name, title=job_title, description=description),
        notifications_enabled=notifications_enabled,
        reply_markup=deal_employer_confirm_kb(deal_id, i18n),
    )


async def notify_payment_released(
    bot: Bot, freelancer_tg_id: int, amount, deal_id: int, i18n,
    notifications_enabled: bool = True,
    currency: str = "usd",
) -> None:
    from utils.keyboards import rating_kb
    key = "payment_released_freelancer_ton" if currency == "ton" else "payment_released_freelancer"
    await notify(
        bot,
        freelancer_tg_id,
        i18n(key, amount=amount),
        notifications_enabled=notifications_enabled,
        reply_markup=rating_kb(i18n, deal_id),
    )


async def notify_new_message(
    bot: Bot,
    receiver_tg_id: int,
    sender_name: str,
    text: str,
    sender_id: int,
    job_id: int,
    i18n,
    notifications_enabled: bool = True,
) -> None:
    if not _should_send(receiver_tg_id, f"msg_{sender_id}"):
        return
    from utils.keyboards import chat_reply_kb
    preview = text[:80] + ("…" if len(text) > 80 else "") if text else "📎 File"
    await notify(
        bot,
        receiver_tg_id,
        i18n("new_message", name=sender_name, text=preview),
        notifications_enabled=notifications_enabled,
        reply_markup=chat_reply_kb(sender_id, job_id, i18n),
    )


async def notify_new_application(
    bot: Bot,
    employer_tg_id: int,
    freelancer_name: str,
    job_title: str,
    i18n,
    notifications_enabled: bool = True,
) -> None:
    await notify(
        bot, employer_tg_id,
        i18n("new_application_employer", freelancer=freelancer_name, title=job_title),
        notifications_enabled=notifications_enabled,
    )


async def notify_auto_released(
    bot: Bot, freelancer_tg_id: int, amount, i18n,
    notifications_enabled: bool = True,
    currency: str = "usd",
) -> None:
    key = "auto_release_done_ton" if currency == "ton" else "auto_release_done"
    await notify(
        bot, freelancer_tg_id,
        i18n(key, amount=amount),
        notifications_enabled=notifications_enabled,
    )


async def notify_invitation(
    bot: Bot,
    freelancer_tg_id: int,
    inv_id: int,
    employer_name: str,
    job_title: str,
    budget: float,
    message: str | None,
    i18n,
    notifications_enabled: bool = True,
) -> None:
    from utils.keyboards import invitation_kb
    text = i18n(
        "invitation_received",
        title=job_title,
        employer=employer_name,
        budget=budget,
        message=message or "—",
    )
    await notify(
        bot, freelancer_tg_id, text,
        notifications_enabled=notifications_enabled,
        reply_markup=invitation_kb(inv_id, i18n),
    )


async def notify_dispute_opened(
    bot: Bot,
    opener_name: str,
    job_title: str,
    reason: str,
    deal_id: int,
    evidence_file_id: str | None = None,
    evidence_type: str | None = None,
) -> None:
    from config import settings
    text = (
        f"⚠️ <b>Новий спір!</b>\n\n"
        f"📌 Замовлення: <b>{job_title}</b>\n"
        f"👤 Ініціатор: {opener_name}\n"
        f"🆔 Deal #{deal_id}\n\n"
        f"📝 Причина:\n{reason}"
    )
    caption = f"📎 Доказ по спору Deal #{deal_id}"
    for admin_id in settings.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, parse_mode="HTML")
            if evidence_file_id:
                if evidence_type == "photo":
                    await bot.send_photo(admin_id, evidence_file_id, caption=caption)
                elif evidence_type == "video":
                    await bot.send_video(admin_id, evidence_file_id, caption=caption)
                elif evidence_type == "document":
                    await bot.send_document(admin_id, evidence_file_id, caption=caption)
        except Exception as e:
            logger.warning(f"Admin dispute notify failed {admin_id}: {e}")


async def broadcast(bot: Bot, users: list, text: str) -> int:
    sent = 0
    for user in users:
        try:
            await bot.send_message(chat_id=user.telegram_id, text=text, parse_mode="HTML")
            sent += 1
        except Exception as exc:
            logger.warning(f"Broadcast failed for {user.telegram_id}: {exc}")
    return sent
