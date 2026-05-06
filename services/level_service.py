from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User

# Thresholds
_LEVELS = [
    ("top",      20, 4.5, 500.0),
    ("pro",      10, 4.0, 0.0),
    ("verified",  3, 0.0, 0.0),
    ("newbie",    0, 0.0, 0.0),
]


def compute_level(completed_orders: int, rating: float, total_earned: float) -> str:
    for name, min_orders, min_rating, min_earned in _LEVELS:
        if (completed_orders >= min_orders
                and rating >= min_rating
                and total_earned >= min_earned):
            return name
    return "newbie"


def level_badge(level: str, i18n) -> str:
    key = f"level_{level}"
    return i18n(key)


async def refresh_level(session: AsyncSession, user: User) -> None:
    new_level = compute_level(
        user.completed_orders or 0,
        user.rating or 0.0,
        user.total_earned or 0.0,
    )
    if (user.level or "newbie") != new_level:
        user.level = new_level
        await session.commit()
