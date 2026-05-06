from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import and_, case, select

from database.connection import async_session_maker
from database.models import BotSettings, JobCategory, Service, ServiceOrder, User
from services.notification_service import notify
from services.user_service import get_user_by_telegram_id
from states import ServiceCreationState
from utils.helpers import btn, category_label, format_date, safe_float
from utils.keyboards import (
    REMOVE,
    categories_kb,
    confirm_cancel_kb,
    my_services_list_kb,
    service_detail_kb,
    service_order_buyer_kb,
    service_order_seller_kb,
    services_list_kb,
)

router = Router()

PLATFORM_FEE_PCT = 0.05
DEFAULT_PROMO_PRICE = 5.0
PROMO_DAYS = 7


async def get_promo_price() -> float:
    async with async_session_maker() as session:
        result = await session.execute(
            select(BotSettings).where(BotSettings.key == "service_promo_price")
        )
        row = result.scalar_one_or_none()
    return float(row.value) if row else DEFAULT_PROMO_PRICE


# ── Browse services ────────────────────────────────────────────────────────

@router.message(btn("btn_browse_services"))
async def handle_browse_services(message: Message, i18n, db_user: User | None) -> None:
    if not db_user:
        return
    await show_services_list(message, i18n)


async def show_services_list(target, i18n) -> None:
    now = datetime.now(timezone.utc)
    async with async_session_maker() as session:
        result = await session.execute(
            select(Service)
            .where(Service.is_active == True)
            .order_by(
                case(
                    (and_(Service.is_promoted == True, Service.promoted_until > now), 1),
                    else_=0,
                ).desc(),
                Service.created_at.desc(),
            )
            .limit(30)
        )
        services = result.scalars().all()

    if not services:
        text = i18n("no_services")
        if isinstance(target, Message):
            await target.answer(text)
        else:
            await target.message.edit_text(text)
        return

    text = i18n("services_list")
    kb = services_list_kb(services, i18n)
    if isinstance(target, Message):
        await target.answer(text, reply_markup=kb)
    else:
        await target.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data == "browse_services")
