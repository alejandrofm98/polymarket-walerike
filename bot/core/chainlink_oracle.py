"""Lazy Chainlink oracle reader with manual cache for tests and paper mode."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from bot.config.settings import Settings


CHAINLINK_LATEST_ROUND_ABI = [
    {
        "inputs": [],
        "name": "latestRoundData",
        "outputs": [
            {"internalType": "uint80", "name": "roundId", "type": "uint80"},
            {"internalType": "int256", "name": "answer", "type": "int256"},
            {"internalType": "uint256", "name": "startedAt", "type": "uint256"},
            {"internalType": "uint256", "name": "updatedAt", "type": "uint256"},
            {"internalType": "uint80", "name": "answeredInRound", "type": "uint80"},
        ],
        "stateMutability": "view",
        "type": "function",
    }
]


@dataclass(slots=True)
class OraclePrice:
    asset: str
    price: float
    round_id: int | None
    updated_at: float
    stale: bool


class ChainlinkOracle:
    def __init__(self, settings: Settings | None = None, stale_seconds: int | None = None) -> None:
        self.settings = settings or Settings.from_env()
        self.stale_seconds = stale_seconds or self.settings.chainlink_stale_seconds
        self._manual: dict[str, OraclePrice] = {}
        self._web3: Any | None = None

    def set_manual_price(
        self,
        asset: str,
        price: float,
        updated_at: float | None = None,
        round_id: int | None = None,
    ) -> OraclePrice:
        updated = updated_at or time.time()
        oracle_price = OraclePrice(
            asset=asset.upper(),
            price=price,
            round_id=round_id,
            updated_at=updated,
            stale=self._is_stale(updated),
        )
        self._manual[asset.upper()] = oracle_price
        return oracle_price

    def get_cached_price(self, asset: str) -> OraclePrice | None:
        cached = self._manual.get(asset.upper())
        if cached is None:
            return None
        return OraclePrice(cached.asset, cached.price, cached.round_id, cached.updated_at, self._is_stale(cached.updated_at))

    def read_price(self, asset: str, prefer_cache: bool = True) -> OraclePrice:
        asset = asset.upper()
        if prefer_cache:
            cached = self.get_cached_price(asset)
            if cached is not None:
                return cached

        address = self.settings.chainlink_feed_addresses.get(asset)
        if not address:
            raise RuntimeError(f"No Chainlink feed configured for {asset}")
        web3 = self._get_web3()
        contract = web3.eth.contract(address=web3.to_checksum_address(address), abi=CHAINLINK_LATEST_ROUND_ABI)
        round_id, answer, _started_at, updated_at, _answered_in_round = contract.functions.latestRoundData().call()
        price = float(answer) / 100_000_000.0
        return OraclePrice(asset=asset, price=price, round_id=int(round_id), updated_at=float(updated_at), stale=self._is_stale(float(updated_at)))

    async def read_price_async(self, asset: str, prefer_cache: bool = True) -> OraclePrice:
        return self.read_price(asset, prefer_cache=prefer_cache)

    def _get_web3(self) -> Any:
        if not self.settings.chainlink_rpc_url:
            raise RuntimeError("CHAINLINK_RPC_URL required for live Chainlink reads")
        if self._web3 is None:
            try:
                from web3 import Web3
            except ImportError as exc:
                raise RuntimeError("Live Chainlink reads require optional package web3") from exc
            self._web3 = Web3(Web3.HTTPProvider(self.settings.chainlink_rpc_url))
        return self._web3

    def _is_stale(self, updated_at: float) -> bool:
        return (time.time() - updated_at) > self.stale_seconds
