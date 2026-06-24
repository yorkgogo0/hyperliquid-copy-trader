"""Solo strategy loop: trades directly off bitcoin-intel-agent's own analysis - no whale
tracking, no confirmation gate (there's nothing to confirm against). Opens a position when
a coin gets a Long/Short call that already passed bitcoin-intel-agent's own no-trade rules,
sized by its confidence tier. Closes when the live analysis no longer agrees with holding
the position (bias changed), or price has crossed the freshly-recomputed invalidation/target.
"""

import os
import sys
import time
from datetime import datetime, timezone

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


def compute_solo_size(my_account_value, entry_price, size_tier):
    """No whale to be proportional to - sizes directly off our own risk cap and confidence tier."""
    tier_multiplier = risk.SIZE_TIER_MULTIPLIERS.get(size_tier, 1.0)
    risk_pct = config.MAX_RISK_PCT_PER_TRADE * tier_multiplier
    margin_usd = risk_pct / 100 * my_account_value
    notional_usd = margin_usd * config.MAX_LEVERAGE
    size = notional_usd / entry_price if entry_price else 0.0
    return {"risk_pct": risk_pct, "leverage": config.MAX_LEVERAGE, "margin_usd": margin_usd, "size": size}


def run(poll_seconds=60, max_iterations=None):
    info = monitor.make_info_client()
    starting_equity = monitor.fetch_wallet_state(info, config.ACCOUNT_ADDRESS)["account_value"]
    log(f"Starting solo strategy loop. Coins: {COINS}. Starting equity ${starting_equity:.2f}.")

    iteration = 0
    while max_iterations is None or iteration < max_iterations:
        iteration += 1
        my_state = monitor.fetch_wallet_state(info, config.ACCOUNT_ADDRESS)

        if risk.daily_loss_breached(starting_equity, my_state["account_value"], config.DAILY_LOSS_CIRCUIT_BREAKER_PCT):
            log(f"CIRCUIT BREAKER TRIPPED - down more than {config.DAILY_LOSS_CIRCUIT_BREAKER_PCT}% today. Halting.")
            break

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

            if report["bias"] not in ("Long", "Short"):
                continue
            if len(my_state["positions"]) >= config.MAX_CONCURRENT_POSITIONS:
                log(f"{coin}: signal is {report['bias']} but at the {config.MAX_CONCURRENT_POSITIONS}-position cap - skipping")
                continue

            sizing = compute_solo_size(my_state["account_value"], report["price"], report["size_tier"])
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
