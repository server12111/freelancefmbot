from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import Message, User


async def send_message(
    session: AsyncSession,
    sender: User,
    receiver: User,
    text: str | None,
    job_id: int | None = None,
    message_type: str = "text",
    file_id: str | None = None,
    filename: str | None = None,
) -> Message:
    msg = Message(
        sender_id=sender.id,
        receiver_id=receiver.id,
        job_id=job_id,
        text=text,
        message_type=message_type,
        file_id=file_id,
        filename=filename,
    )
    session.add(msg)
    await session.commit()
    await session.refresh(msg)
    return msg


async def get_conversation(
    session: AsyncSession,
    user1_id: int,
    user2_id: int,
    job_id: int | None = None,
    limit: int = 20,
) -> list[Message]:
    filters = [
        or_(
            and_(Message.sender_id == user1_id, Message.receiver_id == user2_id),
            and_(Message.sender_id == user2_id, Message.receiver_id == user1_id),
        )
    ]
    if job_id:
        filters.append(Message.job_id == job_id)

    result = await session.execute(
        select(Message)
        .where(and_(*filters))
        .options(selectinload(Message.sender))
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    messages = list(result.scalars().all())
    return list(reversed(messages))


async def mark_read(
    session: AsyncSession, receiver_id: int, sender_id: int
) -> None:
    result = await session.execute(
        select(Message).where(
            and_(
                Message.receiver_id == receiver_id,
                Message.sender_id == sender_id,
                Message.is_read == False,
            )
        )
    )
    for msg in result.scalars():
        msg.is_read = True
    await session.commit()


async def get_conversations_list(
    session: AsyncSession, user_id: int
) -> list[dict]:
    """Returns unique conversation partners with last message and unread count."""
    result = await session.execute(
        select(Message)
        .where(
            or_(Message.sender_id == user_id, Message.receiver_id == user_id)
        )
        .options(selectinload(Message.sender), selectinload(Message.receiver))
        .order_by(Message.created_at.desc())
    )
    messages = list(result.scalars().all())

    seen: dict[int, dict] = {}
    for msg in messages:
        other_id = msg.receiver_id if msg.sender_id == user_id else msg.sender_id
        if other_id not in seen:
            other = msg.receiver if msg.sender_id == user_id else msg.sender
            seen[other_id] = {
                "user_id": other.id,
                "telegram_id": other.telegram_id,
                "name": other.full_name,
                "job_id": msg.job_id or 0,
                "last_message": msg.text[:50],
                "unread": 0,
            }
        if msg.receiver_id == user_id and not msg.is_read:
            seen[other_id]["unread"] += 1

    return list(seen.values())
