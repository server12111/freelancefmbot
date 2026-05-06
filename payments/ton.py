import hashlib
import time

import aiohttp
from loguru import logger

from config import settings

# In-memory cache: refreshed every 5 minutes from CoinGecko
_rate_cache: dict = {"rate": 5.0, "ts": 0.0}


async def get_ton_usd_rate() -> float:
    """Return current TON price in USD, refreshed every 5 minutes."""
    if time.time() - _rate_cache["ts"] < 300:
        return _rate_cache["rate"]
    try:
        async with aiohttp.ClientSession() as session:
            resp = await session.get(
                "https://api.coingecko.com/api/v3/simple/price"
                "?ids=the-open-network&vs_currencies=usd",
                timeout=aiohttp.ClientTimeout(total=5),
            )
            data = await resp.json()
            rate = float(data["the-open-network"]["usd"])
            _rate_cache.update({"rate": rate, "ts": time.time()})
            logger.info(f"TON rate updated: 1 TON = ${rate:.4f}")
    except Exception as e:
        logger.warning(f"TON rate fetch failed, using cached {_rate_cache['rate']}: {e}")
    return _rate_cache["rate"]


def usd_to_ton(usd: float) -> float:
    """Convert USD to TON using the cached rate."""
    rate = _rate_cache["rate"]
    return round(usd / rate, 4)


def ton_to_usd(ton: float) -> float:
    rate = _rate_cache["rate"]
    return round(ton * rate, 2)


def make_memo(user_id: int, amount: float) -> str:
    """Deterministic memo to identify a payment."""
    raw = f"{user_id}:{amount}:{int(time.time() // 3600)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16].upper()


class TonCenterClient:
    def __init__(self):
        self.api_key = settings.TON_API_KEY
        self.base_url = settings.TON_CENTER_URL
        self.wallet = settings.TON_WALLET_ADDRESS

    async def _get(self, endpoint: str, params: dict | None = None) -> dict | None:
        url = f"{self.base_url}/{endpoint}"
        headers = {"X-API-Key": self.api_key}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as resp:
                if resp.status != 200:
                    logger.error(f"TON API error {resp.status}")
                    return None
                return await resp.json()

    async def get_transactions(self, address: str, limit: int = 20) -> list[dict]:
        result = await self._get(
            "getTransactions",
            {"address": address, "limit": limit},
        )
        if not result or not result.get("ok"):
            return []
        return result.get("result", [])

    async def check_payment(self, memo: str, min_ton: float) -> bool:
        """Check if a transaction with the memo comment arrived in the last hour."""
        txs = await self.get_transactions(self.wallet)
        for tx in txs:
            msg = tx.get("in_msg", {})
            comment = msg.get("message", "")
            value_nano = int(msg.get("value", 0))
            value_ton = value_nano / 1e9
            if comment == memo and value_ton >= min_ton * 0.99:  # 1% tolerance
                return True
        return False

    async def get_seqno(self, address: str) -> int:
        """Fetch current wallet seqno via getWalletInformation."""
        result = await self._get("getWalletInformation", {"address": address})
        try:
            if result and result.get("ok"):
                return int(result["result"].get("seqno", 0))
        except Exception:
            pass
        return 0

    async def send_boc(self, boc: str) -> str | None:
        """Broadcast a base64-encoded BOC and return message hash on success."""
        url = f"{self.base_url}/sendBoc"
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                params={"api_key": self.api_key},
                json={"boc": boc},
            ) as resp:
                data = await resp.json()
                if data.get("ok"):
                    return data.get("result")
                logger.error(f"sendBoc failed: {data}")
        return None


ton_client = TonCenterClient()


async def send_ton(recipient: str, amount_ton: float) -> str | None:
    """Send TON via WalletV5R1 (W5). Handles uninitialized wallet (deploy+send in one tx)."""
    from pytoniq import WalletV5R1, LiteBalancer
    from pytoniq_core import Address

    mnemonics = settings.TON_MNEMONIC.split()
    if len(mnemonics) != 24:
        logger.error("TON_MNEMONIC is not set or invalid")
        return None

    provider = None
    try:
        provider = LiteBalancer.from_mainnet_config(1)
        await provider.start_up()

        wallet = await WalletV5R1.from_mnemonic(
            provider=provider,
            mnemonics=mnemonics,
            network_global_id=-239,
        )

        # Try on-chain seqno; if wallet is uninitialized (exit code -256) use 0
        try:
            seqno = await wallet.get_seqno()
            initialized = True
        except Exception:
            seqno = wallet.seqno  # 0 for new wallet
            initialized = False

        dest = Address(recipient)
        msg = wallet.create_wallet_internal_message(
            destination=dest,
            value=int(amount_ton * 1_000_000_000),
            body="FreelanceBot withdrawal",
        )

        transfer_cell = wallet.raw_create_transfer_msg(
            private_key=wallet.private_key,
            seqno=seqno,
            wallet_id=wallet.wallet_id,
            messages=[msg],
        )

        if initialized:
            await wallet.send_external(body=transfer_cell)
        else:
            # First-ever tx: deploy contract + send in one message
            await wallet.send_external(body=transfer_cell, state_init=wallet.state_init)

        logger.info(f"TON sent: {amount_ton} TON to {recipient} (seqno={seqno}, init={not initialized})")
        return "sent"
    except Exception as e:
        logger.error(f"send_ton failed: {e}")
        return None
    finally:
        if provider:
            try:
                await provider.close_all()
            except Exception:
                pass
