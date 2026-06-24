"""Read-only wallet polling - same free, keyless Hyperliquid endpoint as bitcoin-intel-agent's
Watchlist. No credentials needed here; this never places an order."""

from hyperliquid.info import Info

import config


def fetch_wallet_state(info, address):
    state = info.user_state(address)
    positions = {}
    for entry in state.get("assetPositions", []):
        pos = entry["position"]
        size = float(pos["szi"])
        if size == 0:
            continue
        positions[pos["coin"]] = {
            "side": "Long" if size > 0 else "Short",
            "size": abs(size),
            "leverage": pos["leverage"]["value"],
            "entry_price": float(pos["entryPx"]),
            "margin_used": float(pos["marginUsed"]),
            "position_value_usd": float(pos["positionValue"]),
            "unrealized_pnl": float(pos["unrealizedPnl"]),
        }
    return {"account_value": float(state["marginSummary"]["accountValue"]), "positions": positions}


def fetch_closing_fills(info, address, coin, since_ms):
    """Fills for `coin` since `since_ms` that reduced/closed a position - used to reconcile
    a position that disappeared without our own code closing it (most likely: liquidation),
    so the journal logs the real outcome instead of leaving a permanently-stale 'open' row."""
    fills = info.user_fills(address)
    return [
        f for f in fills
        if f["coin"] == coin and f["time"] >= since_ms and f["dir"].startswith("Close")
    ]


def diff_positions(previous, current):
    """Compares two fetch_wallet_state() position dicts. Returns opened/closed/changed coin lists."""
    prev_coins = set(previous.keys())
    curr_coins = set(current.keys())
    opened = [c for c in curr_coins - prev_coins]
    closed = [c for c in prev_coins - curr_coins]
    changed = [
        c
        for c in curr_coins & prev_coins
        if previous[c]["side"] != current[c]["side"] or abs(previous[c]["size"] - current[c]["size"]) / previous[c]["size"] > 0.05
    ]
    return {"opened": opened, "closed": closed, "changed": changed}


def make_info_client():
    return Info(config.API_URL, skip_ws=True)
