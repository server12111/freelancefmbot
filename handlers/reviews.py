from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from database.connection import async_session_maker
from database.models import User
from services.escrow_service import get_deal
from services.review_service import (
    create_review,
    get_reviews_by_user,
    get_reviews_for_user,
    has_reviewed,
)
from services.user_service import get_user_by_id, get_user_by_telegram_id
from states import ReviewState
from utils.helpers import btn, format_date
from utils.keyboards import rating_kb, review_text_kb

router = Router()


@router.message(btn("btn_reviews"))
async def handle_reviews_menu(message: Message, i18n, db_user: User | None) -> None:
    if not db_user:
        return
    await show_reviews_received(message, i18n, db_user)


async def show_reviews_received(target, i18n, db_user: User) -> None:
    async with async_session_maker() as session:
        reviews = await get_reviews_for_user(session, db_user.id)

    if not reviews:
        text = i18n("no_reviews")
    else:
        lines = [i18n("reviews_received")]
        for r in reviews[:10]:
            t = r.text or "—"
            lines.append(i18n("review_item", rating=r.rating, author=r.reviewer.full_name, text=t, date=format_date(r.created_at)))
        text = "\n".join(lines)

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text=i18n("btn_reviews_received"), callback_data="reviews_received")
    builder.button(text=i18n("btn_reviews_given"),    callback_data="my_given_reviews")
    builder.adjust(2)
    kb = builder.as_markup()

    if isinstance(target, Message):
        await target.answer(text, reply_markup=kb)
    else:
        await target.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data == "my_given_reviews")
async def cb_given_reviews(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    async with async_session_maker() as session:
        reviews = await get_reviews_by_user(session, db_user.id)

    if not reviews:
        text = i18n("no_reviews")
    else:
        lines = [i18n("reviews_given")]
        for r in reviews[:10]:
            t = r.text or "—"
            lines.append(i18n("review_item", rating=r.rating, author=r.reviewee.full_name, text=t, date=format_date(r.created_at)))
        text = "\n".join(lines)

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text=i18n("btn_reviews_received"), callback_data="reviews_received")
    builder.button(text=i18n("btn_reviews_given"),    callback_data="my_given_reviews")
    builder.adjust(2)
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data == "reviews_received")
async def cb_reviews_received(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    await show_reviews_received(callback, i18n, db_user)
    await callback.answer()


# ── Leave a review (triggered after deal completed) ────────────────────────

@router.callback_query(F.data.startswith("rate:"))
async def cb_rate(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    parts = callback.data.split(":")
    deal_id = int(parts[1])
    rating = int(parts[2])

    await state.update_data(review_deal_id=deal_id, review_rating=rating)
    await callback.message.edit_text(
        i18n("review_text_prompt"),
        reply_markup=review_text_kb(i18n),
    )
    await state.set_state(ReviewState.text)
    await callback.answer()


@router.message(ReviewState.text)
async def review_text_input(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    text = message.text.strip() if message.text != "/skip" else None
    data = await state.get_data()
    deal_id = data["review_deal_id"]
    rating = data["review_rating"]
    await state.clear()

    async with async_session_maker() as session:
        deal = await get_deal(session, deal_id)
        if not deal:
            await message.answer(i18n("error_not_found"))
            return

        reviewer = await get_user_by_telegram_id(session, message.from_user.id)
        # Determine reviewee
        if reviewer.id == deal.employer_id:
            reviewee = await get_user_by_id(session, deal.freelancer_id)
        else:
            reviewee = await get_user_by_id(session, deal.employer_id)

        if await has_reviewed(session, deal_id, reviewer.id):
            await message.answer(i18n("error_general"))
            return

        await create_review(session, deal, reviewer, reviewee, rating, text)

    await message.answer(i18n("review_submitted"))


@router.callback_query(F.data == "skip_review_text")
async def cb_skip_review_text(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    data = await state.get_data()
    deal_id = data.get("review_deal_id")
    rating = data.get("review_rating")
    await state.clear()

    if not deal_id or not rating:
        await callback.answer()
        return

    async with async_session_maker() as session:
        deal = await get_deal(session, deal_id)
        reviewer = await get_user_by_telegram_id(session, callback.from_user.id)
        if reviewer.id == deal.employer_id:
            reviewee = await get_user_by_id(session, deal.freelancer_id)
        else:
            reviewee = await get_user_by_id(session, deal.employer_id)

        if not await has_reviewed(session, deal_id, reviewer.id):
            await create_review(session, deal, reviewer, reviewee, rating, None)

    await callback.message.edit_text(i18n("review_submitted"))
    await callback.answer()
