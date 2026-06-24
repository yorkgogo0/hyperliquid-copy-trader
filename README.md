# hyperliquid-copy-trader

A copy-trading bot for Hyperliquid: watches specific wallet addresses and mirrors their
trades onto your own account, proportionally sized to your equity, within hard risk limits.

**Status: validated end-to-end on testnet.** Order placement, position closing, and the
polling loop have all been run against real testnet infrastructure with real signed orders
(on fake money). Not yet run continuously against a genuinely active tracked wallet - the
loop mechanics are proven, a live detected-copy hasn't been demonstrated yet. Never touched
mainnet. Separate from [bitcoin-intel-agent](../bitcoin-intel-agent) on purpose - that
project's whole premise is "never executes trades"; this one's job is the opposite, so they
shouldn't share a codebase.

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
- `executor.py` - order placement via the official SDK, signed by the agent wallet, acting on the master account
- `bot.py` - the loop: polls a tracked wallet, copies opens/closes within risk limits, halts on the circuit breaker

## Known gaps

- Resized positions (whale adds to or trims an existing position) are logged but not yet
  auto-adjusted - deciding how much to scale an existing copy is a separate problem, not
  guessed at here.
- Hasn't been run continuously against a wallet that's actually trading on testnet, so a
  real detected-and-copied trade hasn't been demonstrated yet, only the loop mechanics
  (polling, equity tracking, circuit breaker, clean start/stop).

## Setup

```
pip install -r requirements.txt
```

## Run

```
python bot.py <wallet_address_to_track> [poll_seconds]
```

Read-only monitoring and the bot loop's structure work with just `HL_AGENT_PRIVATE_KEY`
and `HL_ACCOUNT_ADDRESS` set as environment variables.
