from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from database.connection import async_session_maker
from database.models import DealStatus, User
from services.escrow_service import (
    ReleaseResult,
    confirm_work,
    fund_escrow,
    fund_escrow_ton,
    get_deal,
    open_dispute,
    submit_work,
)
from services.notification_service import notify, notify_dispute_opened, notify_payment_released, notify_work_submitted
from services.user_service import get_user_by_telegram_id
from states import DisputeState, WorkSubmitState
from utils.helpers import deal_status_label
from utils.keyboards import (
    confirm_cancel_kb,
    deal_employer_confirm_kb,
    deal_freelancer_extended_kb,
    deal_freelancer_kb,
    dispute_guide_kb,
    escrow_currency_kb,
    rating_kb,
    skip_evidence_kb,
)

router = Router()


@router.callback_query(F.data.startswith("fund_escrow:"))
async def cb_fund_escrow(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    """Show currency choice (USD or TON) before funding escrow."""
    deal_id = int(callback.data.split(":")[1])
    async with async_session_maker() as session:
        deal = await get_deal(session, deal_id)
        if not deal:
            await callback.answer(i18n("error_not_found"))
            return
        if deal.employer_id != db_user.id:
            await callback.answer(i18n("error_permission"))
            return
        if deal.status != DealStatus.pending_payment:
            await callback.answer("Already processed.")
            return
        employer = await get_user_by_telegram_id(session, callback.from_user.id)
        usd_bal = employer.balance
        ton_bal = getattr(employer, "balance_ton", 0.0)
        deal_amount = deal.amount

    from payments.ton import get_ton_usd_rate, usd_to_ton
    await get_ton_usd_rate()
    ton_needed = usd_to_ton(deal_amount)

    has_usd = usd_bal >= deal_amount
    has_ton = ton_bal >= ton_needed

    if not has_usd and not has_ton:
        await callback.answer(
            i18n("insufficient_balance_both", usd=usd_bal, ton=ton_bal),
            show_alert=True,
        )
        return

    await callback.message.edit_text(
        i18n("escrow_choose_currency", amount=deal_amount, ton_needed=ton_needed, usd_bal=usd_bal, ton_bal=ton_bal),
        reply_markup=escrow_currency_kb(deal_id, deal_amount, ton_needed, i18n),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("fund_escrow_cur:"))
async def cb_fund_escrow_currency(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    """Execute escrow funding in the chosen currency."""
    _, currency, deal_id_str = callback.data.split(":")
    deal_id = int(deal_id_str)

    async with async_session_maker() as session:
        deal = await get_deal(session, deal_id)
        if not deal:
            await callback.answer(i18n("error_not_found"))
            return
        if deal.employer_id != db_user.id:
            await callback.answer(i18n("error_permission"))
            return
        if deal.status != DealStatus.pending_payment:
            await callback.answer("Already processed.")
            return

        employer = await get_user_by_telegram_id(session, callback.from_user.id)

        if currency == "ton":
            from payments.ton import get_ton_usd_rate
            rate = await get_ton_usd_rate()
            success = await fund_escrow_ton(session, deal, employer, rate)
            if not success:
                ton_bal = getattr(employer, "balance_ton", 0.0)
                await callback.answer(i18n("insufficient_balance_ton", available=ton_bal), show_alert=True)
                return
        else:
            success = await fund_escrow(session, deal, employer)
            if not success:
                await callback.answer(i18n("insufficient_balance", available=employer.balance), show_alert=True)
                return

        freelancer_tg_id = deal.freelancer.telegram_id
        job_title = deal.job.title
        deal_id_fresh = deal.id

    await callback.message.edit_text(i18n("escrow_funded"))
    await notify(
        callback.bot, freelancer_tg_id,
        i18n("application_accepted_freelancer_escrow", title=job_title),
        reply_markup=deal_freelancer_extended_kb(deal_id_fresh, i18n),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("submit_work:"))
async def cb_submit_work_start(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    deal_id = int(callback.data.split(":")[1])
    await state.update_data(submit_deal_id=deal_id)
    await callback.message.edit_text(i18n("enter_work_description"))
    await state.set_state(WorkSubmitState.description)
    await callback.answer()


@router.message(WorkSubmitState.description)
async def process_work_submit(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    description = message.text.strip() if message.text else ""
    if not description:
        await message.answer(i18n("error_invalid_input"))
        return

    data = await state.get_data()
    deal_id = data.get("submit_deal_id")
    await state.clear()

    async with async_session_maker() as session:
        deal = await get_deal(session, deal_id)
        if not deal or deal.freelancer_id != db_user.id:
            await message.answer(i18n("error_permission"))
            return
        await submit_work(session, deal, description)
        employer_tg_id = deal.employer.telegram_id
        employer_i18n_lang = deal.employer.language.value
        job_title = deal.job.title
        freelancer_name = db_user.full_name
        deal_id_fresh = deal.id

    from localization import get_i18n
    employer_i18n = get_i18n(employer_i18n_lang)

    await message.answer(i18n("work_submitted_freelancer"))
    await notify_work_submitted(
        message.bot,
        employer_tg_id,
        freelancer_name,
        job_title,
        description,
        deal_id_fresh,
        employer_i18n,
    )


@router.callback_query(F.data.startswith("confirm_work:"))
async def cb_confirm_work(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    deal_id = int(callback.data.split(":")[1])
    async with async_session_maker() as session:
        deal = await get_deal(session, deal_id)
        if not deal or deal.employer_id != db_user.id:
            await callback.answer(i18n("error_permission"))
            return
        if deal.status != DealStatus.work_submitted:
            await callback.answer("Not in submitted state.")
            return

        freelancer = deal.freelancer
        freelancer_tg_id = freelancer.telegram_id
        escrow_cur = getattr(deal, "escrow_currency", "usd")
        result: ReleaseResult = await confirm_work(session, deal, freelancer)
        deal_id_fresh = deal.id
        fl_lang = freelancer.language.value if hasattr(freelancer, "language") and freelancer.language else "en"

    from localization import get_i18n
    freelancer_i18n = get_i18n(fl_lang)

    if escrow_cur == "ton":
        confirmed_msg = i18n("work_confirmed_ton", amount=result.amount)
        amount_display = f"◎{result.amount:.4f} TON"
    else:
        confirmed_msg = i18n("work_confirmed", amount=result.amount)
        amount_display = result.amount

    await callback.message.edit_text(confirmed_msg)
    await notify_payment_released(
        callback.bot, freelancer_tg_id, amount_display,
        deal_id_fresh, freelancer_i18n, currency=escrow_cur,
    )
    await callback.answer()


# ── Dispute — employer side ────────────────────────────────────────────────

@router.callback_query(F.data.startswith("dispute:"))
async def cb_open_dispute_employer(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    deal_id = int(callback.data.split(":")[1])
    await state.update_data(dispute_deal_id=deal_id, dispute_opener="employer")
    await callback.message.edit_text(i18n("enter_dispute_reason"), reply_markup=dispute_guide_kb(i18n))
    await state.set_state(DisputeState.reason)
    await callback.answer()


# ── Dispute — freelancer side ──────────────────────────────────────────────

@router.callback_query(F.data.startswith("freelancer_dispute:"))
async def cb_open_dispute_freelancer(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    deal_id = int(callback.data.split(":")[1])
    await state.update_data(dispute_deal_id=deal_id, dispute_opener="freelancer")
    await callback.message.edit_text(i18n("enter_dispute_reason"), reply_markup=dispute_guide_kb(i18n))
    await state.set_state(DisputeState.reason)
    await callback.answer()


@router.message(DisputeState.reason)
async def process_dispute_reason(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    reason = message.text.strip() if message.text else ""
    if not reason:
        await message.answer(i18n("error_invalid_input"))
        return

    await state.update_data(dispute_reason=reason)
    await state.set_state(DisputeState.evidence)
    await message.answer(i18n("enter_dispute_evidence"), reply_markup=skip_evidence_kb(i18n))


@router.message(DisputeState.evidence)
async def process_dispute_evidence(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    from aiogram.types import ReplyKeyboardRemove
    from localization import get_i18n

    data = await state.get_data()
    deal_id = data.get("dispute_deal_id")
    opener = data.get("dispute_opener", "employer")
    reason = data.get("dispute_reason", "")

    evidence_file_id = None
    evidence_type = None
    if message.photo:
        evidence_file_id = message.photo[-1].file_id
        evidence_type = "photo"
    elif message.video:
        evidence_file_id = message.video.file_id
        evidence_type = "video"
    elif message.document:
        evidence_file_id = message.document.file_id
        evidence_type = "document"

    await state.clear()

    async with async_session_maker() as session:
        deal = await get_deal(session, deal_id)
        if not deal:
            await message.answer(i18n("error_not_found"), reply_markup=ReplyKeyboardRemove())
            return
        if opener == "employer" and deal.employer_id != db_user.id:
            await message.answer(i18n("error_permission"), reply_markup=ReplyKeyboardRemove())
            return
        if opener == "freelancer" and deal.freelancer_id != db_user.id:
            await message.answer(i18n("error_permission"), reply_markup=ReplyKeyboardRemove())
            return

        await open_dispute(session, deal, reason, opened_by_id=db_user.id)
        employer_tg_id = deal.employer.telegram_id
        freelancer_tg_id = deal.freelancer.telegram_id
        emp_lang = deal.employer.language.value if deal.employer.language else "en"
        fl_lang = deal.freelancer.language.value if deal.freelancer.language else "en"
        job_title = deal.job.title
        deal_id_fresh = deal.id

    await message.answer(i18n("dispute_opened"), reply_markup=ReplyKeyboardRemove())

    other_tg = freelancer_tg_id if opener == "employer" else employer_tg_id
    other_lang = fl_lang if opener == "employer" else emp_lang
    await notify(message.bot, other_tg, get_i18n(other_lang)("dispute_opened_other_party"))

    await notify_dispute_opened(
        message.bot, db_user.full_name, job_title, reason,
        deal_id_fresh, evidence_file_id, evidence_type,
    )
