"""Order placement - NOT YET WIRED UP OR TESTED.

This is intentionally a stub. Placing real orders requires a testnet agent wallet
(HL_AGENT_PRIVATE_KEY, HL_ACCOUNT_ADDRESS env vars) which we don't have yet, and I won't
write untested code for the highest-stakes part of this project. Once those env vars are
set, this gets built out using hyperliquid.exchange.Exchange and verified against testnet
before anything else changes.
"""

import config


def make_exchange_client():
    if not config.AGENT_PRIVATE_KEY or not config.ACCOUNT_ADDRESS:
        raise RuntimeError(
            "HL_AGENT_PRIVATE_KEY and HL_ACCOUNT_ADDRESS must be set as environment variables "
            "before any order can be placed. Not yet configured."
        )
    raise NotImplementedError("Order placement is not implemented yet - see module docstring.")
