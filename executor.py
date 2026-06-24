"""Order placement against Hyperliquid (testnet by default - see config.NETWORK).

Uses the official SDK's Exchange class, signed with the agent wallet's key, acting on
behalf of the master account (config.ACCOUNT_ADDRESS) - the agent never holds funds itself.
"""

import eth_account
from hyperliquid.exchange import Exchange

import config


def make_exchange_client():
    if not config.AGENT_PRIVATE_KEY or not config.ACCOUNT_ADDRESS:
        raise RuntimeError(
            "HL_AGENT_PRIVATE_KEY and HL_ACCOUNT_ADDRESS must be set as environment variables first."
        )
    wallet = eth_account.Account.from_key(config.AGENT_PRIVATE_KEY)
    return Exchange(wallet, config.API_URL, account_address=config.ACCOUNT_ADDRESS)


def place_market_order(coin, is_buy, size, slippage=0.01):
    """Opens (or adds to) a position. Real order against config.API_URL - testnet unless NETWORK changed."""
    exchange = make_exchange_client()
    return exchange.market_open(coin, is_buy, size, slippage=slippage)


def close_position(coin, size=None, slippage=0.01):
    """Closes (all of, or `size` of) an existing position."""
    exchange = make_exchange_client()
    return exchange.market_close(coin, sz=size, slippage=slippage)
