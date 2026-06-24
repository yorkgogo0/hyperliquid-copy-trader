"""Live dashboard for the copy-trading bot. Run with: streamlit run dashboard.py

Main menu: account overview. Bot Control: start/stop the running strategy loop and set its
leverage - this page writes to bot_control.json, it doesn't run the loop itself (Streamlit's
request/response model isn't suited to hosting a long-running process; solo_bot.py/bot.py
run as their own separate process and just read this file every cycle). Trade Journal: every
trade the bot has placed, with the reasoning that justified entry and an outcome note once
closed.
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import bot_control
import config
import journal
import monitor

st.set_page_config(page_title="Copy-Trader", layout="wide")
st.title("Hyperliquid Copy-Trader")
st.caption(f"Network: {config.NETWORK}. Read-only account view + trade journal - this page never places an order.")

page = st.sidebar.radio("Menu", ["Account Overview", "Bot Control", "Trade Journal"])

if page == "Bot Control":
    st.subheader("Bot Control")
    st.caption(
        "Controls whichever bot process is actually running (solo_bot.py or bot.py) - this "
        "page doesn't start the process itself, it just changes what an already-running one does."
    )
    control = bot_control.read_control()

    running = st.toggle("Trading enabled", value=control["running"])
    if running != control["running"]:
        bot_control.write_control(running=running)
        st.rerun()

    if running:
        st.success("Running - will open new positions on confirmed signals.")
    else:
        st.warning("Paused - will NOT open new positions, but still manages exits on anything already open.")

    st.divider()
    st.write("**Leverage for new positions** (doesn't affect positions already open)")
    leverage = st.radio(
        "Leverage", bot_control.ALLOWED_LEVERAGES,
        index=bot_control.ALLOWED_LEVERAGES.index(control["leverage"]),
        format_func=lambda x: f"{x}x", horizontal=True,
    )
    if leverage != control["leverage"]:
        bot_control.write_control(leverage=leverage)
        st.rerun()

    st.caption(f"Current: {'Running' if control['running'] else 'Paused'}, {control['leverage']}x leverage on new positions.")

elif page == "Account Overview":
    if st.button("Refresh"):
        st.rerun()
    if not config.ACCOUNT_ADDRESS:
        st.error("HL_ACCOUNT_ADDRESS isn't set.")
    else:
        info = monitor.make_info_client()
        state = monitor.fetch_wallet_state(info, config.ACCOUNT_ADDRESS)
        st.metric("Account Value", f"${state['account_value']:,.2f}")
        if state["positions"]:
            st.subheader("Open Positions")
            st.dataframe(pd.DataFrame.from_dict(state["positions"], orient="index"), use_container_width=True)
        else:
            st.caption("No open positions right now.")

else:
    st.subheader("Trade Journal")
    rows = journal.load_journal()
    if not rows:
        st.caption("No trades logged yet - the bot hasn't copied anything.")
    else:
        df = pd.DataFrame(rows)
        closed = df[df["closed_at"] != ""]

        cols = st.columns(3)
        cols[0].metric("Total Trades", len(df))
        if len(closed) > 0:
            wins = (closed["pnl_usd"].astype(float) > 0).sum()
            cols[1].metric("Win Rate", f"{wins / len(closed) * 100:.0f}%  ({wins}/{len(closed)})")
            cols[2].metric("Total P&L", f"${closed['pnl_usd'].astype(float).sum():+,.2f}")

            closed_sorted = closed.copy()
            closed_sorted["cum_pnl"] = closed_sorted["pnl_usd"].astype(float).cumsum()
            fig = go.Figure(go.Scatter(x=range(len(closed_sorted)), y=closed_sorted["cum_pnl"], mode="lines+markers"))
            fig.update_layout(title="Cumulative P&L by closed trade", height=300, margin=dict(l=10, r=10, t=40, b=10))
            st.plotly_chart(fig, use_container_width=True)
        else:
            cols[1].metric("Win Rate", "-")
            cols[2].metric("Total P&L", "-")

        st.divider()
        for _, row in df[::-1].iterrows():
            status = "OPEN" if not row["closed_at"] else ("WIN" if float(row["pnl_usd"] or 0) > 0 else "LOSS")
            with st.expander(f"{row['opened_at']} - {row['side']} {row['coin']} - {status}"):
                st.write(f"**Whale tracked:** {row['whale_address']}")
                st.write(f"**Entry:** ${float(row['entry_price']):,.4f} | **Size:** {row['size']}")
                if row["closed_at"]:
                    st.write(f"**Exit:** ${float(row['exit_price']):,.4f} | **P&L:** ${float(row['pnl_usd']):+,.2f} ({float(row['pnl_pct']):+.2f}%)")
                st.write("**Confirmation reasoning at entry:**")
                for r in row["confirmation_reasoning"].split(" | "):
                    st.write(f"- {r}")
                if row["outcome_note"]:
                    st.info(row["outcome_note"])
