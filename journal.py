"""Trade journal: every copied trade we actually open/close, with the confirmation
reasoning that justified entry and an outcome note once it's closed."""

import csv
import os
from datetime import datetime, timezone

JOURNAL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trade_journal.csv")
FIELDS = [
    "opened_at", "closed_at", "coin", "side", "size", "whale_address",
    "entry_price", "exit_price", "pnl_usd", "pnl_pct", "confirmation_reasoning", "outcome_note",
]


def log_open(coin, side, size, whale_address, entry_price, reasoning):
    is_new = not os.path.exists(JOURNAL_FILE)
    with open(JOURNAL_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(FIELDS)
        writer.writerow([
            datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"), "", coin, side, size, whale_address,
            f"{entry_price:.6f}", "", "", "", " | ".join(reasoning), "",
        ])


def _generate_outcome_note(side, confirmation_reasoning, pnl_pct, pnl_usd, liquidated=False):
    """Win/loss is decided by pnl_usd (net of both open and close fees), not pnl_pct (price
    move only) - the two can disagree on small trades where fees roughly cancel out a tiny
    favorable price move, and what actually happened to the account is what matters here."""
    won = pnl_usd > 0
    signal_count = len(confirmation_reasoning.split(" | ")) if confirmation_reasoning else 0
    if liquidated:
        return (
            f"LIQUIDATED (${pnl_usd:+.4f}, {pnl_pct:+.2f}% price move): position was force-closed "
            f"by the exchange before the strategy's own exit logic acted - this is a margin/sizing "
            f"problem, not evidence the {signal_count} entry signal(s) were wrong."
        )
    if won:
        return f"Won (${pnl_usd:+.4f}): entered with {signal_count} confirming signal(s) - direction played out as expected."
    if pnl_pct > 0:
        return (
            f"Lost (${pnl_usd:+.4f} after fees, despite a {pnl_pct:+.2f}% favorable price move): "
            f"entered with {signal_count} confirming signal(s) - fees alone outweighed the gain on this size."
        )
    return (
        f"Lost (${pnl_usd:+.4f}, {pnl_pct:+.2f}%): entered with {signal_count} confirming signal(s) at the time, "
        f"but price moved against the position - worth reviewing which signal(s) were misleading."
    )


def find_open_row(coin):
    """Most recent still-open journal row for this coin, or None - lets a caller look up
    a position's real open time before closing it (e.g. to scope a fills query)."""
    for row in reversed(load_journal()):
        if row["coin"] == coin and not row["closed_at"]:
            return row
    return None


def log_close(coin, exit_price, pnl_usd, liquidated=False):
    """Finds the most recent still-open journal row for this coin and fills in the outcome."""
    if not os.path.exists(JOURNAL_FILE):
        return None
    with open(JOURNAL_FILE, newline="") as f:
        rows = list(csv.DictReader(f))

    updated_row = None
    for row in reversed(rows):
        if row["coin"] == coin and not row["closed_at"]:
            entry_price = float(row["entry_price"])
            pnl_pct = (
                (exit_price - entry_price) / entry_price * 100
                if row["side"] == "Long"
                else (entry_price - exit_price) / entry_price * 100
            )
            row["closed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            row["exit_price"] = f"{exit_price:.6f}"
            row["pnl_usd"] = f"{pnl_usd:.4f}"
            row["pnl_pct"] = f"{pnl_pct:.2f}"
            row["outcome_note"] = _generate_outcome_note(row["side"], row["confirmation_reasoning"], pnl_pct, pnl_usd, liquidated)
            updated_row = row
            break

    if updated_row:
        with open(JOURNAL_FILE, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
    return updated_row


def load_journal():
    if not os.path.exists(JOURNAL_FILE):
        return []
    with open(JOURNAL_FILE, newline="") as f:
        return list(csv.DictReader(f))
