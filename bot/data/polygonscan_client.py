from __future__ import annotations

import logging

import httpx

logger = logging.getLogger("walerike.polygonscan")

PUSD_CONTRACT = "0x9Cb2f26A23b8d89973F08c957C4d7cdf75CD341c"
PUSD_DECIMALS = 6
POLYGONSCAN_API_URL = "https://api.polygonscan.com/api"


class PolygonScanClient:
    def __init__(self, api_key: str | None, timeout: float = 10.0) -> None:
        self.api_key = api_key
        self.timeout = timeout

    async def pusd_balance(self, wallet: str) -> float | None:
        if not self.api_key:
            logger.debug("no POLYGONSCAN_API_KEY, skipping PUSD balance fetch")
            return None

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    POLYGONSCAN_API_URL,
                    params={
                        "module": "account",
                        "action": "tokenbalance",
                        "contractaddress": PUSD_CONTRACT,
                        "address": wallet,
                        "tag": "latest",
                        "apikey": self.api_key,
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPStatusError as exc:
            logger.error(f"HTTP error fetching PUSD balance for {wallet}: {exc}")
            return None
        except httpx.RequestError as exc:
            logger.error(f"Network error fetching PUSD balance for {wallet}: {exc}")
            return None

        if not isinstance(payload, dict):
            logger.warning(f"polygonscan unexpected response type for {wallet}: {type(payload)}")
            return None

        if payload.get("status") != "1":
            logger.warning(f"polygonscan error for {wallet}: {payload.get('message', 'unknown')}")
            return None

        raw_balance = payload.get("result", "0")
        try:
            balance_wei = int(raw_balance)
            return balance_wei / (10**PUSD_DECIMALS)
        except (ValueError, TypeError) as exc:
            logger.error(f"cannot parse PUSD balance for {wallet}: {raw_balance!r} -> {exc}")
            return None