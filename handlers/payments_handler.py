from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from database.connection import async_session_maker
from database.models import Transaction, TransactionStatus, User
from payments.cryptobot import cryptobot
from payments.ton import get_ton_usd_rate, make_memo, send_ton, ton_client, usd_to_ton
from services.balance_service import (
    gross_deposit,
    net_withdrawal,
    request_ton_withdrawal,
    request_withdrawal,
    top_up_balance,
    top_up_ton_balance,
)
from services.user_service import get_user_by_telegram_id
from states import PaymentState
from utils.helpers import btn, safe_float
from utils.keyboards import (
    cryptobot_pay_kb,
    payment_method_kb,
    ton_pay_kb,
)

router = Router()


async def show_balance(target, i18n, db_user: User) -> None:
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from utils.keyboards import _ok, _nav, _bad
    builder = InlineKeyboardBuilder()
    builder.add(
        _ok(i18n("btn_top_up"),       "topup"),
        _nav(i18n("btn_withdraw"),     "withdraw_start"),
        _bad(i18n("btn_withdraw_ton"), "withdraw_ton_start"),
        _nav(i18n("btn_profile"),      "profile_back"),
    )
    builder.adjust(2, 1, 1)

    ton_bal = getattr(db_user, "balance_ton", 0.0)
    text = (
        f"{i18n('balance_header')}\n\n"
        f"{i18n('balance_usd', amount=db_user.balance)}\n"
        f"{i18n('balance_ton_display', amount=ton_bal)}"
    )
    if isinstance(target, Message):
        await target.answer(text, reply_markup=builder.as_markup())
    else:
        await target.message.edit_text(text, reply_markup=builder.as_markup())


@router.message(btn("btn_balance"))
async def handle_balance_menu(message: Message, i18n, db_user: User | None) -> None:
    if not db_user:
        return
    async with async_session_maker() as session:
        user = await get_user_by_telegram_id(session, message.from_user.id)
    await show_balance(message, i18n, user)


@router.callback_query(F.data == "balance")
async def cb_balance(callback: CallbackQuery, i18n, db_user: User | None) -> None:
    async with async_session_maker() as session:
        user = await get_user_by_telegram_id(session, callback.from_user.id)
    await show_balance(callback, i18n, user)
    await callback.answer()


