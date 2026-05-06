from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from database.connection import async_session_maker
from database.models import User
from services.invitation_service import (
    accept_invitation,
    already_invited,
    decline_invitation,
    get_invitation,
    get_pending_invitations,
    send_invitation,
)
from services.notification_service import notify_invitation
from services.user_service import get_user_by_id, get_user_by_telegram_id
from states import InvitationState
from utils.helpers import btn
from utils.keyboards import invitation_kb, my_invitations_kb

router = Router()


# ── Employer: open invite dialog from job detail ───────────────────────────

@router.callback_query(F.data.startswith("job_invite:"))
async def cb_job_invite(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    if not db_user:
        await callback.answer(i18n("error_permission"))
        return
    job_id = int(callback.data.split(":")[1])
    await state.update_data(invite_job_id=job_id)
    await callback.message.edit_text(i18n("invitation_enter_freelancer_id"))
    await state.set_state(InvitationState.select_freelancer)
    await callback.answer()


@router.message(InvitationState.select_freelancer)
async def process_invite_freelancer(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    text = message.text.strip() if message.text else ""
    try:
        tg_id = int(text)
    except ValueError:
        await message.answer(i18n("error_invalid_input"))
        return

    async with async_session_maker() as session:
        freelancer = await get_user_by_telegram_id(session, tg_id)
        if not freelancer:
            await message.answer(i18n("invitation_freelancer_not_found"))
            return

        data = await state.get_data()
        job_id = data.get("invite_job_id")

        if await already_invited(session, db_user.id, freelancer.id, job_id):
            await message.answer(i18n("invitation_already_sent"))
            return

    await state.update_data(invite_freelancer_id=freelancer.id, invite_freelancer_name=freelancer.full_name)
    await message.answer(i18n("invitation_enter_message"))
    await state.set_state(InvitationState.message)


@router.message(InvitationState.message)
async def process_invite_message(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    invite_msg = message.text.strip() if message.text else None
    await state.update_data(invite_message=invite_msg)
    data = await state.get_data()

    await message.answer(
        i18n(
            "invitation_confirm",
            freelancer=data["invite_freelancer_name"],
            message=invite_msg or "—",
        ),
        reply_markup=_confirm_invite_kb(i18n),
    )
    await state.set_state(InvitationState.confirm)


def _confirm_invite_kb(i18n):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text=i18n("btn_confirm"), callback_data="inv_do_send")
    builder.button(text=i18n("btn_cancel"),  callback_data="inv_cancel")
    builder.adjust(2)
    return builder.as_markup()


@router.callback_query(F.data == "inv_do_send", InvitationState.confirm)
async def cb_inv_do_send(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    if not db_user:
        await callback.answer()
        return
    data = await state.get_data()
    job_id = data.get("invite_job_id")
    freelancer_id = data.get("invite_freelancer_id")
    invite_msg = data.get("invite_message")
    await state.clear()

    async with async_session_maker() as session:
        employer = await get_user_by_telegram_id(session, callback.from_user.id)
        freelancer = await get_user_by_id(session, freelancer_id)
        from services.job_service import get_job
        job = await get_job(session, job_id)
        if not employer or not freelancer or not job:
            await callback.answer(i18n("error_not_found"))
            return

        inv = await send_invitation(session, employer, freelancer, job, invite_msg)
        inv_id = inv.id
        freelancer_tg = freelancer.telegram_id
        notif_enabled = bool(freelancer.notifications_enabled)
        lang = freelancer.language.value if freelancer.language else "en"

    from localization import get_i18n
    fl_i18n = get_i18n(lang)
    await notify_invitation(
        callback.bot,
        freelancer_tg,
        inv_id,
        db_user.full_name,
        job.title,
        job.budget,
        invite_msg,
        fl_i18n,
        notif_enabled,
    )
    await callback.message.edit_text(i18n("invitation_sent"))
    await callback.answer()


@router.callback_query(F.data == "inv_cancel")
async def cb_inv_cancel(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    await state.clear()
    await callback.message.edit_text(i18n("main_menu"))
    await callback.answer()


# ── Freelancer: view invitations ───────────────────────────────────────────

@router.message(btn("btn_invitations"))
async def handle_my_invitations(message: Message, i18n, db_user: User | None) -> None:
    if not db_user:
        return
    async with async_session_maker() as session:
        invs = await get_pending_invitations(session, db_user.id)

    if not invs:
        await message.answer(i18n("no_invitations"))
        return

    await message.answer(i18n("my_invitations"), reply_markup=my_invitations_kb(invs, i18n))


@router.callback_query(F.data.startswith("inv_view:"))
async def cb_inv_view(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    inv_id = int(callback.data.split(":")[1])
    async with async_session_maker() as session:
        inv = await get_invitation(session, inv_id)

    if not inv:
        await callback.answer(i18n("error_not_found"))
        return

    text = i18n(
        "invitation_item",
        employer=inv.employer.full_name,
        title=inv.job.title,
        budget=inv.job.budget,
        message=inv.message or "—",
    )
    await callback.message.edit_text(text, reply_markup=invitation_kb(inv_id, i18n))
    await callback.answer()


@router.callback_query(F.data.startswith("inv_accept:"))
async def cb_inv_accept(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    inv_id = int(callback.data.split(":")[1])
    async with async_session_maker() as session:
        inv = await get_invitation(session, inv_id)
        if not inv or inv.freelancer_id != db_user.id:
            await callback.answer(i18n("error_permission"))
            return
        await accept_invitation(session, inv)

    await callback.message.edit_text(i18n("invitation_accepted"))
    await callback.answer()


@router.callback_query(F.data.startswith("inv_decline:"))
async def cb_inv_decline(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    inv_id = int(callback.data.split(":")[1])
    async with async_session_maker() as session:
        inv = await get_invitation(session, inv_id)
        if not inv or inv.freelancer_id != db_user.id:
            await callback.answer(i18n("error_permission"))
            return
        await decline_invitation(session, inv)

    await callback.message.edit_text(i18n("invitation_declined"))
    await callback.answer()
