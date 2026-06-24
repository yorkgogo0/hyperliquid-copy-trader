"""Shared start/stop + leverage control - the dashboard writes to this file, the running
bot loop reads it every cycle. Decouples the dashboard (a Streamlit request/response app,
not naturally suited to hosting a long-running loop itself) from the actual bot process."""

import json
import os

CONTROL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_control.json")
ALLOWED_LEVERAGES = [1, 2, 5, 10]
DEFAULT_STATE = {"running": True, "leverage": 5}


def read_control():
    if not os.path.exists(CONTROL_FILE):
        return dict(DEFAULT_STATE)
    try:
        with open(CONTROL_FILE) as f:
            state = json.load(f)
        return {**DEFAULT_STATE, **state}
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_STATE)


def write_control(running=None, leverage=None):
    state = read_control()
    if running is not None:
        state["running"] = running
    if leverage is not None:
        if leverage not in ALLOWED_LEVERAGES:
            raise ValueError(f"leverage must be one of {ALLOWED_LEVERAGES}, got {leverage}")
        state["leverage"] = leverage
    with open(CONTROL_FILE, "w") as f:
        json.dump(state, f)
    return state
