import aiohttp
from loguru import logger

from config import settings


class CryptoBotClient:
    def __init__(self):
        self.token = settings.CRYPTOBOT_TOKEN
        self.base_url = settings.CRYPTOBOT_API_URL
        self.headers = {"Crypto-Pay-API-Token": self.token}

    async def _request(self, method: str, endpoint: str, **kwargs) -> dict | None:
        url = f"{self.base_url}/{endpoint}"
        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, headers=self.headers, **kwargs) as resp:
                if resp.status != 200:
                    logger.error(f"CryptoBot error {resp.status}: {await resp.text()}")
                    return None
                data = await resp.json()
                if not data.get("ok"):
                    logger.error(f"CryptoBot API error: {data}")
                    return None
                return data.get("result")

    async def create_invoice(
        self,
        amount: float,
        asset: str = "USDT",
        description: str = "FreelanceBot top-up",
        payload: str = "",
        expires_in: int = 3600,
    ) -> dict | None:
        """Create a payment invoice. Returns invoice dict with pay_url and invoice_id."""
        return await self._request(
            "POST",
            "createInvoice",
            json={
                "asset": asset,
                "amount": str(amount),
                "description": description,
                "payload": payload,
                "expires_in": expires_in,
            },
        )

    async def get_invoice(self, invoice_id: int) -> dict | None:
        return await self._request("GET", "getInvoices", params={"invoice_ids": str(invoice_id)})

    async def check_invoice_paid(self, invoice_id: str) -> bool:
        result = await self._request(
            "GET", "getInvoices", params={"invoice_ids": invoice_id}
        )
        if not result:
            return False
        items = result.get("items", [])
        return any(item.get("status") == "paid" for item in items)

    async def transfer(self, user_id: int, asset: str, amount: float, spend_id: str) -> dict | None:
        """Send funds to a Telegram user via CryptoBot."""
        return await self._request(
            "POST",
            "transfer",
            json={
                "user_id": user_id,
                "asset": asset,
                "amount": str(amount),
                "spend_id": spend_id,
            },
        )


cryptobot = CryptoBotClient()
