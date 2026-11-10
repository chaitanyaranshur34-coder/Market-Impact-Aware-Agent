from abides_core import Message, NanosecondTime
from abides_markets.agents import TradingAgent
from abides_markets.messages.query import QuerySpreadResponseMsg
from abides_markets.orders import Side

class TWAPAgent(TradingAgent):
    def __init__(self, id, name, type, symbol, starting_cash, total_shares, start_time, end_time, interval_seconds):
        super().__init__(id, name, type, starting_cash=starting_cash)
        self.symbol = symbol
        self.total_shares = total_shares

        # ABIDES uses nanoseconds for all time variables
        self.start_time = start_time
        self.end_time = end_time
        self.interval_ns = int(interval_seconds * 10**9)

        # Calculate TWAP slices
        total_time_ns = end_time - start_time
        self.num_slices = max(1, total_time_ns // self.interval_ns)
        self.shares_per_slice = total_shares // self.num_slices

        # State tracking
        self.slices_executed = 0
        self.shares_submitted = 0
        self.pending_trade_size = 0
        self.state = "IDLE"

        # --- METRICS FOR SLIPPAGE CALCULATION ---
        self.arrival_price = None
        self.total_cost = 0
        self.total_shares_filled = 0

    def get_wake_frequency(self) -> NanosecondTime:
        return self.interval_ns

    def wakeup(self, current_time):
        ready_to_trade = super().wakeup(current_time)

        # Too early: wake up exactly when trading should start
        if current_time < self.start_time:
            self.set_wakeup(self.start_time)
            return

        if (
            ready_to_trade
            and self.state == "IDLE"
            and current_time <= self.end_time
            and self.slices_executed < self.num_slices
        ):

            # Handle the last slice: if there's a remainder, buy it all
            if self.slices_executed == self.num_slices - 1:
                trade_qty = self.total_shares - self.shares_submitted
            else:
                trade_qty = self.shares_per_slice

            if trade_qty > 0:
                self.pending_trade_size = trade_qty
                # In ABIDES, you check the spread before placing a Market Order
                self.get_current_spread(self.symbol)
                self.state = "AWAITING_SPREAD"
                # Schedule the next slice now; don't rely on receive_message for scheduling
                self.set_wakeup(current_time + self.interval_ns)
                return

        if current_time <= self.end_time and self.slices_executed < self.num_slices:
            # Could not trade on this wakeup (e.g. market hours not known yet): retry next interval
            self.set_wakeup(current_time + self.interval_ns)

    def receive_message(self, current_time, sender_id, msg):
        super().receive_message(current_time, sender_id, msg)

        # 1. Handle Spread Query Response (Time to trade)
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
            return  # wakeup() already scheduled the next slice

        # Record Arrival Price at the very first trade tick
        if self.arrival_price is None:
            self.arrival_price = (msg.bids[0][0] + msg.asks[0][0]) / 2.0

        # Place the Market Order for this slice
        self.place_market_order(
            symbol=self.symbol,
            quantity=self.pending_trade_size,
            side=Side.BID,
        )

        self.shares_submitted += self.pending_trade_size
        self.slices_executed += 1

    # 2. Handle Order Executions (Time to record what actually happened)
    def order_executed(self, order):
        super().order_executed(order)

        if order.agent_id != self.id or order.symbol != self.symbol:
            return

        self.total_cost += (order.fill_price * order.quantity)
        self.total_shares_filled += order.quantity

        print(
            f"[FILL] {self.name}: "
            f"{order.quantity} shares "
            f"at ${order.fill_price / 100:.2f}; "
            f"total filled = {self.total_shares_filled}"
        )
