from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

MENU_KEYS = [
    "btn_find_jobs", "btn_create_job", "btn_my_jobs", "btn_my_applications",
    "btn_browse_services", "btn_my_services", "btn_chats", "btn_reviews",
    "btn_profile", "btn_balance", "chat_exit",
]


class CancelStateOnMenuMiddleware(BaseMiddleware):
    """Clears FSM state when user presses a main menu button during input."""

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        state: FSMContext | None = data.get("state")
        i18n = data.get("i18n")
        if state and i18n and event.text:
            current = await state.get_state()
            if current:
                menu_texts = {i18n(key) for key in MENU_KEYS}
                if event.text in menu_texts:
                    await state.clear()
        return await handler(event, data)
