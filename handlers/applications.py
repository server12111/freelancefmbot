from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from database.connection import async_session_maker
from database.models import ApplicationStatus, User
from services.application_service import (
    accept_application,
    create_application,
    get_application,
    get_freelancer_applications,
    get_job_applications,
    has_applied,
    reject_application,
    withdraw_application,
)
from services.escrow_service import create_deal
from services.job_service import get_job, set_job_in_progress
from services.notification_service import (
    notify_application_rejected,
    notify_new_application,
)
from services.user_service import get_user_by_telegram_id
from states import ApplicationState
from utils.helpers import app_status_label, btn, paginate, safe_float
from utils.keyboards import (
    application_actions_kb,
    confirm_cancel_kb,
    my_application_kb,
)

router = Router()


# ── FREELANCER: My Applications ────────────────────────────────────────────

@router.message(btn("btn_my_applications"))
async def handle_my_applications(message: Message, i18n, db_user: User | None) -> None:
    if not db_user:
        return
    await show_my_applications(message, i18n, db_user)


async def show_my_applications(target, i18n, db_user: User, page: int = 1) -> None:
    async with async_session_maker() as session:
        apps = await get_freelancer_applications(session, db_user.id)

    if not apps:
        text = i18n("no_applications")
        if isinstance(target, Message):
            await target.answer(text)
        else:
            await target.message.edit_text(text)
        return

    page_apps, total = paginate(apps, page)
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()

    for app in page_apps:
        status = app_status_label(app.status, i18n)
        label = f"📌 {app.job.title[:30]} — {status}"
        builder.button(text=label, callback_data=f"my_app:{app.id}")
    builder.adjust(1)

    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text=i18n("btn_prev"), callback_data=f"myapps_page:{page-1}"))
    nav.append(InlineKeyboardButton(text=f"{page}/{total}", callback_data="noop"))
    if page < total:
        nav.append(InlineKeyboardButton(text=i18n("btn_next"), callback_data=f"myapps_page:{page+1}"))
    if nav:
        builder.row(*nav)

    text = i18n("my_applications")
    if isinstance(target, Message):
        await target.answer(text, reply_markup=builder.as_markup())
    else:
        await target.message.edit_text(text, reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("myapps_page:"))
