from exchange.paper_trading import MIN_ORDER_AMOUNT, DEFAULT_MIN_AMOUNT


class RiskGuardrails:
    def __init__(self, budget: float, stop_loss_pct: float, max_trades_per_day: int):
        self.budget = budget
        self.stop_loss_pct = stop_loss_pct
        self.max_trades_per_day = max_trades_per_day

    def can_trade(self, agent_state) -> tuple[bool, str]:
        if agent_state.status == "killed":
            return False, "Agent has been killed"
        if agent_state.status == "stopped":
            return False, "Agent is stopped"
        if agent_state.trades_today >= self.max_trades_per_day:
            return False, f"Max trades per day ({self.max_trades_per_day}) reached"
        remaining_budget = agent_state.budget_allocated - agent_state.budget_used
        if remaining_budget <= 0:
            return False, "No remaining budget"
        return True, "OK"

    def check_stop_loss(self, entry_price: float, current_price: float, side: str) -> bool:
        if side == "buy":
            loss_pct = (entry_price - current_price) / entry_price
            return loss_pct >= self.stop_loss_pct
        elif side == "sell":
            loss_pct = (current_price - entry_price) / entry_price
            return loss_pct >= self.stop_loss_pct
        return False

    def calculate_position_size(self, available_budget: float, price: float, symbol: str = "BTC/MXN") -> float:
        """
        Size a trade at 25% of available budget per trade (realistic for day trading).
        If 25% falls below the exchange minimum order size, uses the minimum directly
        (as long as it's affordable). Returns 0.0 if even the minimum is unaffordable.
        """
        if price <= 0 or available_budget <= 0:
            return 0.0

        min_amount = MIN_ORDER_AMOUNT.get(symbol, DEFAULT_MIN_AMOUNT)

        trade_budget = available_budget * 0.25
        amount = trade_budget / price
        amount = round(amount, 8)

        if amount < min_amount:
            # 25% isn't enough — try the minimum order size
            min_cost = min_amount * price
            if min_cost <= available_budget:
                amount = min_amount
            else:
                return 0.0  # Can't afford even the minimum — budget too small for this pair

        return round(amount, 8)
