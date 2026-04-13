from exchange.paper_trading import MIN_ORDER_AMOUNT, DEFAULT_MIN_AMOUNT


class RiskGuardrails:
    def __init__(
        self,
        budget: float,
        stop_loss_pct: float,
        max_trades_per_day: int,
        max_losses_per_day: int = 3,
        max_daily_loss_pct: float = 0.05,
        position_size_pct: float = 0.25,
    ):
        self.budget = budget
        self.stop_loss_pct = stop_loss_pct
        self.max_trades_per_day = max_trades_per_day
        self.max_losses_per_day = max_losses_per_day
        self.max_daily_loss_pct = max_daily_loss_pct
        self.position_size_pct = max(0.05, min(0.80, float(position_size_pct or 0.25)))

    def can_trade(self, agent_state) -> tuple[bool, str]:
        if agent_state.status == "killed":
            return False, "Bot has been closed"
        if agent_state.status == "stopped":
            return False, "Bot is paused"
        if agent_state.trades_today >= self.max_trades_per_day:
            return False, f"Max trades per day ({self.max_trades_per_day}) reached"
        remaining_budget = getattr(
            agent_state,
            "effective_remaining_budget",
            (agent_state.budget_allocated + getattr(agent_state, "realized_pnl_total", 0.0)) - agent_state.budget_used,
        )
        remaining_budget = max(0.0, float(remaining_budget or 0.0))
        if remaining_budget <= 0:
            return False, "No remaining budget"

        # Exit criteria: too many losses today
        losses_today = getattr(agent_state, 'losses_today', 0) or 0
        if losses_today >= self.max_losses_per_day:
            return False, f"Daily loss limit reached: {losses_today} losing trades today (max {self.max_losses_per_day})"

        # Exit criteria: daily loss % of budget exceeded
        realized_pnl_today = getattr(agent_state, 'realized_pnl_today', 0.0) or 0.0
        max_loss_amount = self.budget * self.max_daily_loss_pct
        if realized_pnl_today <= -max_loss_amount:
            return False, f"Daily loss cap hit: lost ${abs(realized_pnl_today):.2f} MXN today (max {self.max_daily_loss_pct*100:.0f}% = ${max_loss_amount:.2f})"

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

        trade_budget = available_budget * self.position_size_pct
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

    def calculate_adaptive_position_size(
        self, available_budget: float, price: float, symbol: str, confidence: float
    ) -> float:
        """
        Scale position size by signal confidence: 15% to 35% of available budget.
        Stronger signals get larger positions, weaker signals stay conservative.
        """
        if price <= 0 or available_budget <= 0:
            return 0.0

        min_amount = MIN_ORDER_AMOUNT.get(symbol, DEFAULT_MIN_AMOUNT)

        base_pct = self.position_size_pct
        effective_pct = (base_pct * 0.6) + max(0.0, min(confidence, 1.0)) * (base_pct * 0.8)
        trade_budget = available_budget * effective_pct
        amount = trade_budget / price
        amount = round(amount, 8)

        if amount < min_amount:
            min_cost = min_amount * price
            if min_cost <= available_budget:
                amount = min_amount
            else:
                return 0.0

        return round(amount, 8)
