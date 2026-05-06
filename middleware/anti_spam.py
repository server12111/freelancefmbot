import time
from collections import defaultdict
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from config import settings


class AntiSpamMiddleware(BaseMiddleware):
    """Simple in-memory rate limiter. Replace with Redis for multi-process."""

    def __init__(self):
        self._user_timestamps: dict[int, list[float]] = defaultdict(list)
        self._max = settings.ANTI_SPAM_MAX_MESSAGES
        self._window = settings.ANTI_SPAM_WINDOW_SECONDS

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)

        user_id = event.from_user.id if event.from_user else None
        if not user_id:
            return await handler(event, data)

        now = time.time()
        timestamps = self._user_timestamps[user_id]
        # Drop timestamps outside the window
        self._user_timestamps[user_id] = [t for t in timestamps if now - t < self._window]
        self._user_timestamps[user_id].append(now)

        if len(self._user_timestamps[user_id]) > self._max:
            await event.answer("⚠️ Too many requests. Please slow down.")
            return

        return await handler(event, data)
