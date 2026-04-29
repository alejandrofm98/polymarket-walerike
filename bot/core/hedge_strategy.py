"""Signal-only hedge strategy; execution and hard risk checks live elsewhere."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import time


class HedgeMode(StrEnum):
    ARBITRAGE = "ARBITRAGE"
    COPYTRADE = "COPYTRADE"
    HEDGE_BIASED_UP = "HEDGE_BIASED_UP"
    HEDGE_BIASED_DOWN = "HEDGE_BIASED_DOWN"
    HEDGE_NEUTRAL = "HEDGE_NEUTRAL"


@dataclass(slots=True)
class HedgeConfig:
    arbitrage_yes_no_sum: float = 0.98
    entry_threshold: float = 0.499
    max_sum_avg: float = 0.98
    max_buys_per_side: int = 4
    
    reversal_delta: float = 0.02
    depth_buy_discount_percent: float = 0.05
    second_side_buffer: float = 0.01
    second_side_time_threshold_ms: float = 200.0
    dynamic_threshold_boost: float = 0.04
    min_liquidity: float = 10.0
    max_oracle_discrepancy_pct: float = 1.0
    momentum_threshold_pct: float = 0.25
    hedge_bias_fraction: float = 0.65
    taker_fee_rate: float = 0.072


@dataclass(slots=True)
class MarketSnapshot:
    market_id: str
    asset: str
    timeframe: str
    yes_token_id: str
    no_token_id: str
    yes_price: float
    no_price: float
    yes_liquidity: float
    no_liquidity: float
    spot_price: float
    oracle_price: float
    timestamp: float
    market_slug: str | None = None
    end_date: str | None = None
    price_to_beat: float | None = None
    window_start_timestamp: int | None = None


@dataclass(slots=True)
class HedgeSignal:
    mode: HedgeMode
    yes_size: float
    no_size: float
    expected_margin: float
    reasons: list[str] = field(default_factory=list)
    target_side: str | None = None
    strategy_name: str | None = None
    order_type: str = "TAKER"
    post_only: bool = False
    limit_price: float | None = None


@dataclass(slots=True)
class CopytradeRow:
    qty_yes: float = 0.0
    qty_no: float = 0.0
    cost_yes: float = 0.0
    cost_no: float = 0.0
    buy_count_yes: int = 0
    buy_count_no: int = 0
    last_buy_side: str | None = None


@dataclass(slots=True)
class TrackingState:
    tracking_side: str | None = None
    temp_price: float = 0.0
    initialized: bool = False
    first_buy_of_hedge: bool = True
    second_side_timer_started_at: float | None = None


class HedgeStrategy:
    def __init__(self, config: HedgeConfig | None = None) -> None:
        self.config = config or HedgeConfig()
        self._rows: dict[str, CopytradeRow] = {}
        self._tracking: dict[str, TrackingState] = {}

    def evaluate(self, snapshot: MarketSnapshot, capital_per_trade: float, momentum_pct: float) -> HedgeSignal:
        return self._evaluate_copytrade(snapshot, capital_per_trade)

    def record_buy(self, snapshot: MarketSnapshot, side: str, price: float, size: float) -> None:
        key = self._key(snapshot)
        row = self._rows.setdefault(key, CopytradeRow())
        side = side.upper()
        effective_price = price + self.fee_per_share(price, self.config.taker_fee_rate)
        if side == "YES":
            row.qty_yes += size
            row.cost_yes += effective_price * size
            row.buy_count_yes += 1
        else:
            row.qty_no += size
            row.cost_no += effective_price * size
            row.buy_count_no += 1
        row.last_buy_side = side

        tracking = self._tracking.setdefault(key, TrackingState())
        opposite = "NO" if side == "YES" else "YES"
        dynamic_threshold = max(0.0, min(1.0, 1.0 - price + self.config.dynamic_threshold_boost))
        tracking.tracking_side = opposite
        tracking.temp_price = dynamic_threshold
        tracking.initialized = True
        tracking.first_buy_of_hedge = False
        tracking.second_side_timer_started_at = None

    def state_snapshot(self, snapshot: MarketSnapshot) -> dict[str, float | int | str | None]:
        key = self._key(snapshot)
        row = self._rows.get(key, CopytradeRow())
        tracking = self._tracking.get(key, TrackingState())
        return {
            "key": key,
            "qty_yes": row.qty_yes,
            "qty_no": row.qty_no,
            "avg_yes": self._avg(row.cost_yes, row.qty_yes),
            "avg_no": self._avg(row.cost_no, row.qty_no),
            "sum_avg": self._avg(row.cost_yes, row.qty_yes) + self._avg(row.cost_no, row.qty_no),
            "net_sum_avg": self._avg(row.cost_yes, row.qty_yes) + self._avg(row.cost_no, row.qty_no),
            "buy_count_yes": row.buy_count_yes,
            "buy_count_no": row.buy_count_no,
            "last_buy_side": row.last_buy_side,
            "tracking_side": tracking.tracking_side,
            "tracking_price": tracking.temp_price,
        }

    def _evaluate_copytrade(self, snapshot: MarketSnapshot, capital_per_trade: float = 10.0) -> HedgeSignal:
        reasons: list[str] = []
        if snapshot.yes_liquidity < self.config.min_liquidity or snapshot.no_liquidity < self.config.min_liquidity:
            reasons.append("liquidity below threshold")

        oracle_discrepancy = self._oracle_discrepancy_pct(snapshot.spot_price, snapshot.oracle_price)
        if oracle_discrepancy > self.config.max_oracle_discrepancy_pct:
            reasons.append("oracle discrepancy above threshold")

        key = self._key(snapshot)
        row = self._rows.setdefault(key, CopytradeRow())
        tracking = self._tracking.setdefault(key, TrackingState())
        yes_no_sum = (
            snapshot.yes_price
            + self.fee_per_share(snapshot.yes_price, self.config.taker_fee_rate)
            + snapshot.no_price
            + self.fee_per_share(snapshot.no_price, self.config.taker_fee_rate)
        )
        expected_margin = max(0.0, self.config.max_sum_avg - yes_no_sum)

        if row.buy_count_yes >= self.config.max_buys_per_side and row.buy_count_no >= self.config.max_buys_per_side:
            reasons.append("hedge complete")
            return HedgeSignal(HedgeMode.COPYTRADE, 0.0, 0.0, expected_margin, reasons)

        if snapshot.yes_liquidity < self.config.min_liquidity or snapshot.no_liquidity < self.config.min_liquidity:
            return HedgeSignal(HedgeMode.COPYTRADE, 0.0, 0.0, expected_margin, reasons)

        if row.buy_count_yes >= self.config.max_buys_per_side or row.buy_count_no >= self.config.max_buys_per_side:
            reasons.append("strict hedge pair max buys reached")
            return HedgeSignal(HedgeMode.COPYTRADE, 0.0, 0.0, expected_margin, reasons)

        effective_yes = snapshot.yes_price + self.fee_per_share(snapshot.yes_price, self.config.taker_fee_rate)
        effective_no = snapshot.no_price + self.fee_per_share(snapshot.no_price, self.config.taker_fee_rate)
        pair_cost = effective_yes + effective_no
        if pair_cost > self.config.max_sum_avg:
            reasons.append(f"strict hedge pair guard sum={pair_cost:.4f} max={self.config.max_sum_avg:.4f} includes_fee")
            return HedgeSignal(HedgeMode.COPYTRADE, 0.0, 0.0, expected_margin, reasons)

        size = min(capital_per_trade / pair_cost if pair_cost > 0 else 0.0, snapshot.yes_liquidity, snapshot.no_liquidity)
        if size <= 0.0:
            reasons.append("strict hedge pair size unavailable")
            return HedgeSignal(HedgeMode.COPYTRADE, 0.0, 0.0, expected_margin, reasons)
        reasons.append("strict hedge pair trigger")
        return HedgeSignal(HedgeMode.COPYTRADE, size, size, expected_margin, reasons, target_side="BOTH")

        if not tracking.initialized or tracking.tracking_side is None:
            yes_below = snapshot.yes_price <= self.config.entry_threshold
            no_below = snapshot.no_price <= self.config.entry_threshold
            if not yes_below and not no_below:
                reasons.append("waiting for entry threshold")
                return HedgeSignal(HedgeMode.COPYTRADE, 0.0, 0.0, expected_margin, reasons)
            if row.last_buy_side == "YES" and yes_below:
                side = "YES"
            elif row.last_buy_side == "NO" and no_below:
                side = "NO"
            elif yes_below:
                side = "YES"
            else:
                side = "NO"
            tracking.tracking_side = side
            tracking.temp_price = snapshot.yes_price if side == "YES" else snapshot.no_price
            tracking.initialized = True
            tracking.first_buy_of_hedge = True
            reasons.append(f"tracking {side} below entry threshold")
            return HedgeSignal(HedgeMode.COPYTRADE, 0.0, 0.0, expected_margin, reasons, target_side=side)

        side = tracking.tracking_side
        price = snapshot.yes_price if side == "YES" else snapshot.no_price
        liquidity = snapshot.yes_liquidity if side == "YES" else snapshot.no_liquidity
        buy_count = row.buy_count_yes if side == "YES" else row.buy_count_no
        if liquidity < self.config.min_liquidity:
            return HedgeSignal(HedgeMode.COPYTRADE, 0.0, 0.0, expected_margin, reasons, target_side=side)
        if buy_count >= self.config.max_buys_per_side:
            opposite = "NO" if side == "YES" else "YES"
            opposite_count = row.buy_count_no if opposite == "NO" else row.buy_count_yes
            if opposite_count >= self.config.max_buys_per_side:
                reasons.append("hedge complete")
                return HedgeSignal(HedgeMode.COPYTRADE, 0.0, 0.0, expected_margin, reasons)
            tracking.tracking_side = opposite
            tracking.temp_price = snapshot.no_price if opposite == "NO" else snapshot.yes_price
            tracking.second_side_timer_started_at = None
            reasons.append(f"{side} max buys reached; switching to {opposite}")
            return HedgeSignal(HedgeMode.COPYTRADE, 0.0, 0.0, expected_margin, reasons, target_side=opposite)

        if not tracking.first_buy_of_hedge and row.last_buy_side == side:
            opposite = "NO" if side == "YES" else "YES"
            tracking.tracking_side = opposite
            tracking.temp_price = snapshot.no_price if opposite == "NO" else snapshot.yes_price
            tracking.second_side_timer_started_at = None
            side = opposite
            price = snapshot.yes_price if side == "YES" else snapshot.no_price
            liquidity = snapshot.yes_liquidity if side == "YES" else snapshot.no_liquidity
            buy_count = row.buy_count_yes if side == "YES" else row.buy_count_no
            reasons.append(f"strict alternation executing {opposite}")

        if price < tracking.temp_price:
            tracking.temp_price = price
            tracking.second_side_timer_started_at = None
            reasons.append(f"new low for {side}")
            return HedgeSignal(HedgeMode.COPYTRADE, 0.0, 0.0, expected_margin, reasons, target_side=side)

        effective_price = price + self.fee_per_share(price, self.config.taker_fee_rate)
        other_avg = self._avg(row.cost_no, row.qty_no) if side == "YES" else self._avg(row.cost_yes, row.qty_yes)
        max_acceptable_price = self.config.max_sum_avg - other_avg
        shares_for_capital = capital_per_trade / effective_price if effective_price > 0 else 0.0
        projected_sum_avg = self._projected_sum_avg(row, side, effective_price, shares_for_capital)
        if effective_price > max_acceptable_price or projected_sum_avg > self.config.max_sum_avg:
            reasons.append(f"sumAvg guard price={effective_price:.4f} max={max_acceptable_price:.4f} projected={projected_sum_avg:.4f} includes_fee")
            return HedgeSignal(HedgeMode.COPYTRADE, 0.0, 0.0, expected_margin, reasons, target_side=side)

        now_ms = time.time() * 1000.0
        is_second_side = row.last_buy_side is not None and row.last_buy_side != side
        time_based = False
        if is_second_side:
            if price > tracking.temp_price:
                tracking.second_side_timer_started_at = None
            else:
                if tracking.second_side_timer_started_at is None:
                    tracking.second_side_timer_started_at = now_ms
                time_based = now_ms - tracking.second_side_timer_started_at >= self.config.second_side_time_threshold_ms

        deep_discount = price <= tracking.temp_price * (1.0 - self.config.depth_buy_discount_percent)
        reversal = price > tracking.temp_price + self.config.reversal_delta
        immediate_second_side = is_second_side and price <= tracking.temp_price - self.config.second_side_buffer
        if time_based:
            reasons.append("second side time threshold")
        elif immediate_second_side:
            reasons.append("second side dynamic threshold")
        elif deep_discount:
            reasons.append("depth discount trigger")
        elif reversal:
            reasons.append("reversal trigger")
        else:
            reasons.append("waiting for trigger")
            return HedgeSignal(HedgeMode.COPYTRADE, 0.0, 0.0, expected_margin, reasons, target_side=side)

        size = min(shares_for_capital, liquidity)
        yes_size = size if side == "YES" else 0.0
        no_size = size if side == "NO" else 0.0
        return HedgeSignal(HedgeMode.COPYTRADE, yes_size, no_size, expected_margin, reasons, target_side=side)

    @staticmethod
    def _key(snapshot: MarketSnapshot) -> str:
        return snapshot.market_slug or snapshot.market_id

    @staticmethod
    def _avg(cost: float, qty: float) -> float:
        return cost / qty if qty > 0 else 0.0

    @classmethod
    def _projected_sum_avg(cls, row: CopytradeRow, side: str, price: float, size: float) -> float:
        yes_cost = row.cost_yes + (price * size if side == "YES" else 0.0)
        yes_qty = row.qty_yes + (size if side == "YES" else 0.0)
        no_cost = row.cost_no + (price * size if side == "NO" else 0.0)
        no_qty = row.qty_no + (size if side == "NO" else 0.0)
        return cls._avg(yes_cost, yes_qty) + cls._avg(no_cost, no_qty)

    @staticmethod
    def _size_for(capital: float, price: float, liquidity: float) -> float:
        if capital <= 0 or price <= 0:
            return 0.0
        return min(capital / price, liquidity)

    @staticmethod
    def fee_per_share(price: float, fee_rate: float = 0.072) -> float:
        return max(0.0, fee_rate * price * (1.0 - price))

    @staticmethod
    def _oracle_discrepancy_pct(spot_price: float, oracle_price: float) -> float:
        if oracle_price <= 0:
            return 0.0
        return abs(spot_price - oracle_price) / oracle_price * 100.0
