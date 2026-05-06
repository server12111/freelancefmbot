from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from database.connection import async_session_maker
from database.models import User
from services.application_service import get_job_applications, has_applied
from services.job_service import (
    cancel_job,
    create_job,
    get_employer_jobs,
    get_job,
    get_open_jobs,
)
from states import JobCreationState, JobFilterState
from utils.helpers import (
    btn,
    category_label,
    format_date,
    job_status_label,
    paginate,
    safe_float,
)
from utils.keyboards import (
    REMOVE,
    categories_kb,
    confirm_cancel_kb,
    filter_advanced_kb,
    job_detail_employer_kb,
    job_detail_freelancer_kb,
    job_promotion_kb,
    jobs_list_kb,
)

router = Router()

ITEMS_PER_PAGE = 5


# ── EMPLOYER: Create job ───────────────────────────────────────────────────

@router.message(btn("btn_create_job"))
async def handle_create_job(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    if not db_user:
        return
    await state.clear()
    await message.answer(i18n("create_job_start"), reply_markup=REMOVE)
    await state.set_state(JobCreationState.title)


@router.message(JobCreationState.title)
async def job_title(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    title = message.text.strip() if message.text else ""
    if not title or len(title) > 200:
        await message.answer(i18n("error_invalid_input"))
        return
    await state.update_data(title=title)
    await message.answer(i18n("create_job_description"))
    await state.set_state(JobCreationState.description)


@router.message(JobCreationState.description)
async def job_description(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    desc = message.text.strip() if message.text else ""
    if not desc:
        await message.answer(i18n("error_invalid_input"))
        return
    await state.update_data(description=desc)
    await message.answer(i18n("create_job_category"), reply_markup=categories_kb(i18n, "job_cat"))
    await state.set_state(JobCreationState.category)


@router.callback_query(F.data.startswith("job_cat:"), JobCreationState.category)
async def job_category(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    cat = callback.data.split(":")[1]
    await state.update_data(category=cat)
    await callback.message.edit_text(i18n("create_job_budget"))
    await state.set_state(JobCreationState.budget)
    await callback.answer()


@router.message(JobCreationState.budget)
async def job_budget(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    budget = safe_float(message.text)
    if budget is None:
        await message.answer(i18n("invalid_budget"))
        return
    await state.update_data(budget=budget)
    await message.answer(i18n("create_job_deadline"))
    await state.set_state(JobCreationState.deadline)


@router.message(JobCreationState.deadline)
async def job_deadline(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    deadline = message.text.strip() if message.text else ""
    if not deadline:
        await message.answer(i18n("error_invalid_input"))
        return
    await state.update_data(deadline=deadline)
    data = await state.get_data()

    from database.models import JobCategory
    cat_label = category_label(JobCategory(data["category"]), i18n)

    await message.answer(
        i18n(
            "create_job_confirm",
            title=data["title"],
            description=data["description"],
            category=cat_label,
            budget=data["budget"],
            deadline=data["deadline"],
        ),
        reply_markup=confirm_cancel_kb(i18n, "confirm_job", "cancel_job_creation"),
    )
    await state.set_state(JobCreationState.confirm)


@router.callback_query(F.data == "confirm_job", JobCreationState.confirm)
async def confirm_create_job(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    if not db_user:
        return
    data = await state.get_data()
    await state.clear()

    async with async_session_maker() as session:
        from services.user_service import get_user_by_telegram_id
        user = await get_user_by_telegram_id(session, callback.from_user.id)
        job = await create_job(
            session, user,
            title=data["title"],
            description=data["description"],
            category=data["category"],
            budget=data["budget"],
            deadline=data["deadline"],
        )

    from utils.keyboards import main_menu
    await callback.message.edit_text(i18n("job_created", title=data["title"]))
    await callback.message.answer(i18n("main_menu"), reply_markup=main_menu(None, i18n))
    await callback.answer()


@router.callback_query(F.data == "cancel_job_creation")
async def cancel_create_job(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    await state.clear()
    from utils.keyboards import main_menu
    await callback.message.edit_text(i18n("main_menu"))
    await callback.message.answer(i18n("main_menu"), reply_markup=main_menu(None, i18n))
    await callback.answer()


# ── EMPLOYER: My Jobs ──────────────────────────────────────────────────────

@router.message(btn("btn_my_jobs"))
async def handle_my_jobs(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    if not db_user:
        return
    await show_my_jobs(message, i18n, db_user, page=1)


async def show_my_jobs(target, i18n, db_user: User, page: int = 1) -> None:
    async with async_session_maker() as session:
        jobs = await get_employer_jobs(session, db_user.id)

    if not jobs:
        text = i18n("no_jobs")
        if isinstance(target, Message):
            await target.answer(text)
        else:
            await target.message.edit_text(text)
        return

    page_jobs, total = paginate(jobs, page)
    lines = [i18n("my_jobs")]
    for job in page_jobs:
        status = job_status_label(job.status, i18n)
        badge = "💎 " if job.is_vip else ("🔥 " if job.is_boosted else "")
        lines.append(f"\n{badge}📌 <b>{job.title}</b>  {status}\n💰 ${job.budget:.2f} | 📊 {len(job.applications)} apps")

    builder = _jobs_nav_builder(page_jobs, page, total, i18n, prefix="ej")

    text = "\n".join(lines)
    if isinstance(target, Message):
        await target.answer(text, reply_markup=builder)
    else:
        await target.message.edit_text(text, reply_markup=builder)


def _jobs_nav_builder(jobs, page, total, i18n, prefix="job"):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    for job in jobs:
        builder.button(text=f"📌 {job.title[:35]}", callback_data=f"{prefix}:{job.id}")
    builder.adjust(2)
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text=i18n("btn_prev"), callback_data=f"myjobs_page:{page-1}"))
    nav.append(InlineKeyboardButton(text=f"{page}/{total}", callback_data="noop"))
    if page < total:
        nav.append(InlineKeyboardButton(text=i18n("btn_next"), callback_data=f"myjobs_page:{page+1}"))
    if nav:
        builder.row(*nav)
    return builder.as_markup()


@router.callback_query(F.data.startswith("myjobs_page:"))
async def cb_my_jobs_page(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    page = int(callback.data.split(":")[1])
    await show_my_jobs(callback, i18n, db_user, page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("ej:"))
async def cb_employer_job_detail(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    job_id = int(callback.data.split(":")[1])
    async with async_session_maker() as session:
        job = await get_job(session, job_id)
        apps = await get_job_applications(session, job_id)

    if not job:
        await callback.answer(i18n("error_not_found"))
        return

    cat_label = category_label(job.category, i18n)
    badge = "💎 VIP | " if job.is_vip else ("🔥 Boosted | " if job.is_boosted else "")
    text = i18n(
        "job_details",
        title=f"{badge}{job.title}",
        description=job.description,
        category=cat_label,
        budget=job.budget,
        deadline=job.deadline,
        employer=job.employer.full_name,
        app_count=len(apps),
        date=format_date(job.created_at),
    )
    await callback.message.edit_text(text, reply_markup=job_detail_employer_kb(job_id, len(apps), i18n))
    await callback.answer()


@router.callback_query(F.data.startswith("cancel_job:"))
async def cb_cancel_job(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    job_id = int(callback.data.split(":")[1])
    await callback.message.edit_text(
        i18n("confirm_cancel_job"),
        reply_markup=confirm_cancel_kb(i18n, f"do_cancel_job:{job_id}", f"ej:{job_id}"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("do_cancel_job:"))
async def cb_do_cancel_job(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    job_id = int(callback.data.split(":")[1])
    async with async_session_maker() as session:
        job = await get_job(session, job_id)
        if job and job.employer_id == db_user.id:
            await cancel_job(session, job)
    await callback.message.edit_text(i18n("job_cancelled"))
    await callback.answer()


# ── EMPLOYER: Promote job ──────────────────────────────────────────────────

@router.callback_query(F.data.startswith("job_promote:"))
async def cb_job_promote(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    job_id = int(callback.data.split(":")[1])
    await callback.message.edit_text(
        i18n("promote_select_type"),
        reply_markup=job_promotion_kb(job_id, i18n),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("promote:"))
async def cb_promote_do(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    parts = callback.data.split(":")
    promo_type_str = parts[1]
    job_id = int(parts[2])

    from database.models import PromotionType
    from services.promotion_service import BOOST_COST, VIP_COST, promote_job

    async with async_session_maker() as session:
        from services.user_service import get_user_by_telegram_id
        employer = await get_user_by_telegram_id(session, callback.from_user.id)
        job = await get_job(session, job_id)
        if not job or job.employer_id != employer.id:
            await callback.answer(i18n("error_permission"))
            return

        promo_type = PromotionType.boost if promo_type_str == "boost" else PromotionType.vip
        cost = BOOST_COST if promo_type == PromotionType.boost else VIP_COST
        success = await promote_job(session, job, employer, promo_type)

    if not success:
        await callback.answer(i18n("promotion_insufficient_funds", cost=cost), show_alert=True)
        return

    key = "boost_activated" if promo_type_str == "boost" else "vip_activated"
    await callback.message.edit_text(i18n(key))
    await callback.answer()


# ── FREELANCER: Find Jobs ──────────────────────────────────────────────────

@router.message(btn("btn_find_jobs"))
async def handle_find_jobs(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    if not db_user:
        return
    await state.update_data(
        job_page=1,
        filter_category=None,
        filter_budget_min=None,
        filter_budget_max=None,
        filter_keyword=None,
    )
    await show_jobs_list(message, i18n, db_user, state)


async def show_jobs_list(target, i18n, db_user: User, state: FSMContext, page: int = 1) -> None:
    data = await state.get_data()
    cat = data.get("filter_category")
    bmin = data.get("filter_budget_min")
    bmax = data.get("filter_budget_max")
    keyword = data.get("filter_keyword")

    async with async_session_maker() as session:
        jobs = await get_open_jobs(
            session,
            category=cat,
            budget_min=bmin,
            budget_max=bmax,
            keyword=keyword,
        )

    if not jobs:
        text = i18n("jobs_list_empty")
        kb = _empty_filter_kb(i18n)
        if isinstance(target, Message):
            await target.answer(text, reply_markup=kb)
        else:
            await target.message.edit_text(text, reply_markup=kb)
        return

    page_jobs, total = paginate(jobs, page)
    kb = jobs_list_kb(page_jobs, page, total, i18n)
    text = i18n("jobs_list")

    if isinstance(target, Message):
        await target.answer(text, reply_markup=kb)
    else:
        await target.message.edit_text(text, reply_markup=kb)


def _empty_filter_kb(i18n, funded_only=False):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text=i18n("btn_filters"),       callback_data="filters")
    builder.button(text=i18n("btn_clear_filters"), callback_data="clear_filters")
    builder.adjust(2)
    return builder.as_markup()


@router.callback_query(F.data.startswith("page:"))
async def cb_jobs_page(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    page = int(callback.data.split(":")[1])
    await show_jobs_list(callback, i18n, db_user, state, page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("job:"))
async def cb_job_detail(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    job_id = int(callback.data.split(":")[1])
    async with async_session_maker() as session:
        job = await get_job(session, job_id)
        app_count = len(await get_job_applications(session, job_id))
        applied = await has_applied(session, job_id, db_user.id)

    if not job:
        await callback.answer(i18n("error_not_found"))
        return

    cat_label = category_label(job.category, i18n)
    badge = "💎 VIP | " if job.is_vip else ("🔥 " if job.is_boosted else "")
    text = i18n(
        "job_details",
        title=f"{badge}{job.title}",
        description=job.description,
        category=cat_label,
        budget=job.budget,
        deadline=job.deadline,
        employer=job.employer.full_name,
        app_count=app_count,
        date=format_date(job.created_at),
    )

    from database.models import JobStatus
    is_own_job = db_user and job.employer_id == db_user.id

    if is_own_job:
        await callback.message.edit_text(
            text,
            reply_markup=job_detail_employer_kb(job_id, app_count, i18n),
        )
    elif job.status != JobStatus.open or applied:
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()
        builder.button(text=i18n("btn_back"), callback_data="jobs_list")
        kb = builder.as_markup()
        note = i18n("already_applied") if applied else i18n("job_closed")
        await callback.message.edit_text(f"{text}\n\n{note}", reply_markup=kb)
    else:
        await callback.message.edit_text(
            text,
            reply_markup=job_detail_freelancer_kb(job_id, i18n, employer_db_id=job.employer_id),
        )
    await callback.answer()


@router.callback_query(F.data == "jobs_list")
async def cb_back_to_jobs(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    await show_jobs_list(callback, i18n, db_user, state)
    await callback.answer()


@router.callback_query(F.data == "my_jobs")
async def cb_back_to_my_jobs(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    if not db_user:
        return
    await show_my_jobs(callback, i18n, db_user, page=1)
    await callback.answer()


@router.callback_query(F.data == "back")
async def cb_back_generic(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    await state.clear()
    await show_jobs_list(callback, i18n, db_user, state)
    await callback.answer()


# ── Filters ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "filters")
async def cb_filters(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    await callback.message.edit_text(
        i18n("filter_menu_prompt"),
        reply_markup=filter_advanced_kb(i18n),
    )
    await callback.answer()


@router.callback_query(F.data == "filter:category")
async def cb_filter_category_start(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    await callback.message.edit_text(
        i18n("filter_category_prompt"),
        reply_markup=categories_kb(i18n, "fcat"),
    )
    await state.set_state(JobFilterState.category)
    await callback.answer()


@router.callback_query(F.data.startswith("fcat:"), JobFilterState.category)
async def cb_filter_category(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    cat = callback.data.split(":")[1]
    await state.update_data(filter_category=cat)
    await state.set_state(None)
    await show_jobs_list(callback, i18n, db_user, state)
    await callback.answer()


@router.callback_query(F.data == "filter:keyword")
async def cb_filter_keyword_start(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    await callback.message.edit_text(i18n("filter_keyword_prompt"))
    await state.set_state(JobFilterState.keyword)
    await callback.answer()


@router.message(JobFilterState.keyword)
async def process_filter_keyword(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    kw = message.text.strip() if message.text else ""
    await state.update_data(filter_keyword=kw or None)
    await state.set_state(None)
    await show_jobs_list(message, i18n, db_user, state)


@router.callback_query(F.data == "filter:budget")
async def cb_filter_budget_start(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    await callback.message.edit_text(i18n("filter_budget_min"))
    await state.set_state(JobFilterState.budget_min)
    await callback.answer()


@router.message(JobFilterState.budget_min)
async def process_filter_budget_min(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    val = safe_float(message.text)
    await state.update_data(filter_budget_min=val)
    await message.answer(i18n("filter_budget_max"))
    await state.set_state(JobFilterState.budget_max)


@router.message(JobFilterState.budget_max)
async def process_filter_budget_max(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    val = safe_float(message.text)
    await state.update_data(filter_budget_max=val)
    await state.set_state(None)
    await show_jobs_list(message, i18n, db_user, state)


@router.callback_query(F.data == "clear_filters")
async def cb_clear_filters(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    await state.update_data(
        filter_category=None,
        filter_budget_min=None,
        filter_budget_max=None,
        filter_keyword=None,
    )
    await show_jobs_list(callback, i18n, db_user, state)
    await callback.answer()
