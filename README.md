# hyperliquid-copy-trader

A copy-trading bot for Hyperliquid: watches specific wallet addresses and mirrors their
trades onto your own account, proportionally sized to your equity, within hard risk limits
- and never copies a trade it can't independently justify.

**Status: validated end-to-end on testnet**, including the full confirm -> execute ->
journal pipeline with a real signed order. Not yet run continuously against a genuinely
active tracked wallet - the mechanics are proven, a live detected-and-confirmed copy in the
wild hasn't been demonstrated yet. Never touched mainnet. Separate from
[bitcoin-intel-agent](../bitcoin-intel-agent) on purpose - that project's whole premise is
"never executes trades"; this one's job is the opposite. It does, however, *depend on*
bitcoin-intel-agent's analysis as the confirmation gate (see below) - that's a one-way
dependency (this imports from there, not the reverse), so the safety boundary still holds.

## Safety model

- **Defaults to testnet** (`config.NETWORK = "testnet"`). Mainnet is a deliberate, separate
  decision after a real testnet validation period - not a flag you flip casually.
- **Agent/API wallets only.** Generate one at https://app.hyperliquid-testnet.xyz/API (or
  the mainnet equivalent, later). These are cryptographically incapable of withdrawing
  funds - even a compromised key can only trade, never move money out. Your main account's
  private key is never used by this project. Agent wallets don't hold funds themselves -
  all balance and positions live on the master account.
- **Credentials are environment variables, never code, never chat.** `HL_AGENT_PRIVATE_KEY`
  and `HL_ACCOUNT_ADDRESS` - set them yourself, locally. `.env` and anything resembling a
  secret is gitignored.
- **Reading wallets needs no credentials at all** - `monitor.py` uses the same free, public,
  keyless Hyperliquid endpoint as the Watchlist in `bitcoin-intel-agent`. Only `executor.py`
  (placing/closing orders) needs the agent wallet.

## Smart-money confirmation gate

Before copying *any* whale trade, `confirmation.py` calls bitcoin-intel-agent's own
independent analysis for that coin and requires it to agree with the whale's direction. If
bitcoin-intel-agent's bias isn't an exact match (including if it's already been overridden
to "No Trade" by its own no-trade rules), the copy is **declined and logged as declined** -
never blindly mirrored just because a tracked wallet did it. Only BTC/ETH/SOL/HYPE are
covered (bitcoin-intel-agent's supported coins); anything else is auto-declined for lack of
independent evidence.

This is deliberately strict - in practice it will decline most potential copies, especially
during choppy/uncertain markets when bitcoin-intel-agent's own no-trade rules are already
firing. That's intentional: "a missed trade is preferable to a bad trade."

## Trade journal

Every trade this bot actually places (confirmed copies only) gets logged to
`trade_journal.csv`: entry time/price/size, the whale being copied, the confirmation
reasoning that justified entry, and - once closed - exit price, P&L, and an outcome note
("Won: ... direction played out as expected" / "Lost: ... worth reviewing which signal(s)
were misleading"). View it in the dashboard's **Trade Journal** menu, including win rate
and cumulative P&L. This is real history to learn from, not a vague promise to "do better
next time" - there's nothing to apply lessons from without an actual logged record.

## Risk limits (current defaults - see `config.py`, confirm/adjust before going further)

- Position sizing: proportional to account size (mirrors the tracked wallet's risk as a %
  of *their* equity, scaled to yours), capped at **3% max risk per trade**
- Max leverage: **5x**, regardless of what the tracked wallet uses
- Max concurrent copied positions: **5**
- Daily loss circuit breaker: **5%** - auto-pause, requires manual re-enable

## Project layout

- `config.py` - network selection, risk limits, credential loading (env vars only)
- `risk.py` - pure position-sizing and circuit-breaker math, no I/O
- `monitor.py` - read-only wallet polling and position-change detection, no credentials needed
- `confirmation.py` - smart-money confirmation gate, depends on bitcoin-intel-agent's analysis
- `executor.py` - order placement via the official SDK, signed by the agent wallet, acting on the master account
- `journal.py` - trade journal logging and outcome notes
- `bot.py` - the loop: polls a tracked wallet, confirms, copies opens/closes within risk limits, halts on the circuit breaker
- `dashboard.py` - Account Overview + Trade Journal menu

## Known gaps

- Resized positions (whale adds to or trims an existing position) are logged but not yet
  auto-adjusted - deciding how much to scale an existing copy is a separate problem, not
  guessed at here.
- Hasn't been run continuously against a wallet that's actually trading on testnet, so a
  real detected-confirmed-and-copied trade in the wild hasn't been demonstrated yet, only
  each piece individually (confirmation gate, execution, journal) with real signed orders.
- The small list of supported coins (BTC/ETH/SOL/HYPE) means whale trades on other assets
  get auto-declined for lack of coverage, not lack of merit.

## Setup

```
pip install -r requirements.txt
```

## Run

```
python bot.py <wallet_address_to_track> [poll_seconds]
streamlit run dashboard.py
```