# ── Top Up ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "topup")
async def cb_topup(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    await callback.message.edit_text(i18n("enter_top_up_amount"))
    await state.set_state(PaymentState.top_up_amount)
    await callback.answer()


@router.message(PaymentState.top_up_amount)
async def process_topup_amount(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    amount = safe_float(message.text)
    if amount is None or amount < 1 or amount > 10000:
        await message.answer(i18n("invalid_amount"))
        return
    charged = gross_deposit(amount)
    await state.update_data(topup_amount=amount, topup_charged=charged)
    fee_note = i18n("deposit_fee_note", charged=charged, amount=amount)
    await message.answer(fee_note, reply_markup=payment_method_kb(i18n, "topup"))
    await state.set_state(PaymentState.top_up_method)


@router.callback_query(F.data.startswith("pay_method:topup:"), PaymentState.top_up_method)
async def cb_topup_method(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    method = callback.data.split(":")[2]
    data = await state.get_data()
    amount = data["topup_amount"]

    if method == "cryptobot":
        charged = data.get("topup_charged", amount)
        invoice = await cryptobot.create_invoice(
            amount=charged,
            description=f"FreelanceBot top-up ${amount:.2f} (incl. fee)",
            payload=f"topup:{db_user.id}:{amount}",
        )
        if not invoice:
            await callback.message.edit_text(i18n("payment_failed"))
            await state.clear()
            await callback.answer()
            return

        await state.update_data(invoice_id=str(invoice["invoice_id"]))
        await callback.message.edit_text(
            i18n("invoice_created_cryptobot", amount=charged),
            reply_markup=cryptobot_pay_kb(invoice["pay_url"], i18n, str(invoice["invoice_id"])),
        )

    elif method == "ton":
        await get_ton_usd_rate()
        ton_amount = usd_to_ton(amount)
        memo = make_memo(db_user.id, amount)
        nano_tons = int(ton_amount * 1_000_000_000)
        await state.update_data(ton_memo=memo, ton_amount=ton_amount, usd_amount=amount)
        await callback.message.edit_text(
            i18n("invoice_created_ton", amount=ton_amount, address=ton_client.wallet),
            reply_markup=ton_pay_kb(
                i18n, f"check_ton:{memo}:{ton_amount}",
                wallet=ton_client.wallet, nano_tons=nano_tons, memo=memo,
            ),
        )

    await callback.answer()


@router.callback_query(F.data.startswith("check_pay:"))
async def cb_check_cryptobot(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    invoice_id = callback.data.split(":")[1]
    paid = await cryptobot.check_invoice_paid(invoice_id)

    if paid:
        data = await state.get_data()
        amount = data.get("topup_amount", 0)
        await state.clear()

        async with async_session_maker() as session:
            user = await get_user_by_telegram_id(session, callback.from_user.id)
            await top_up_balance(session, user, amount, invoice_id, "cryptobot")

        await callback.message.edit_text(i18n("payment_success", amount=amount))
    else:
        await callback.answer(i18n("payment_pending"), show_alert=True)


@router.callback_query(F.data.startswith("check_ton:"))
async def cb_check_ton(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    parts = callback.data.split(":")
    memo = parts[1]
    ton_amount = float(parts[2])  # TON amount locked at invoice creation

    paid = await ton_client.check_payment(memo, ton_amount)

    if paid:
        data = await state.get_data()
        credited_ton = data.get("ton_amount") or ton_amount
        await state.clear()

        async with async_session_maker() as session:
            user = await get_user_by_telegram_id(session, callback.from_user.id)
            await top_up_ton_balance(session, user, credited_ton, memo)

        await callback.message.edit_text(i18n("payment_success_ton", amount=credited_ton))
    else:
        await callback.answer(i18n("payment_pending"), show_alert=True)


# ── Withdraw USD ───────────────────────────────────────────────────────────

@router.callback_query(F.data == "withdraw_start")
async def cb_withdraw_start(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    async with async_session_maker() as session:
        user = await get_user_by_telegram_id(session, callback.from_user.id)

    if user.balance <= 0:
        await callback.answer(i18n("insufficient_balance", available=user.balance), show_alert=True)
        return

    await callback.message.edit_text(i18n("enter_withdraw_amount", available=user.balance))
    await state.set_state(PaymentState.withdraw_amount)
    await callback.answer()


@router.message(PaymentState.withdraw_amount)
async def process_withdraw_amount(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    amount = safe_float(message.text)
    if amount is None or amount <= 0:
        await message.answer(i18n("invalid_amount"))
        return

    async with async_session_maker() as session:
        user = await get_user_by_telegram_id(session, message.from_user.id)

    if user.balance < amount:
        await message.answer(i18n("insufficient_balance", available=user.balance))
        return

    net = net_withdrawal(amount)
    await state.update_data(withdraw_amount=amount, withdraw_net=net)
    fee_note = i18n("withdrawal_fee_note", net=net, amount=amount)
    await message.answer(fee_note, reply_markup=payment_method_kb(i18n, "withdraw"))
    await state.set_state(PaymentState.withdraw_method)


@router.callback_query(F.data.startswith("pay_method:withdraw:"), PaymentState.withdraw_method)
async def cb_withdraw_method(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    if not db_user:
        return
    method = callback.data.split(":")[2]
    await state.update_data(withdraw_method=method)

    if method == "ton":
        data = await state.get_data()
        net = data.get("withdraw_net", 0)
        await get_ton_usd_rate()
        ton_amount = usd_to_ton(net)
        await state.update_data(withdraw_ton_amount=ton_amount)
        await callback.message.edit_text(i18n("enter_ton_address", ton=ton_amount))
        await state.set_state(PaymentState.withdraw_address)
    else:
        data = await state.get_data()
        amount = data.get("withdraw_amount", 0)
        net = data.get("withdraw_net", amount)

        if net < 1.0:
            min_gross = round(1.0 / 0.95 + 0.005, 2)
            await callback.answer(i18n("withdrawal_cryptobot_min", min_gross=min_gross), show_alert=True)
            return

        await state.clear()

        async with async_session_maker() as session:
            user = await get_user_by_telegram_id(session, callback.from_user.id)
            tx = await request_withdrawal(session, user, amount, method, str(callback.from_user.id))

        if not tx:
            await callback.answer(i18n("insufficient_balance", available=db_user.balance), show_alert=True)
            return

        result = await cryptobot.transfer(
            user_id=callback.from_user.id,
            asset="USDT",
            amount=net,
            spend_id=f"withdraw_{tx.id}",
        )

        async with async_session_maker() as session:
            tx_db = await session.get(Transaction, tx.id)
            if result:
                tx_db.status = TransactionStatus.completed
            else:
                tx_db.status = TransactionStatus.failed
                user_db = await get_user_by_telegram_id(session, callback.from_user.id)
                user_db.balance += amount
            await session.commit()

        if result:
            await callback.message.edit_text(i18n("withdrawal_completed", amount=net))
        else:
            await callback.message.edit_text(i18n("withdrawal_failed"))

    await callback.answer()


@router.message(PaymentState.withdraw_address)
async def process_ton_withdraw_address(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    """USD → TON withdrawal: deducts USD balance, sends TON equivalent."""
    address = message.text.strip()
    data = await state.get_data()
    amount = data.get("withdraw_amount", 0)
    net = data.get("withdraw_net", amount)
    ton_amount = data.get("withdraw_ton_amount", usd_to_ton(net))
    await state.clear()

    async with async_session_maker() as session:
        user = await get_user_by_telegram_id(session, message.from_user.id)
        tx = await request_withdrawal(session, user, amount, "ton", address)

    if not tx:
        await message.answer(i18n("insufficient_balance", available=db_user.balance))
        return

    tx_hash = await send_ton(address, ton_amount)

    async with async_session_maker() as session:
        tx_db = await session.get(Transaction, tx.id)
        if tx_hash:
            tx_db.status = TransactionStatus.completed
        else:
            tx_db.status = TransactionStatus.failed
            user_db = await get_user_by_telegram_id(session, message.from_user.id)
            user_db.balance += amount
        await session.commit()

    if tx_hash:
        await message.answer(i18n("withdrawal_completed_ton", ton=ton_amount, usd=net))
    else:
        await message.answer(i18n("withdrawal_failed"))


# ── Withdraw TON (direct from TON balance) ─────────────────────────────────

@router.callback_query(F.data == "withdraw_ton_start")
async def cb_withdraw_ton_start(callback: CallbackQuery, state: FSMContext, i18n, db_user: User | None) -> None:
    async with async_session_maker() as session:
        user = await get_user_by_telegram_id(session, callback.from_user.id)
    ton_bal = getattr(user, "balance_ton", 0.0)

    if ton_bal <= 0:
        await callback.answer(i18n("insufficient_balance_ton", available=0.0), show_alert=True)
        return

    await callback.message.edit_text(i18n("enter_withdraw_ton_amount", available=ton_bal))
    await state.set_state(PaymentState.withdraw_ton_amount)
    await callback.answer()


@router.message(PaymentState.withdraw_ton_amount)
async def process_withdraw_ton_amount(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    amount = safe_float(message.text)
    if amount is None or amount <= 0:
        await message.answer(i18n("invalid_amount"))
        return

    async with async_session_maker() as session:
        user = await get_user_by_telegram_id(session, message.from_user.id)
    ton_bal = getattr(user, "balance_ton", 0.0)

    if ton_bal < amount:
        await message.answer(i18n("insufficient_balance_ton", available=ton_bal))
        return

    await state.update_data(withdraw_ton_direct=amount)
    await message.answer(i18n("enter_ton_address_withdraw", ton=amount))
    await state.set_state(PaymentState.withdraw_ton_address)


@router.message(PaymentState.withdraw_ton_address)
async def process_direct_ton_withdraw(message: Message, state: FSMContext, i18n, db_user: User | None) -> None:
    address = message.text.strip()
    data = await state.get_data()
    ton_amount = data.get("withdraw_ton_direct", 0)
    await state.clear()

    async with async_session_maker() as session:
        user = await get_user_by_telegram_id(session, message.from_user.id)
        tx = await request_ton_withdrawal(session, user, ton_amount, address)

    if not tx:
        await message.answer(i18n("insufficient_balance_ton", available=0.0))
        return

    tx_hash = await send_ton(address, ton_amount)

    async with async_session_maker() as session:
        tx_db = await session.get(Transaction, tx.id)
        if tx_hash:
            tx_db.status = TransactionStatus.completed
        else:
            tx_db.status = TransactionStatus.failed
            user_db = await get_user_by_telegram_id(session, message.from_user.id)
            user_db.balance_ton += ton_amount
        await session.commit()

    if tx_hash:
        await message.answer(i18n("withdrawal_ton_completed", ton=ton_amount))
    else:
        await message.answer(i18n("withdrawal_failed"))
