# hyperliquid-copy-trader

A copy-trading bot for Hyperliquid: watches specific wallet addresses and mirrors their
trades onto your own account, proportionally sized to your equity, within hard risk limits.

**Status: skeleton only. No orders have been placed - this has never touched real money,
testnet or mainnet.** Separate from [bitcoin-intel-agent](../bitcoin-intel-agent) on
purpose - that project's whole premise is "never executes trades"; this one's job is the
opposite, so they shouldn't share a codebase.

## Safety model

- **Defaults to testnet** (`config.NETWORK = "testnet"`). Mainnet is a deliberate, separate
  decision after a real testnet validation period - not a flag you flip casually.
- **Agent/API wallets only.** Generate one at https://app.hyperliquid.xyz/API. These are
  cryptographically incapable of withdrawing funds - even a compromised key can only trade,
  never move money out. Your main account's private key is never used by this project.
- **Credentials are environment variables, never code, never chat.** `HL_AGENT_PRIVATE_KEY`
  and `HL_ACCOUNT_ADDRESS` - set them yourself, locally. `.env` and anything resembling a
  secret is gitignored.
- **Reading wallets needs no credentials at all** - `monitor.py` uses the same free, public,
  keyless Hyperliquid endpoint as the Watchlist in `bitcoin-intel-agent`. Only placing an
  order (in `executor.py`, not yet implemented) needs the agent wallet.

## Risk limits (current defaults - see `config.py`, confirm/adjust before going further)

- Position sizing: proportional to account size (mirrors the tracked wallet's risk as a %
  of *their* equity, scaled to yours), capped at **3% max risk per trade**
- Max leverage: **5x**, regardless of what the tracked wallet uses
- Max concurrent copied positions: **5**
- Daily loss circuit breaker: **5%** - auto-pause, requires manual re-enable

## Project layout

- `config.py` - network selection, risk limits, credential loading (env vars only)
- `risk.py` - pure position-sizing and circuit-breaker math, no I/O - fully tested without any credentials
- `monitor.py` - read-only wallet polling and position-change detection, no credentials needed
- `executor.py` - order placement - **stub only, not implemented**, pending testnet credentials

## Setup

```
pip install -r requirements.txt
```

Read-only monitoring works right now with zero setup. Order placement isn't built yet.
