"""Always-on copy-trading loop: polls a tracked wallet, mirrors new/closed positions onto
the master account within config's risk limits, and halts if the daily circuit breaker trips.

Every potential copy is run through confirmation.confirm_direction() first - bitcoin-intel-
agent's own independent analysis must agree with the whale's direction, or the trade is
declined and logged as such, never blindly mirrored.

Resized (not opened/closed) positions are logged but not yet auto-adjusted - deciding how
much to scale an existing copy when the whale adds/trims is a separate, harder problem
deferred for now rather than guessed at.
"""

import sys
import time
from datetime import datetime, timezone

import config
import confirmation
import executor
import journal
import monitor
import risk


def log(msg):
    print(f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}] {msg}")


def run(whale_address, poll_seconds=30, max_iterations=None):
    info = monitor.make_info_client()
    previous_whale_positions = {}
    starting_equity = monitor.fetch_wallet_state(info, config.ACCOUNT_ADDRESS)["account_value"]
    log(f"Starting. Watching {whale_address}. Starting equity ${starting_equity:.2f}.")

    iteration = 0
    while max_iterations is None or iteration < max_iterations:
        iteration += 1
        my_state = monitor.fetch_wallet_state(info, config.ACCOUNT_ADDRESS)

        if risk.daily_loss_breached(starting_equity, my_state["account_value"], config.DAILY_LOSS_CIRCUIT_BREAKER_PCT):
            log(f"CIRCUIT BREAKER TRIPPED - down more than {config.DAILY_LOSS_CIRCUIT_BREAKER_PCT}% today. Halting.")
            break

        whale_state = monitor.fetch_wallet_state(info, whale_address)
        diff = monitor.diff_positions(previous_whale_positions, whale_state["positions"])

        for coin in diff["opened"]:
            whale_pos = whale_state["positions"][coin]

            confirmed, reasoning, _ = confirmation.confirm_direction(coin, whale_pos["side"])
            if not confirmed:
                log(f"Whale opened {whale_pos['side']} {coin} - DECLINED, no independent confirmation: {reasoning}")
                continue

            if len(my_state["positions"]) >= config.MAX_CONCURRENT_POSITIONS:
                log(f"Whale opened {coin}, confirmed, but we're at the {config.MAX_CONCURRENT_POSITIONS}-position cap - skipping")
                continue

            sizing = risk.compute_copy_size(
                my_state["account_value"], whale_state["account_value"], whale_pos,
                config.MAX_RISK_PCT_PER_TRADE, config.MAX_LEVERAGE,
            )
            log(f"Whale opened {whale_pos['side']} {coin} - CONFIRMED ({len(reasoning)} supporting signals), "
                f"copying {sizing['size']:.6f} ({sizing['our_risk_pct']:.1f}% risk, {sizing['leverage']}x)")
            result = executor.place_market_order(coin, whale_pos["side"] == "Long", sizing["size"])
            log(f"Order result: {result}")
            journal.log_open(coin, whale_pos["side"], sizing["size"], whale_address, whale_pos["entry_price"], reasoning)

        for coin in diff["closed"]:
            log(f"Whale closed {coin} - closing our mirrored position")
            last_known_pnl = my_state["positions"].get(coin, {}).get("unrealized_pnl", 0.0)
            result = executor.close_position(coin)
            log(f"Close result: {result}")
            try:
                exit_price = float(result["response"]["data"]["statuses"][0]["filled"]["avgPx"])
                journal.log_close(coin, exit_price, last_known_pnl)
            except (KeyError, IndexError, TypeError):
                log(f"Could not parse close fill for journal - logged order result above, journal entry left open for {coin}")

        for coin in diff["changed"]:
            log(f"Whale resized/flipped {coin} - logged only, not auto-adjusting yet")

        previous_whale_positions = whale_state["positions"]
        if max_iterations is None or iteration < max_iterations:
            time.sleep(poll_seconds)

    log(f"Stopped after {iteration} iteration(s).")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python bot.py <whale_address_to_track> [poll_seconds]")
    poll = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    run(sys.argv[1], poll_seconds=poll)
