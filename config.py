"""All config in one place. Defaults to testnet - mainnet requires deliberately changing NETWORK."""

import os

from hyperliquid.utils import constants

NETWORK = "testnet"  # change to "mainnet" only after a real testnet validation period
API_URL = constants.TESTNET_API_URL if NETWORK == "testnet" else constants.MAINNET_API_URL

# Never hardcode these. Set as environment variables on your own machine, never in chat or in this repo.
AGENT_PRIVATE_KEY = os.environ.get("HL_AGENT_PRIVATE_KEY")
ACCOUNT_ADDRESS = os.environ.get("HL_ACCOUNT_ADDRESS")

MAX_RISK_PCT_PER_TRADE = 3.0  # never risk more than this % of account equity on one copied trade
MAX_LEVERAGE = 5  # caps our own leverage regardless of what the tracked wallet uses
MAX_CONCURRENT_POSITIONS = 5
DAILY_LOSS_CIRCUIT_BREAKER_PCT = 5.0  # auto-pause and require manual re-enable past this daily loss
