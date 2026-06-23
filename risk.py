"""Pure position-sizing and risk math - no I/O, no network calls, no SDK."""


def compute_copy_size(my_account_value, whale_account_value, whale_position, max_risk_pct, max_leverage):
    """Mirrors the whale's risk as a % of THEIR account, scaled to ours, capped at max_risk_pct
    of our own equity. Uses margin_used as the risk proxy since we can't see their actual
    stop-loss - that's a private intention, not public on-chain data."""
    whale_risk_pct = whale_position["margin_used"] / whale_account_value * 100
    our_risk_pct = min(whale_risk_pct, max_risk_pct)
    our_margin_budget = our_risk_pct / 100 * my_account_value

    leverage = min(whale_position["leverage"], max_leverage)
    notional_usd = our_margin_budget * leverage
    size = notional_usd / whale_position["entry_price"] if whale_position["entry_price"] else 0.0

    return {
        "whale_risk_pct": whale_risk_pct,
        "our_risk_pct": our_risk_pct,
        "leverage": leverage,
        "margin_usd": our_margin_budget,
        "notional_usd": notional_usd,
        "size": size,
    }


def daily_loss_breached(starting_equity, current_equity, circuit_breaker_pct):
    if starting_equity <= 0:
        return False
    loss_pct = (starting_equity - current_equity) / starting_equity * 100
    return loss_pct >= circuit_breaker_pct
