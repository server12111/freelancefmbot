from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from loguru import logger


class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        event_type = type(event).__name__

        if user:
            logger.info(f"[{event_type}] user={user.id} (@{user.username})")
        else:
            logger.info(f"[{event_type}]")

        try:
            result = await handler(event, data)
            return result
        except Exception as exc:
            logger.exception(f"Unhandled error in {event_type}: {exc}")
            raise