async def cb_browse_services(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    await show_services_list(callback, i18n)
    await callback.answer()


@router.callback_query(F.data.startswith("svc:"))
async def cb_service_detail(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    service_id = int(callback.data.split(":")[1])
    async with async_session_maker() as session:
        result = await session.execute(select(Service).where(Service.id == service_id))
        service = result.scalar_one_or_none()

    if not service:
        await callback.answer(i18n("error_not_found"))
        return

    is_own = db_user and service.seller_id == db_user.id
    now = datetime.now(timezone.utc)
    is_promoted = service.is_promoted and service.promoted_until and service.promoted_until > now
    cat_label = category_label(service.category, i18n)
    promo_badge = "🚀 " if is_promoted else ""
    text = i18n(
        "service_details",
        title=promo_badge + service.title,
        description=service.description,
        category=cat_label,
        price=service.price,
        seller=service.seller.full_name,
        orders=service.orders_count,
        date=format_date(service.created_at),
    )
    await callback.message.edit_text(
        text,
        reply_markup=service_detail_kb(service_id, service.seller_id, i18n, is_own=is_own, is_promoted=is_promoted),
    )
    await callback.answer()


# ── Buy service ────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("svc_buy:"))
async def cb_buy_service(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    if not db_user:
        return
    service_id = int(callback.data.split(":")[1])

    async with async_session_maker() as session:
        result = await session.execute(select(Service).where(Service.id == service_id))
        service = result.scalar_one_or_none()

        if not service or not service.is_active:
            await callback.answer(i18n("error_not_found"), show_alert=True)
            return
        if service.seller_id == db_user.id:
            await callback.answer(i18n("error_own_service"), show_alert=True)
            return

        buyer = await get_user_by_telegram_id(session, callback.from_user.id)
        if buyer.balance < service.price:
            await callback.answer(
                i18n("insufficient_balance", available=buyer.balance), show_alert=True
            )
            return

        fee = round(service.price * PLATFORM_FEE_PCT, 2)
        buyer.balance -= service.price

        order = ServiceOrder(
            service_id=service_id,
            buyer_id=buyer.id,
            seller_id=service.seller_id,
            amount=service.price,
            platform_fee=fee,
            status="escrow",
        )
        session.add(order)
        service.orders_count += 1
        await session.commit()
        await session.refresh(order)

        seller_tg_id = service.seller.telegram_id
        service_title = service.title
        order_id = order.id
        buyer_name = buyer.full_name

    await callback.message.edit_text(
        i18n("service_purchased", title=service_title, amount=service.price)
    )
    await notify(
        callback.bot, seller_tg_id,
        i18n("service_new_order", title=service_title, buyer=buyer_name, amount=service.price),
        reply_markup=service_order_seller_kb(order_id, i18n),
    )
    await callback.answer()


# ── Seller: mark delivered ─────────────────────────────────────────────────

@router.callback_query(F.data.startswith("svc_delivered:"))
async def cb_service_delivered(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    order_id = int(callback.data.split(":")[1])
    async with async_session_maker() as session:
        result = await session.execute(select(ServiceOrder).where(ServiceOrder.id == order_id))
        order = result.scalar_one_or_none()

        if not order or order.status != "escrow":
            await callback.answer(i18n("error_not_found"))
            return
        if order.seller_id != db_user.id:
            await callback.answer(i18n("error_permission"))
            return

        order.status = "delivered"
        await session.commit()
        buyer_tg_id = order.buyer.telegram_id
        service_title = order.service.title

    await callback.message.edit_text(i18n("service_delivery_sent"))
    await notify(
        callback.bot, buyer_tg_id,
        i18n("service_delivery_received", title=service_title),
        reply_markup=service_order_buyer_kb(order_id, i18n),
    )
    await callback.answer()


# ── Buyer: confirm receipt ─────────────────────────────────────────────────

@router.callback_query(F.data.startswith("svc_confirm:"))
async def cb_service_confirm(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    order_id = int(callback.data.split(":")[1])
    async with async_session_maker() as session:
        result = await session.execute(select(ServiceOrder).where(ServiceOrder.id == order_id))
        order = result.scalar_one_or_none()

        if not order or order.status != "delivered":
            await callback.answer(i18n("error_not_found"))
            return
        if order.buyer_id != db_user.id:
            await callback.answer(i18n("error_permission"))
            return

        net = round(order.amount - order.platform_fee, 2)
        from services.user_service import get_user_by_id
        seller = await get_user_by_id(session, order.seller_id)
        seller.balance += net
        seller.completed_orders += 1
        order.status = "completed"
        await session.commit()

        seller_tg_id = seller.telegram_id
        service_title = order.service.title

    await callback.message.edit_text(i18n("service_confirmed"))
    await notify(
        callback.bot, seller_tg_id,
        i18n("service_payment_received", title=service_title, amount=net),
    )
    await callback.answer()


# ── Buyer: dispute ─────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("svc_dispute:"))
async def cb_service_dispute(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    await callback.answer(i18n("service_dispute_hint"), show_alert=True)


# ── My services ────────────────────────────────────────────────────────────

@router.message(btn("btn_my_services"))
async def handle_my_services(message: Message, i18n, db_user: User | None) -> None:
    if not db_user:
        return
    await show_my_services(message, i18n, db_user)


async def show_my_services(target, i18n, db_user: User) -> None:
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    async with async_session_maker() as session:
        result = await session.execute(
            select(Service)
            .where(Service.seller_id == db_user.id)
            .order_by(Service.created_at.desc())
        )
        services = result.scalars().all()

    if not services:
        text = i18n("my_services_empty")
        builder = InlineKeyboardBuilder()
        builder.button(text=i18n("btn_create_service"), callback_data="svc_create")
        kb = builder.as_markup()
    else:
        text = i18n("my_services")
        kb = my_services_list_kb(services, i18n)

    if isinstance(target, Message):
        await target.answer(text, reply_markup=kb)
    else:
        await target.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data == "my_services_back")
async def cb_my_services_back(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    if not db_user:
        return
    await show_my_services(callback, i18n, db_user)
    await callback.answer()


@router.callback_query(F.data.startswith("mysvc:"))
async def cb_my_service_detail(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    service_id = int(callback.data.split(":")[1])
    async with async_session_maker() as session:
        result = await session.execute(select(Service).where(Service.id == service_id))
        service = result.scalar_one_or_none()

    if not service:
        await callback.answer(i18n("error_not_found"))
        return

    now = datetime.now(timezone.utc)
    is_promoted = service.is_promoted and service.promoted_until and service.promoted_until > now
    cat_label = category_label(service.category, i18n)
    promo_badge = "🚀 " if is_promoted else ""
    text = i18n(
        "service_details",
        title=promo_badge + service.title,
        description=service.description,
        category=cat_label,
        price=service.price,
        seller=service.seller.full_name,
        orders=service.orders_count,
        date=format_date(service.created_at),
    )
    await callback.message.edit_text(
        text,
        reply_markup=service_detail_kb(service_id, service.seller_id, i18n, is_own=True, is_promoted=is_promoted),
    )
    await callback.answer()


# ── Toggle service active ──────────────────────────────────────────────────

@router.callback_query(F.data.startswith("svc_toggle:"))
async def cb_toggle_service(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    service_id = int(callback.data.split(":")[1])
    async with async_session_maker() as session:
        result = await session.execute(select(Service).where(Service.id == service_id))
        service = result.scalar_one_or_none()

        if not service or service.seller_id != db_user.id:
            await callback.answer(i18n("error_permission"))
            return

        service.is_active = not service.is_active
        await session.commit()
        is_active = service.is_active

    key = "service_activated" if is_active else "service_paused"
    await callback.answer(i18n(key), show_alert=True)
    await cb_my_service_detail(callback, i18n, db_user)


# ── Promote service ────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("svc_promote:"))
async def cb_promote_service(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    if not db_user:
        return
    service_id = int(callback.data.split(":")[1])
    price = await get_promo_price()

    async with async_session_maker() as session:
        result = await session.execute(select(Service).where(Service.id == service_id))
        service = result.scalar_one_or_none()
        if not service or service.seller_id != db_user.id:
            await callback.answer(i18n("error_permission"))
            return

    from utils.keyboards import confirm_cancel_kb as _cc
    await callback.message.edit_text(
        i18n("service_promo_confirm", title=service.title, price=price, days=PROMO_DAYS),
        reply_markup=_cc(i18n, f"svc_promo_ok:{service_id}", "my_services_back"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("svc_promo_ok:"))
async def cb_promote_service_confirm(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    if not db_user:
        return
    service_id = int(callback.data.split(":")[1])
    price = await get_promo_price()

    async with async_session_maker() as session:
        from services.user_service import get_user_by_telegram_id as _get
        user = await _get(session, callback.from_user.id)

        if user.balance < price:
            await callback.answer(
                i18n("insufficient_balance", available=user.balance), show_alert=True
            )
            return

        result = await session.execute(select(Service).where(Service.id == service_id))
        service = result.scalar_one_or_none()
        if not service or service.seller_id != db_user.id:
            await callback.answer(i18n("error_permission"))
            return

        user.balance -= price
        service.is_promoted = True
        service.promoted_until = datetime.now(timezone.utc) + timedelta(days=PROMO_DAYS)
        await session.commit()

    await callback.message.edit_text(
        i18n("service_promoted", title=service.title, days=PROMO_DAYS)
    )
    await callback.answer()


# ── Create service flow ────────────────────────────────────────────────────

@router.callback_query(F.data == "svc_create")
async def cb_create_service(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    await callback.message.edit_text(i18n("create_service_title"))
    await state.set_state(ServiceCreationState.title)
    await callback.answer()


@router.message(ServiceCreationState.title)
async def svc_title(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    title = message.text.strip() if message.text else ""
    if not title or len(title) > 200:
        await message.answer(i18n("error_invalid_input"))
        return
    await state.update_data(svc_title=title)
    await message.answer(i18n("create_service_description"))
    await state.set_state(ServiceCreationState.description)


@router.message(ServiceCreationState.description)
async def svc_description(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    desc = message.text.strip() if message.text else ""
    if not desc:
        await message.answer(i18n("error_invalid_input"))
        return
    await state.update_data(svc_description=desc)
    await message.answer(i18n("create_service_category"), reply_markup=categories_kb(i18n, "svc_cat"))
    await state.set_state(ServiceCreationState.category)


@router.callback_query(F.data.startswith("svc_cat:"), ServiceCreationState.category)
async def svc_category(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    cat = callback.data.split(":")[1]
    await state.update_data(svc_category=cat)
    await callback.message.edit_text(i18n("create_service_price"))
    await state.set_state(ServiceCreationState.price)
    await callback.answer()


@router.message(ServiceCreationState.price)
async def svc_price(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    price = safe_float(message.text)
    if price is None or price <= 0:
        await message.answer(i18n("invalid_amount"))
        return
    await state.update_data(svc_price=price)
    data = await state.get_data()
    cat_label = category_label(JobCategory(data["svc_category"]), i18n)
    await message.answer(
        i18n(
            "create_service_confirm",
            title=data["svc_title"],
            description=data["svc_description"],
            category=cat_label,
            price=price,
        ),
        reply_markup=confirm_cancel_kb(i18n, "confirm_service", "cancel_service"),
    )
    await state.set_state(ServiceCreationState.confirm)


@router.callback_query(F.data == "confirm_service", ServiceCreationState.confirm)
async def confirm_create_service(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    if not db_user:
        return
    data = await state.get_data()
    await state.clear()

    async with async_session_maker() as session:
        user = await get_user_by_telegram_id(session, callback.from_user.id)
        service = Service(
            seller_id=user.id,
            title=data["svc_title"],
            description=data["svc_description"],
            category=data["svc_category"],
            price=data["svc_price"],
        )
        session.add(service)
        await session.commit()

    await callback.message.edit_text(i18n("service_created", title=data["svc_title"]))
    await callback.answer()


@router.callback_query(F.data == "cancel_service")
async def cancel_create_service(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    await state.clear()
    await callback.message.edit_text(i18n("service_creation_cancelled"))
    await callback.answer()
