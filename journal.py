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


def _generate_outcome_note(side, confirmation_reasoning, pnl_pct):
    won = pnl_pct > 0
    signal_count = len(confirmation_reasoning.split(" | ")) if confirmation_reasoning else 0
    if won:
        return f"Won ({pnl_pct:+.2f}%): entered with {signal_count} confirming signal(s) - direction played out as expected."
    return (
        f"Lost ({pnl_pct:+.2f}%): entered with {signal_count} confirming signal(s) at the time, "
        f"but price moved against the position - worth reviewing which signal(s) were misleading."
    )


def log_close(coin, exit_price, pnl_usd):
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
            row["outcome_note"] = _generate_outcome_note(row["side"], row["confirmation_reasoning"], pnl_pct)
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
