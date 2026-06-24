"""Smart-money confirmation gate.

Before copying any whale trade, this requires bitcoin-intel-agent's own independent
analysis to agree with the direction. If it doesn't (or the coin isn't covered), the trade
is declined - never blindly mirrored just because a tracked wallet did it.
"""

import os
import sys

_BITCOIN_INTEL_AGENT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bitcoin-intel-agent")
if _BITCOIN_INTEL_AGENT_PATH not in sys.path:
    sys.path.insert(0, _BITCOIN_INTEL_AGENT_PATH)

from bitcoin_intel_agent import run_analysis  # noqa: E402

SUPPORTED_COINS = {"BTC", "ETH", "SOL", "HYPE"}


def confirm_direction(coin, side):
    """`side` is 'Long' or 'Short' - the direction the whale just took.
    Returns (confirmed: bool, reasoning: list[str], report: dict|None)."""
    if coin not in SUPPORTED_COINS:
        return False, [f"{coin} isn't covered by bitcoin-intel-agent's analysis - no independent evidence available"], None

    report = run_analysis(coin)
    confirmed = report["bias"] == side
    if confirmed:
        reasoning = report["supporting_signals"]
    elif report["conflicting_signals"]:
        reasoning = report["conflicting_signals"]
    else:
        reasoning = [f"Independent analysis says '{report['bias']}', not '{side}' - no evidence for this direction"]
    return confirmed, reasoning, report
