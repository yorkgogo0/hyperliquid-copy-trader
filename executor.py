"""Order placement against Hyperliquid (testnet by default - see config.NETWORK).

Uses the official SDK's Exchange class, signed with the agent wallet's key, acting on
behalf of the master account (config.ACCOUNT_ADDRESS) - the agent never holds funds itself.
"""

import eth_account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info

import config

_sz_decimals_cache = {}


def make_exchange_client():
    if not config.AGENT_PRIVATE_KEY or not config.ACCOUNT_ADDRESS:
        raise RuntimeError(
            "HL_AGENT_PRIVATE_KEY and HL_ACCOUNT_ADDRESS must be set as environment variables first."
        )
    wallet = eth_account.Account.from_key(config.AGENT_PRIVATE_KEY)
    return Exchange(wallet, config.API_URL, account_address=config.ACCOUNT_ADDRESS)


def round_size(coin, size):
    """Hyperliquid rejects order sizes with more decimal places than the asset allows
    (e.g. HYPE/SOL allow 2, BTC allows 5) - caught live when a real 2.1646...-sized HYPE
    order was rejected with 'float_to_wire causes rounding'."""
    if coin not in _sz_decimals_cache:
        info = Info(config.API_URL, skip_ws=True)
        for asset in info.meta()["universe"]:
            _sz_decimals_cache[asset["name"]] = asset["szDecimals"]
    decimals = _sz_decimals_cache.get(coin, 3)
    return round(size, decimals)


DEFAULT_SLIPPAGE = 0.03  # testnet liquidity is consistently thin - 1% repeatedly failed to
# fully fill or even match at all on real test orders; closing a position is risk-management-
# critical, so a stop that can't execute due to tight slippage is a real failure, not a detail.


def place_market_order(coin, is_buy, size, leverage=None, slippage=DEFAULT_SLIPPAGE):
    """Opens (or adds to) a position. Real order against config.API_URL - testnet unless NETWORK changed.
    Pass `leverage` to set it explicitly first - otherwise the exchange uses whatever was
    last configured for this coin on this account, which may not match what the caller's
    sizing math assumed (caught live: a position opened at ~10x when the code assumed 5x,
    because leverage was never being set before the order)."""
    exchange = make_exchange_client()
    if leverage is not None:
        exchange.update_leverage(leverage, coin, True)
    return exchange.market_open(coin, is_buy, round_size(coin, size), slippage=slippage)


def close_position(coin, size=None, slippage=DEFAULT_SLIPPAGE):
    """Closes (all of, or `size` of) an existing position."""
    exchange = make_exchange_client()
    rounded_size = round_size(coin, size) if size is not None else None
    return exchange.market_close(coin, sz=rounded_size, slippage=slippage)
