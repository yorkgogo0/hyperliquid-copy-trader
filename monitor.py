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


def fetch_realized_pnl(info, address, coin, since_ms, until_ms=None):
    """True net economic result for `coin` in [since_ms, until_ms]: gross closedPnl from the
    closing fill(s), minus ALL fees in that window - both the closing fee AND the opening
    fee. Hyperliquid's own UI 'Closed PNL' column only nets the closing fee (verified live:
    a $0.0679 gross SOL gain showed as the UI's '$0.01' once just its $0.0607 closing fee
    was subtracted - the $0.0607 opening fee paid earlier never got netted against it
    there, because the UI shows opens/closes as separate rows). A journal row represents one
    full round trip, so it should net both, not just one side.

    Leave `until_ms` unset for live use right after closing (there's nothing newer yet).
    Set it explicitly when recomputing history - otherwise a later, separate round trip on
    the same coin gets blended in too (caught live: a retroactive SOL query with no upper
    bound silently pulled in 3 unrelated later trades' fills alongside the one being looked up).

    Also used to reconcile a position that disappeared without our own code closing it
    (most likely: liquidation) - the journal logs the real outcome instead of leaving a
    permanently-stale 'open' row."""
    fills = [
        f for f in info.user_fills(address)
        if f["coin"] == coin and f["time"] >= since_ms and (until_ms is None or f["time"] <= until_ms)
    ]
    closing_fills = [f for f in fills if f["dir"].startswith("Close")]
    gross_pnl = sum(float(f.get("closedPnl") or 0.0) for f in closing_fills)
    total_fees = sum(float(f.get("fee") or 0.0) for f in fills)
    avg_exit_price = (
        sum(float(f["sz"]) * float(f["px"]) for f in closing_fills) / sum(float(f["sz"]) for f in closing_fills)
        if closing_fills else None
    )
    return {
        "pnl": gross_pnl - total_fees,
        "avg_exit_price": avg_exit_price,
        "liquidated": any(f.get("liquidation") for f in closing_fills),
        "has_close": bool(closing_fills),
    }


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
