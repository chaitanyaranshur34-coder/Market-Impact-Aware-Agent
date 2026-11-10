import math

from abides_core import NanosecondTime
from abides_markets.agents import TradingAgent
from abides_markets.messages.query import QuerySpreadResponseMsg
from abides_markets.orders import Side


class MarketImpactAwareAgent(TradingAgent):
    """Impact-aware adaptive execution agent (rule-based).

    Reduces slippage versus a TWAP baseline by accounting for its own market
    impact and by pacing orders to market state:

    1. Self-impact accounting: every fill is measured against the mid at the
       moment its order was sent.  The EMA of that cost
       (`my_temporary_impact` = half-spread + temporary impact we cause) is a
       live estimate of our own footprint; when it gets expensive we shrink
       the next slices instead of continuing to walk the book.

    2. Book-aware participation cap: a slice never consumes more than
       `participation_cap` of the visible ask depth, so we stop moving the
       price against ourselves when the book is thin.  Unbought shares roll
       into later slices.

    3. Opportunistic tilt: slice size grows when the mid trades below a
       reference level (liquidity is cheap for a buyer) and shrinks when it is
       rich.  Reference = arrival midpoint (default) or a short EMA.

    4. Schedule band: cumulative purchases are kept within +-`band_pct` of the
       TWAP schedule, so the tilt can concentrate buying in cheap regimes but
       can never exhaust the budget early or dump it all at the deadline.
    """

    def __init__(
        self,
        id,
        name,
        type,
        symbol,
        starting_cash,
        total_shares,
        start_time,
        end_time,
        interval_seconds,
        dip_weight=0.75,
        dip_scale_cents=15.0,
        anchor="arrival",
        impact_weight=0.3,
        impact_scale_cents=2.0,
        participation_cap=1.0,
        band_pct=0.15,
        min_mult=0.5,
        max_mult=1.75,
        ema_span=20,
        book_depth=5,
        debug=False,
    ):
        super().__init__(id, name, type, starting_cash=starting_cash)
        self.symbol = symbol
        self.total_shares = total_shares
        self.start_time = start_time
        self.end_time = end_time
        self.interval = interval_seconds
        self.interval_ns = int(interval_seconds * 1_000_000_000)
        self.state = "IDLE"

        self.num_slices = max(1, (end_time - start_time) // self.interval_ns)
        self.target_slice = total_shares // self.num_slices
        self.slices_executed = 0
        self.shares_executed = 0
        self.total_cost = 0
        self.total_shares_filled = 0

        # --- impact / slippage accounting ---
        self.arrival_price = None
        self.price_before_last_trade = None  # mid when our last order was sent
        self.my_temporary_impact = 0.0  # EMA of what we pay above that mid

        # --- adaptive sizing knobs ---
        self.dip_weight = dip_weight
        self.dip_scale_cents = dip_scale_cents
        self.anchor = anchor
        self.impact_weight = impact_weight
        self.impact_scale_cents = impact_scale_cents
        self.participation_cap = participation_cap
        self.band_pct = band_pct
        self.min_mult = min_mult
        self.max_mult = max_mult
        self.book_depth = book_depth
        self.ema_alpha = 2.0 / (ema_span + 1.0)
        self.ema_mid = None
        self.debug = debug

    def get_wake_frequency(self) -> int:
        return self.interval_ns

    def wakeup(self, current_time):
        super().wakeup(current_time)

        if current_time < self.start_time:
            self.set_wakeup(self.start_time)
            return

        if current_time > self.end_time or self.shares_executed >= self.total_shares:
            return

        self.get_current_spread(self.symbol, self.book_depth)
        self.state = "AWAITING_SPREAD"
        self.set_wakeup(current_time + self.interval_ns)

    def receive_message(self, current_time, sender_id, msg):
        super().receive_message(current_time, sender_id, msg)

        if not (
            isinstance(msg, QuerySpreadResponseMsg)
            and msg.symbol == self.symbol
            and self.state == "AWAITING_SPREAD"
        ):
            return

        self.state = "IDLE"

        if msg.mkt_closed or current_time > self.end_time:
            return

        if not msg.bids or not msg.asks:
            return  # wakeup() already scheduled the next attempt

        bid, ask = msg.bids[0][0], msg.asks[0][0]
        mid = (bid + ask) / 2.0

        if self.arrival_price is None:
            self.arrival_price = mid

        if self.ema_mid is None:
            self.ema_mid = mid
        else:
            self.ema_mid = self.ema_alpha * mid + (1 - self.ema_alpha) * self.ema_mid

        remaining = self.total_shares - self.shares_executed
        if remaining <= 0:
            return

        intervals_left = max(
            1, math.ceil((self.end_time - current_time) / self.interval_ns)
        )

        # (3) Opportunistic tilt reference level
        ref = self.arrival_price if self.anchor == "arrival" else self.ema_mid

        # Final interval: complete the program no matter what
        if intervals_left == 1:
            quantity = remaining
        else:
            base = self.target_slice

            # (3) Buy when the mid is cheap vs the anchor
            dip_signal = max(-1.0, min(1.0, (ref - mid) / self.dip_scale_cents))

            # (1) Self-impact governor: back off when our own orders are costly
            impact_signal = max(
                0.0,
                min(
                    1.0,
                    (self.my_temporary_impact - self.impact_scale_cents)
                    / self.impact_scale_cents,
                ),
            )

            mult = 1.0 + self.dip_weight * dip_signal - self.impact_weight * impact_signal
            mult = max(self.min_mult, min(self.max_mult, mult))

            quantity = int(round(mult * base))

            # (4) Schedule band: keep cumulative purchases within +-band_pct of
            # the TWAP schedule so we never front-load the budget or dump it
            band = self.band_pct * self.total_shares
            schedule_after = (
                self.total_shares * (self.slices_executed + 1) / self.num_slices
            )
            hi = schedule_after + band - self.shares_executed
            lo = schedule_after - band - self.shares_executed
            quantity = int(max(lo, min(quantity, hi)))
            quantity = max(0, min(quantity, remaining))

            # (2) Participation cap: never consume more than our share of the
            # visible ask depth (limits how far we walk the book)
            if quantity > 0:
                visible_ask_volume = sum(v for _, v in msg.asks)
                cap = max(
                    int(0.5 * base),
                    int(self.participation_cap * visible_ask_volume),
                    1,
                )
                quantity = min(quantity, cap)
                quantity = max(1, min(quantity, remaining))

        if quantity <= 0:
            return

        if self.debug:
            import pandas as pd

            print(
                f"[SLICE] {pd.Timestamp(current_time).time()} mid={mid:.1f} "
                f"dev={ref - mid:+.1f} impEMA={self.my_temporary_impact:+.2f} "
                f"qty={quantity} left={remaining - quantity}"
            )

        # Remember the mid at send time: every fill is priced against it,
        # giving a direct measurement of our own temporary impact.
        self.price_before_last_trade = mid

        self.place_market_order(
            symbol=self.symbol,
            quantity=quantity,
            side=Side.BID,
        )

        self.shares_executed += quantity
        self.slices_executed += 1

    def order_executed(self, order):
        super().order_executed(order)

        if order.agent_id != self.id or order.symbol != self.symbol:
            return

        self.total_cost += order.fill_price * order.quantity
        self.total_shares_filled += order.quantity

        if self.price_before_last_trade is not None:
            cost_above_mid = order.fill_price - self.price_before_last_trade
            self.my_temporary_impact = (
                0.8 * self.my_temporary_impact + 0.2 * cost_above_mid
            )

        if self.debug:
            print(
                f"[FILL] {self.name}: "
                f"{order.quantity} shares "
                f"at ${order.fill_price / 100:.2f}; "
                f"total filled = {self.total_shares_filled}"
            )