async def cb_my_apps_page(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    page = int(callback.data.split(":")[1])
    await show_my_applications(callback, i18n, db_user, page=page)
    await callback.answer()


@router.callback_query(F.data == "my_applications")
async def cb_back_my_apps(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    await show_my_applications(callback, i18n, db_user)
    await callback.answer()


@router.callback_query(F.data.startswith("my_app:"))
async def cb_my_app_detail(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    app_id = int(callback.data.split(":")[1])
    async with async_session_maker() as session:
        app = await get_application(session, app_id)

    if not app:
        await callback.answer(i18n("error_not_found"))
        return

    status = app_status_label(app.status, i18n)
    comment = app.comment or "—"
    text = (
        f"📌 <b>{app.job.title}</b>\n\n"
        f"{i18n('application_item', title=app.job.title, price=app.price, timeframe=app.timeframe, status=status)}\n"
        f"💬 {comment}"
    )

    kb = my_application_kb(app_id, i18n) if app.status == ApplicationStatus.pending else None
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("withdraw_app:"))
async def cb_withdraw_app(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    app_id = int(callback.data.split(":")[1])
    async with async_session_maker() as session:
        app = await get_application(session, app_id)
        if app and app.freelancer_id == db_user.id:
            await withdraw_application(session, app)
    await callback.message.edit_text(i18n("application_withdrawn"))
    await callback.answer()


# ── FREELANCER: Apply ──────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("apply:"))
async def cb_apply_start(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    if not db_user:
        await callback.answer(i18n("error_permission"))
        return

    job_id = int(callback.data.split(":")[1])
    async with async_session_maker() as session:
        job = await get_job(session, job_id)
        if not job:
            await callback.answer(i18n("error_not_found"))
            return
        if job.employer_id == db_user.id:
            await callback.answer(i18n("error_own_job"), show_alert=True)
            return
        if await has_applied(session, job_id, db_user.id):
            await callback.answer(i18n("already_applied"))
            return

    await state.update_data(apply_job_id=job_id, apply_job_title=job.title)
    await callback.message.edit_text(i18n("apply_price", title=job.title))
    await state.set_state(ApplicationState.price)
    await callback.answer()


@router.message(ApplicationState.price)
async def apply_price(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    price = safe_float(message.text)
    if price is None:
        await message.answer(i18n("invalid_amount"))
        return
    await state.update_data(apply_price=price)
    await message.answer(i18n("apply_timeframe"))
    await state.set_state(ApplicationState.timeframe)


@router.message(ApplicationState.timeframe)
async def apply_timeframe(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    timeframe = message.text.strip()
    if not timeframe:
        await message.answer(i18n("error_invalid_input"))
        return
    await state.update_data(apply_timeframe=timeframe)
    await message.answer(i18n("apply_comment"))
    await state.set_state(ApplicationState.comment)


@router.message(ApplicationState.comment)
async def apply_comment(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    if message.text == "/skip":
        comment = None
    else:
        comment = message.text.strip()

    data = await state.get_data()
    await state.update_data(apply_comment=comment)

    await message.answer(
        i18n(
            "apply_confirm",
            title=data["apply_job_title"],
            price=data["apply_price"],
            timeframe=data["apply_timeframe"],
            comment=comment or "—",
        ),
        reply_markup=confirm_cancel_kb(i18n, "confirm_apply", "cancel_apply"),
    )
    await state.set_state(ApplicationState.confirm)


@router.callback_query(F.data == "confirm_apply", ApplicationState.confirm)
async def confirm_apply(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    data = await state.get_data()
    await state.clear()

    employer_tg_id = None
    employer_lang = "en"
    notif_enabled = True
    freelancer_name = ""
    job_title = ""

    async with async_session_maker() as session:
        user = await get_user_by_telegram_id(session, callback.from_user.id)
        job = await get_job(session, data["apply_job_id"])
        if not job:
            await callback.answer(i18n("error_not_found"))
            return
        await create_application(
            session, job, user,
            price=data["apply_price"],
            timeframe=data["apply_timeframe"],
            comment=data.get("apply_comment"),
        )
        # Collect employer notification data before session closes
        employer_tg_id = job.employer.telegram_id
        employer_lang = job.employer.language.value if job.employer.language else "en"
        notif_enabled = bool(getattr(job.employer, "notifications_enabled", True))
        freelancer_name = user.full_name
        job_title = job.title

    await callback.message.edit_text(i18n("application_sent"))

    if employer_tg_id:
        from localization import get_i18n
        emp_i18n = get_i18n(employer_lang)
        await notify_new_application(
            callback.bot, employer_tg_id, freelancer_name, job_title,
            emp_i18n, notif_enabled,
        )

    await callback.answer()


@router.callback_query(F.data == "cancel_apply")
async def cancel_apply(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    await state.clear()
    await callback.message.edit_text(i18n("main_menu"))
    await callback.answer()


# ── EMPLOYER: View applications ────────────────────────────────────────────

@router.message(btn("btn_applications"))
async def handle_applications_menu(message: Message, i18n, db_user: User | None) -> None:
    if not db_user:
        return
    # Show employer's jobs to pick from
    async with async_session_maker() as session:
        from services.job_service import get_employer_jobs
        jobs = await get_employer_jobs(session, db_user.id)

    if not jobs:
        await message.answer(i18n("no_jobs"))
        return

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    for job in jobs[:10]:
        builder.button(text=f"📌 {job.title[:40]}", callback_data=f"job_apps:{job.id}")
    builder.adjust(1)
    await message.answer(i18n("my_jobs"), reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("job_apps:"))
async def cb_job_applications(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    job_id = int(callback.data.split(":")[1])
    async with async_session_maker() as session:
        job = await get_job(session, job_id)
        apps = await get_job_applications(session, job_id)

    if not job:
        await callback.answer(i18n("error_not_found"))
        return

    if not apps:
        await callback.message.edit_text(
            i18n("no_employer_applications"),
            reply_markup=confirm_cancel_kb(i18n, f"ej:{job_id}", f"ej:{job_id}"),
        )
        await callback.answer()
        return

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    for app in apps:
        label = f"👤 {app.freelancer.full_name} — ${app.price:.0f}"
        builder.button(text=label, callback_data=f"view_app:{app.id}")
    builder.button(text=i18n("btn_back"), callback_data=f"ej:{job_id}")
    builder.adjust(1)

    await callback.message.edit_text(
        i18n("employer_applications", title=job.title, count=len(apps)),
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("view_app:"))
async def cb_view_application(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    app_id = int(callback.data.split(":")[1])
    async with async_session_maker() as session:
        app = await get_application(session, app_id)

    if not app:
        await callback.answer(i18n("error_not_found"))
        return

    comment = app.comment or "—"
    text = i18n(
        "application_details",
        name=app.freelancer.full_name,
        price=app.price,
        timeframe=app.timeframe,
        comment=comment,
    )
    await callback.message.edit_text(text, reply_markup=application_actions_kb(app_id, i18n))
    await callback.answer()


@router.callback_query(F.data.startswith("accept_app:"))
async def cb_accept_application(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    app_id = int(callback.data.split(":")[1])
    async with async_session_maker() as session:
        app = await get_application(session, app_id)
        if not app:
            await callback.answer(i18n("error_not_found"))
            return

        job = await get_job(session, app.job_id)
        await accept_application(session, app)
        deal = await create_deal(session, job, app)
        await set_job_in_progress(session, job)

        freelancer_tg_id = app.freelancer.telegram_id
        job_title = job.title

    from utils.keyboards import deal_employer_kb
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(
        text=i18n("btn_fund_escrow", amount=deal.amount),
        callback_data=f"fund_escrow:{deal.id}",
    )
    await callback.message.edit_text(
        i18n("application_accepted_employer"),
        reply_markup=builder.as_markup(),
    )

    await callback.answer()


@router.callback_query(F.data.startswith("reject_app:"))
async def cb_reject_application(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    app_id = int(callback.data.split(":")[1])
    async with async_session_maker() as session:
        app = await get_application(session, app_id)
        if not app:
            await callback.answer(i18n("error_not_found"))
            return
        freelancer_tg_id = app.freelancer.telegram_id
        job_title = app.job.title
        await reject_application(session, app)

    await callback.message.edit_text(i18n("application_rejected_employer"))
    await notify_application_rejected(callback.bot, freelancer_tg_id, job_title, i18n)
    await callback.answer()


@router.callback_query(F.data == "back_to_apps")
async def cb_back_to_apps(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    await callback.message.edit_text(i18n("main_menu"))
    await callback.answer()
