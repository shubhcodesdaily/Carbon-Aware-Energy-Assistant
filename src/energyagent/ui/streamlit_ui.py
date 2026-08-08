"""Streamlit dashboard for the Carbon-Aware Energy Assistant (GreenSlot).

Three tabs:
  1. AI Assistant       - chat with the LangGraph agent (needs a Groq key)
  2. Live grid & forecast - current intensity, supply mix, 48h forecast, and the
                            greenest / cheapest window finders (live API calls)
  3. Analysis & forecast  - hour-of-day profile, anomalies, a backtested seasonal
                            forecast, and an Excel export (runs on logged data)

Live API calls are wrapped so a failed fetch shows a message instead of crashing.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

from src.energyagent.tools import carbon_client, price_client
from src.energyagent.tools.carbon_logic import (
    Slot, find_greenest_window, parse_forecast, describe_window,
    parse_generation_mix, renewable_share, low_carbon_share,
)
from src.energyagent.analysis.timeseries import (
    load_log, append_slots_to_log, hour_of_day_profile, peak_offpeak_summary,
    detect_anomalies, UK_TZ,
)
from src.energyagent.analysis.forecast import backtest
from src.energyagent.analysis.excel_report import build_excel_report

PROJECT_ROOT = Path(__file__).resolve().parents[3]
LOG_PATH = PROJECT_ROOT / "sample_output" / "intensity_log.csv"


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _get_api_key() -> str | None:
    """Groq key from Streamlit secrets (Cloud) or the sidebar."""
    try:
        if "GROQ_API_KEY" in st.secrets:
            return st.secrets["GROQ_API_KEY"]
    except Exception:
        pass
    return st.sidebar.text_input("Groq API key", type="password") or None


def _forecast_to_frame(slots: list[Slot]) -> pd.DataFrame:
    """Slots -> frame indexed by UK local time for charting."""
    rows = [
        {"time": s.start.astimezone(UK_TZ).replace(tzinfo=None),
         "gCO2/kWh": s.intensity}
        for s in slots if s.intensity is not None
    ]
    return pd.DataFrame(rows).set_index("time")


def _synthetic_week() -> list[Slot]:
    """A week of half-hourly slots for demo/analysis when no real log exists."""
    random.seed(7)
    start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) \
        - timedelta(days=7)
    slots = []
    for i in range(48 * 7):
        t = start + timedelta(minutes=30 * i)
        hour = t.hour + t.minute / 60
        base = 160 + 90 * math.sin((hour - 10) / 24 * 2 * math.pi)
        weekend = -30 if t.weekday() >= 5 else 0
        value = max(20, base + weekend + random.gauss(0, 12))
        slots.append(Slot(t, t + timedelta(minutes=30), round(value), None))
    return slots


# --------------------------------------------------------------------------
# Tab 1 - AI assistant
# --------------------------------------------------------------------------

def render_assistant() -> None:
    st.subheader("Ask the assistant")
    api_key = _get_api_key()
    if not api_key:
        st.info("Add a free Groq API key in the sidebar to chat with the assistant. "
                "The other two tabs work without it.")
        return

    from langchain_core.messages import HumanMessage, SystemMessage
    from src.energyagent.agent.graph import SYSTEM_PROMPT, build_agent

    if "history" not in st.session_state:
        st.session_state.history = []
    for role, text in st.session_state.history:
        st.chat_message(role).write(text)

    prompt = st.chat_input("e.g. Greenest 2-hour window to run my washing machine?")
    if not prompt:
        return
    st.session_state.history.append(("user", prompt))
    st.chat_message("user").write(prompt)

    try:
        agent = build_agent(api_key=api_key)
        messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)]
        with st.spinner("Checking the grid..."):
            result = agent.invoke({"messages": messages})
        answer = result["messages"][-1].content
    except Exception as exc:
        answer = f"Sorry - the assistant hit an error: {exc}"
    st.session_state.history.append(("assistant", answer))
    st.chat_message("assistant").write(answer)


# --------------------------------------------------------------------------
# Tab 2 - live grid & forecast
# --------------------------------------------------------------------------

def render_live() -> None:
    st.subheader("Live grid snapshot")

    try:
        cur = carbon_client.get_current_intensity()
        block = cur["data"][0]["intensity"]
        value = block.get("actual") or block.get("forecast")
        index = block.get("index", "-")
    except Exception as exc:
        value, index = None, "-"
        st.warning(f"Could not fetch current intensity: {exc}")

    try:
        mix = parse_generation_mix(carbon_client.get_generation_mix())
    except Exception as exc:
        mix = {}
        st.warning(f"Could not fetch the generation mix: {exc}")

    c1, c2, c3 = st.columns(3)
    c1.metric("Current intensity", f"{value} gCO2/kWh" if value is not None else "-",
              index if value is not None else None)
    c2.metric("Renewable share", f"{renewable_share(mix):.0f}%" if mix else "-")
    c3.metric("Low-carbon share", f"{low_carbon_share(mix):.0f}%" if mix else "-")

    if mix:
        st.caption("Generation mix (%) - the supply side")
        st.bar_chart(pd.DataFrame({"%": mix}).sort_values("%", ascending=False))

    st.divider()
    st.subheader("48-hour carbon forecast")
    postcode = st.text_input("Regional postcode (optional, e.g. CV1)", "")
    try:
        if postcode.strip():
            payload = carbon_client.get_regional_forecast_48h(postcode)
        else:
            payload = carbon_client.get_national_forecast_48h()
        slots = parse_forecast(payload)
        frame = _forecast_to_frame(slots)
        if not frame.empty:
            st.line_chart(frame)
            st.session_state["forecast_slots"] = slots
    except Exception as exc:
        st.warning(f"Could not fetch the forecast: {exc}")

    st.divider()
    st.subheader("Find the best window")
    hours = st.number_input("How long is your task (hours)?", 0.5, 12.0, 2.0, 0.5)
    col_g, col_c = st.columns(2)

    with col_g:
        if st.button("Greenest window"):
            slots = st.session_state.get("forecast_slots")
            try:
                if not slots:
                    slots = parse_forecast(carbon_client.get_national_forecast_48h())
                window = find_greenest_window(slots, hours=hours)
                st.success(describe_window(window, hours=hours))
            except Exception as exc:
                st.warning(f"Could not compute greenest window: {exc}")

    with col_c:
        if st.button("Cheapest window (price)"):
            try:
                pslots = price_client.parse_price_series(
                    price_client.get_market_index_price(hours=48))
                window = find_greenest_window(pslots, hours=hours)
                st.success(describe_window(window, hours=hours, unit="GBP/MWh"))
            except Exception as exc:
                st.warning(f"Could not compute cheapest window: {exc}")


# --------------------------------------------------------------------------
# Tab 3 - analysis & forecast (offline, on logged data)
# --------------------------------------------------------------------------

def _load_analysis_df() -> pd.DataFrame | None:
    upload = st.file_uploader("Upload a log CSV (columns: start_utc, value)", type="csv")
    if upload is not None:
        df = pd.read_csv(upload)
        df["start_utc"] = pd.to_datetime(df["start_utc"], utc=True)
        df["hour_uk"] = df["start_utc"].dt.tz_convert(UK_TZ).dt.hour
        return df
    if LOG_PATH.exists():
        return load_log(LOG_PATH)
    st.info("No logged data yet. Generate a sample week to explore the analysis, "
            "or run the collector to log real grid data.")
    if st.button("Generate sample week"):
        LOG_PATH.parent.mkdir(exist_ok=True)
        append_slots_to_log(_synthetic_week(), LOG_PATH)
        st.rerun()
    return None


def render_analysis() -> None:
    st.subheader("Time-series analysis")
    df = _load_analysis_df()
    if df is None or df.empty:
        return

    summary = peak_offpeak_summary(df)
    if summary:
        a, b, c = st.columns(3)
        a.metric("Cleanest hour (UK)", f"{summary['best_hour']:02d}:00",
                 f"{summary['best_mean']:.0f}")
        b.metric("Dirtiest hour (UK)", f"{summary['worst_hour']:02d}:00",
                 f"{summary['worst_mean']:.0f}")
        c.metric("Peak-trough spread", f"{summary['spread']:.0f} gCO2/kWh")

    st.caption("Average intensity by hour of day")
    prof = hour_of_day_profile(df).set_index("hour_uk")[["mean"]]
    st.line_chart(prof)

    st.caption("Anomalies (readings far from their hour-of-day norm)")
    anoms = detect_anomalies(df, z=2.5)
    if not anoms.empty:
        st.dataframe(anoms, use_container_width=True)
    else:
        st.write("No anomalies at |z| >= 2.5.")

    st.divider()
    st.subheader("Forecast (seasonal baseline)")
    try:
        bt = backtest(df, test_hours=48)
        m1, m2, m3 = st.columns(3)
        m1.metric("Seasonal MAE", bt["seasonal"]["mae"])
        m2.metric("Persistence MAE", bt["persistence"]["mae"])
        m3.metric("Improvement", f"{bt['mae_improvement_pct']}%")

        frame = bt["frame"].copy()
        frame["time"] = frame["start_utc"].dt.tz_convert(UK_TZ).dt.tz_localize(None)
        chart = frame.set_index("time")[["actual", "forecast_seasonal"]]
        st.caption("Backtest: actual vs seasonal forecast (48h hold-out)")
        st.line_chart(chart)
    except Exception as exc:
        st.warning(f"Not enough data to backtest yet: {exc}")

    st.divider()
    st.subheader("Download")
    if st.button("Build Excel report"):
        out_path = PROJECT_ROOT / "sample_output" / "grid_analysis.xlsx"
        build_excel_report(df, out_path, z=2.5)
        with open(out_path, "rb") as fh:
            data = fh.read()
        st.download_button(
            "Download grid_analysis.xlsx", data, file_name="grid_analysis.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(page_title="GreenSlot - Carbon-Aware Energy",
                       page_icon="🌱", layout="wide")
    st.title("🌱 GreenSlot")
    st.write("Know when your electricity is greenest and cheapest over the next "
             "two days, powered by live National Grid data.")

    tab1, tab2, tab3 = st.tabs(
        ["💬 AI Assistant", "⚡ Live grid & forecast", "📊 Analysis & forecast"])
    with tab1:
        render_assistant()
    with tab2:
        render_live()
    with tab3:
        render_analysis()


if __name__ == "__main__":
    main()