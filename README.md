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

## Solo strategy mode (`solo_bot.py`)

No whale, no confirmation gate (there's nothing to confirm against) - trades directly off
bitcoin-intel-agent's own Long/Short calls across BTC/ETH/SOL/HYPE, sized by confidence
tier. Exits when the live analysis no longer agrees with holding the position (bias
changed) or price crosses the freshly-recomputed invalidation/target. Same risk limits,
same journal.

## Bot Control (start/stop + leverage, from the dashboard)

The dashboard's **Bot Control** page writes to `bot_control.json`; the already-running bot
process (`solo_bot.py`, started separately - see Run below) reads it every poll cycle.
Streamlit's request/response model isn't suited to hosting the actual long-running loop
itself, so the dashboard only ever edits this shared file - it never starts or kills the
bot process directly.

- **Trading enabled / Paused toggle** - paused means no *new* positions get opened, but
  exits on anything already open are still managed. Abandoning risk management on an open
  position because trading was paused would be worse than just not opening anything new.
- **Leverage (1x/2x/5x/10x)** - applies to new positions only, via the SDK's
  `update_leverage` call right before each order. Doesn't retroactively change positions
  already open.

**A real liquidation happened during testing**, which is why the reconciliation logic
below exists. A position got force-closed by the exchange (not by `solo_bot.py`'s own exit
logic) while two positions were open concurrently under cross margin - cross margin shares
one pool across all open positions, so the per-trade "5x leverage, 3% risk" framing
understates real liquidation risk once more than one position is open at once. Worth
deciding deliberately (tighter `MAX_CONCURRENT_POSITIONS`, isolated margin, or sizing off
available rather than total margin) rather than assuming the existing caps already cover it.

### Reconciliation

If a journaled-open position disappears without `solo_bot.py`'s own `executor.close_position()`
ever being called - in practice, a liquidation - the journal would otherwise show that
trade as permanently "still open" forever. `reconcile_phantom_closes()` runs at the start
of every poll cycle: for any open journal row whose coin isn't actually held anymore, it
looks up the real closing fill (including Hyperliquid's own `liquidation` flag) via
`userFills` and logs the true outcome, with an explicit `LIQUIDATED` note rather than the
normal win/loss framing - getting liquidated isn't evidence the entry signal was wrong,
it's a margin/sizing problem.

### PnL accuracy (`monitor.fetch_realized_pnl`)

The journal's `pnl_usd` is the *net* economic result of a round trip - gross `closedPnl`
from the closing fill(s), minus **both** the opening and closing fee. Two real bugs found
by checking logged numbers against the exchange's own trade history (asked "how did I make
18 cents here" when the real number was $0.01):

1. The journal was logging the position's stale pre-close `unrealized_pnl` snapshot
   (captured before the close order even executed), not the actual realized PnL from the
   fill that closed it.
2. Even fixed to use the real `closedPnl`, it still didn't match Hyperliquid's own UI -
   because that UI column only nets the *closing* fee against the price PnL, not the
   *opening* fee paid earlier (verified live: a $0.0679 gross gain, minus the $0.0607
   closing fee, displays as the UI's "$0.01" - the $0.0607 opening fee paid earlier is never
   subtracted there, since the UI shows opens and closes as separate rows). A journal row
   represents one full round trip, so both fees get netted, which won't match the per-row
   UI number and is correct, not a bug.

Win/loss in the outcome note is decided by `pnl_usd` (the net dollar result), not
`pnl_pct` (price move only) - on small trades the two can disagree, e.g. a real result of
"price moved favorably but fees outweighed the gain" needs to show as a loss, not a win.

Two real bugs caught live while testing this before running it indefinitely:
- **Order size precision**: Hyperliquid rejects sizes with more decimals than an asset
  allows (HYPE/SOL: 2, ETH: 4, BTC: 5) - `executor.round_size()` fixes this for every order.
- **Leverage was never being set explicitly** - a position opened at ~10x when the sizing
  math assumed 5x, because the exchange uses whatever was last configured for that
  coin/account rather than something tied to each order. `place_market_order` now takes a
  `leverage` argument and sets it before submitting.
- Testnet liquidity is consistently thin enough that orders partially fill or fail to match
  at the default 1% slippage - raised the default to 3%, and both bots now journal the
  *actual filled* size/price, not the requested ones.

## Risk limits (current defaults - see `config.py`, confirm/adjust before going further)

- Position sizing: proportional to account size (mirrors the tracked wallet's risk as a %
  of *their* equity, scaled to yours), capped at **3% max risk per trade**
- **Tiered by confirmation confidence**: bitcoin-intel-agent's confidence tier scales the
  position further - Small (50-59% confidence) = 0.4x, Normal (60-69%) = 0.7x, Full (70%+)
  = 1.0x of the 3% cap. A confirmed-but-lower-confidence copy still gets taken, just smaller
  - more trade frequency without increasing per-trade risk.
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
- `bot.py` - whale-copy loop: polls a tracked wallet, confirms, copies opens/closes within risk limits, halts on the circuit breaker
- `solo_bot.py` - solo strategy loop: trades directly off bitcoin-intel-agent's own calls, no whale
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
