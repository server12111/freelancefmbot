from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Transaction, TransactionStatus, TransactionType, User

DEPOSIT_FEE_PCT = 0.03    # 3% processing fee on CryptoBot top-ups
WITHDRAWAL_FEE_PCT = 0.05  # 5% fee on withdrawals


def gross_deposit(net_amount: float) -> float:
    """Amount user must pay via CryptoBot to receive net_amount credited."""
    return round(net_amount * (1 + DEPOSIT_FEE_PCT), 2)


def net_withdrawal(gross_amount: float) -> float:
    """Amount user actually receives after withdrawal fee."""
    return round(gross_amount * (1 - WITHDRAWAL_FEE_PCT), 2)


async def top_up_balance(
    session: AsyncSession,
    user: User,
    amount: float,
    payment_id: str,
    method: str = "cryptobot",
) -> None:
    user.balance += amount
    tx = Transaction(
        user_id=user.id,
        type=TransactionType.top_up,
        amount=amount,
        status=TransactionStatus.completed,
        payment_id=payment_id,
        description=f"Top up via {method}",
    )
    session.add(tx)
    await session.commit()


async def top_up_ton_balance(
    session: AsyncSession,
    user: User,
    ton_amount: float,
    payment_id: str,
) -> None:
    user.balance_ton += ton_amount
    tx = Transaction(
        user_id=user.id,
        type=TransactionType.top_up,
        amount=ton_amount,
        status=TransactionStatus.completed,
        payment_id=payment_id,
        description=f"TON top up: {ton_amount:.6f} TON",
    )
    session.add(tx)
    await session.commit()


async def request_ton_withdrawal(
    session: AsyncSession,
    user: User,
    ton_amount: float,
    address: str,
) -> Transaction | None:
    if user.balance_ton < ton_amount:
        return None
    user.balance_ton -= ton_amount
    tx = Transaction(
        user_id=user.id,
        type=TransactionType.withdrawal,
        amount=ton_amount,
        status=TransactionStatus.pending,
        description=f"TON withdrawal to {address}",
    )
    session.add(tx)
    await session.commit()
    await session.refresh(tx)
    return tx


async def request_withdrawal(
    session: AsyncSession,
    user: User,
    amount: float,
    method: str,
    address: str,
) -> Transaction | None:
    if user.balance < amount:
        return None

    user.balance -= amount
    tx = Transaction(
        user_id=user.id,
        type=TransactionType.withdrawal,
        amount=amount,
        status=TransactionStatus.pending,
        description=f"Withdrawal via {method} to {address}",
    )
    session.add(tx)
    await session.commit()
    await session.refresh(tx)
    return tx
