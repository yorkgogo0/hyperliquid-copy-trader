"""Solo strategy loop: trades directly off bitcoin-intel-agent's own analysis - no whale
tracking, no confirmation gate (there's nothing to confirm against). Opens a position when
a coin gets a Long/Short call that already passed bitcoin-intel-agent's own no-trade rules,
sized by its confidence tier. Closes when the live analysis no longer agrees with holding
the position (bias changed), or price has crossed the freshly-recomputed invalidation/target.

Reads bot_control.json every cycle (written by the dashboard's Bot Control page): pausing
("running": false) stops new entries but still manages exits on whatever's already open -
abandoning risk management on an open position because trading was paused would be worse
than just not opening anything new. The leverage value there overrides config.MAX_LEVERAGE
for new orders only - it doesn't retroactively change positions already open.
"""

import os
import sys
import time
from datetime import datetime, timezone

import bot_control
import config
import executor
import journal
import monitor
import risk

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bitcoin-intel-agent"))
from bitcoin_intel_agent import run_analysis  # noqa: E402

COINS = ["BTC", "ETH", "SOL", "HYPE"]


def log(msg):
    print(f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}] {msg}")


def reconcile_phantom_closes(info, my_state):
    """A journal row can still show 'open' for a coin we no longer hold if something closed
    it outside our own exit logic - in practice, a liquidation (caught live: a position
    vanished between poll cycles with no log_close ever called, because the exchange closed
    it directly, not through executor.close_position()). Looks up the real fill so the
    journal records what actually happened instead of going stale forever."""
    for row in journal.load_journal():
        if row["closed_at"] or row["coin"] in my_state["positions"]:
            continue
        opened_at = datetime.strptime(row["opened_at"], "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)
        since_ms = int(opened_at.timestamp() * 1000)
        fills = monitor.fetch_closing_fills(info, config.ACCOUNT_ADDRESS, row["coin"], since_ms)
        if not fills:
            log(f"{row['coin']}: journal shows open but position is gone, and no closing fills found - leaving as-is")
            continue
        total_size = sum(float(f["sz"]) for f in fills)
        avg_price = sum(float(f["sz"]) * float(f["px"]) for f in fills) / total_size
        total_pnl = sum(float(f.get("closedPnl") or 0.0) for f in fills)
        was_liquidated = any(f.get("liquidation") for f in fills)
        log(f"{row['coin']}: reconciling phantom close - {'LIQUIDATED' if was_liquidated else 'closed externally'} at avg ${avg_price:,.4f}, pnl ${total_pnl:+.2f}")
        journal.log_close(row["coin"], avg_price, total_pnl, liquidated=was_liquidated)


def compute_solo_size(my_account_value, entry_price, size_tier, leverage):
    """No whale to be proportional to - sizes directly off our own risk cap and confidence tier."""
    tier_multiplier = risk.SIZE_TIER_MULTIPLIERS.get(size_tier, 1.0)
    risk_pct = config.MAX_RISK_PCT_PER_TRADE * tier_multiplier
    margin_usd = risk_pct / 100 * my_account_value
    notional_usd = margin_usd * leverage
    size = notional_usd / entry_price if entry_price else 0.0
    return {"risk_pct": risk_pct, "leverage": leverage, "margin_usd": margin_usd, "size": size}


def run(poll_seconds=60, max_iterations=None):
    info = monitor.make_info_client()
    starting_equity = monitor.fetch_wallet_state(info, config.ACCOUNT_ADDRESS)["account_value"]
    log(f"Starting solo strategy loop. Coins: {COINS}. Starting equity ${starting_equity:.2f}.")

    iteration = 0
    while max_iterations is None or iteration < max_iterations:
        iteration += 1
        control = bot_control.read_control()
        my_state = monitor.fetch_wallet_state(info, config.ACCOUNT_ADDRESS)
        reconcile_phantom_closes(info, my_state)

        if risk.daily_loss_breached(starting_equity, my_state["account_value"], config.DAILY_LOSS_CIRCUIT_BREAKER_PCT):
            log(f"CIRCUIT BREAKER TRIPPED - down more than {config.DAILY_LOSS_CIRCUIT_BREAKER_PCT}% today. Halting.")
            break

        if not control["running"]:
            log(f"Paused via dashboard - managing exits on open positions only, not opening anything new ({len(my_state['positions'])} open)")

        for coin in COINS:
            try:
                report = run_analysis(coin)
            except Exception as exc:  # any data-source hiccup for one coin shouldn't kill the loop
                log(f"{coin}: analysis failed ({exc}), skipping this cycle")
                continue

            held = my_state["positions"].get(coin)

            if held:
                price = report["price"]
                should_exit = report["bias"] != held["side"]
                if not should_exit and report["invalidation"]:
                    should_exit = (price <= report["invalidation"]) if held["side"] == "Long" else (price >= report["invalidation"])
                if not should_exit and report["target"]:
                    should_exit = (price >= report["target"]) if held["side"] == "Long" else (price <= report["target"])
                if should_exit:
                    last_known_pnl = held["unrealized_pnl"]
                    log(f"{coin}: closing {held['side']} - bias now {report['bias']}, price {price:,.2f}")
                    result = executor.close_position(coin)
                    log(f"Close result: {result}")
                    try:
                        exit_price = float(result["response"]["data"]["statuses"][0]["filled"]["avgPx"])
                        journal.log_close(coin, exit_price, last_known_pnl)
                    except (KeyError, IndexError, TypeError):
                        log(f"Could not parse close fill for journal - {coin}")
                continue

            if not control["running"]:
                continue
            if report["bias"] not in ("Long", "Short"):
                continue
            if len(my_state["positions"]) >= config.MAX_CONCURRENT_POSITIONS:
                log(f"{coin}: signal is {report['bias']} but at the {config.MAX_CONCURRENT_POSITIONS}-position cap - skipping")
                continue

            sizing = compute_solo_size(my_state["account_value"], report["price"], report["size_tier"], control["leverage"])
            log(
                f"{coin}: {report['bias']} signal ({report['size_tier']} tier, "
                f"{len(report['supporting_signals'])} supporting signals) - requesting {sizing['size']:.6f} "
                f"({sizing['risk_pct']:.1f}% risk, {sizing['leverage']}x)"
            )
            result = executor.place_market_order(coin, report["bias"] == "Long", sizing["size"], leverage=sizing["leverage"])
            log(f"Order result: {result}")
            try:
                fill = result["response"]["data"]["statuses"][0]["filled"]
                filled_size, filled_price = float(fill["totalSz"]), float(fill["avgPx"])
                if filled_size != sizing["size"]:
                    log(f"{coin}: requested {sizing['size']:.6f} but only {filled_size} filled (testnet liquidity) - journaling the real fill")
                journal.log_open(coin, report["bias"], filled_size, "solo-strategy", filled_price, report["supporting_signals"])
            except (KeyError, IndexError, TypeError):
                log(f"{coin}: could not parse fill - not journaling an entry I can't verify actually happened")

        if max_iterations is None or iteration < max_iterations:
            time.sleep(poll_seconds)

    log(f"Stopped after {iteration} iteration(s).")


if __name__ == "__main__":
    poll = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    run(poll_seconds=poll)
