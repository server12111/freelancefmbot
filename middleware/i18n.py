from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from database.connection import async_session_maker
from database.models import User
from localization import get_i18n
from sqlalchemy import select


class I18nMiddleware(BaseMiddleware):
    """Injects i18n and db_user into handler data."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_tg = data.get("event_from_user")
        lang = "en"
        db_user = None

        if user_tg:
            async with async_session_maker() as session:
                result = await session.execute(
                    select(User).where(User.telegram_id == user_tg.id)
                )
                db_user = result.scalar_one_or_none()
                if db_user:
                    lang = db_user.language.value

        data["i18n"] = get_i18n(lang)
        data["db_user"] = db_user
        return await handler(event, data)
