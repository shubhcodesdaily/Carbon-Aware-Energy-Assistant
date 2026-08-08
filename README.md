GreenSlot — Carbon-Aware Energy Assistant
A Live GB Power-Grid Data, Forecasting & Decision Platform

Know exactly when your electricity is greenest — and cheapest — over the next two days, powered by live National Grid data. Not just a chatbot: a real data pipeline, a backtested forecast, and an analyst-style dashboard behind it.

Tech stack: Python · pandas · NumPy · Requests · LangGraph · LangChain · Groq (LLM) · Streamlit · openpyxl · National Grid / NESO Carbon Intensity API · Elexon BMRS Insights API · Git/GitHub

Why I built this

Electricity isn't equally clean — or equally cheap — at every hour. The carbon intensity of the GB grid swings from ~50 gCO₂/kWh overnight to 250+ during the evening peak, and wholesale prices move with it. If you can shift when a flexible load runs — an EV charge, a dishwasher, a batch job — you can cut both emissions and cost without changing what you do.

I wanted to build something past "call an API and print a number" — the system a real energy-aware tool would need:

a live data layer pulling forecasts, prices and the generation mix from official grid sources,
an optimiser that finds the best window for a task, on carbon or price,
a forecasting model that's honestly evaluated against a baseline, not just asserted, and
an analyst-style dashboard with the profile, anomalies and an Excel export a human can actually work from.

It's also a demonstration of engineering judgment: one sliding-window algorithm reused for two problems, defensive parsing against a real third-party API whose schema shifts, and a forecast I can defend as a baseline — knowing exactly where it sits versus a heavier model.

How I built it

Live grid data. A thin client over the NESO Carbon Intensity API (free, no key, GB-only) pulls current intensity, the national generation mix (wind/gas/nuclear…), and a 48-hour half-hourly forecast — national or localised to a postcode. A second client over Elexon's BMRS Insights API pulls the GB wholesale Market Index price (£/MWh) per settlement period, with tolerant parsing that survives Elexon's field-name changes.

Window optimisation. A sliding-window search finds the lowest-average contiguous block of a given length across the forecast. The key design decision: it optimises the metric in the slots — so feeding it carbon gives the greenest window, and feeding it price gives the cheapest window, from the exact same tested function.

Forecasting. Grid intensity is dominated by daily and weekly cycles, so I built a seasonal baseline that learns the average level for each half-hour-of-week from logged history — the standard climatology / seasonal-naive baseline a forecasting analyst starts from. It's evaluated honestly with a time-based hold-out backtest against a persistence (last-value) baseline, reporting MAE, RMSE and sMAPE.

Analysis & anomaly detection. Logged readings are turned into an hour-of-day profile (mean/std per hour), a peak/off-peak spread, and anomaly flags for any reading more than z standard deviations from its own hour-of-day norm — the kind of dislocation worth a second look.

Conversational agent. A small LangGraph loop lets an LLM (via Groq) call the four data tools on its own — current intensity, supply mix, greenest window, cheapest window — and answer in plain English, always using real numbers rather than inventing them.

Reporting. The analysis exports to a formatted Excel workbook (summary, hour-of-day profile with a chart, anomalies with conditional formatting) — the format a non-technical stakeholder can open and build on.

What I gained from building it

An end-to-end system I understand completely — live data in, optimisation and a backtested forecast out, surfaced through both an agent and a dashboard. Direct experience with the unglamorous parts: integrating two independent public APIs, writing parsing that's resilient to schema drift, reusing one algorithm across two problems instead of duplicating it, and evaluating a forecast the honest way (against a baseline, on held-out data) rather than quoting an unqualified accuracy number. And a clear view of the project's real limitations — which I list below rather than hide.

Screenshots
View	Preview
Dashboard overview	docs/screenshots/dashboard.png
Live grid & 48h forecast	docs/screenshots/forecast.png
Greenest / cheapest window finder	docs/screenshots/windows.png
Analysis: hour-of-day profile & anomalies	docs/screenshots/analysis.png
Backtest: actual vs forecast	docs/screenshots/backtest.png
AI assistant chat	docs/screenshots/assistant.png

Replace the docs/screenshots/*.png paths with your actual images once committed.

Architecture
NESO Carbon Intensity API            Elexon BMRS Insights API
(intensity, 48h forecast,            (Market Index price,
 generation mix, by postcode)         £/MWh per settlement period)
        |                                   |
        v                                   v
   carbon_client.py                    price_client.py
        |                                   |
        +----------------+------------------+
                         v
                   carbon_logic.py
        (Slot/Window model, sliding-window search,
         generation-mix parsing)   <-- one search, two uses:
                         |               carbon -> greenest window
                         |               price  -> cheapest window
        +----------------+---------------------------+
        v                                            v
  analysis/                                     agent/graph.py
  timeseries.py  (hour-of-day profile,          (LangGraph loop)
                  anomaly detection, logging)         |
  forecast.py    (seasonal model + backtest)          v
  excel_report.py (formatted .xlsx)             agent_tools.py
        |                                    (4 tools the LLM can call)
        +----------------------+---------------------+
                               v
                      ui/streamlit_ui.py
             (3 tabs: Assistant | Live grid & forecast |
              Analysis & forecast)  ->  run via app.py
Results (forecast backtest, on the bundled sample week)

The seasonal model is evaluated with a 48-hour time-based hold-out against a persistence baseline. On the bundled synthetic sample week (scripts/demo_analysis.py):

Model	MAE	RMSE	sMAPE
Persistence (last value)	59.1	67.8	40.2%
Seasonal (half-hour-of-week)	13.1	17.6	10.7%

That's a ~78% reduction in MAE over the naive baseline across a 48-hour horizon.

⚠️ These figures are on synthetic demo data, included to show the method works. Run the collector to accumulate real logged grid data, then re-run the backtest to get figures for live grid behaviour — they'll be messier, and that's exactly why they're the ones worth quoting.

Features
Live GB carbon intensity — current half-hour, national or by postcode (NESO API)
48-hour half-hourly carbon forecast, national and regional
Live generation (fuel) mix with renewable / low-carbon share — the supply side
Wholesale power price (£/MWh) per settlement period (Elexon BMRS)
Greenest window finder — lowest-carbon block for a task of any length
Cheapest window finder — same optimiser, run on price
Time-series logging → hour-of-day profile, peak/off-peak spread
Anomaly detection (z-score vs hour-of-day norm)
Seasonal forecast with a time-based backtest (MAE / RMSE / sMAPE) vs a persistence baseline
Formatted Excel report (summary, profile chart, conditionally-formatted anomalies)
LangGraph LLM agent (Groq) that calls all four data tools and answers in plain English
Three-tab Streamlit dashboard: AI Assistant · Live grid & forecast · Analysis & forecast
Unit tests for the core window logic and the forecaster
Getting started
bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (source .venv/bin/activate on macOS/Linux)
pip install -r requirements.txt

# run the tests (no network needed)
set PYTHONPATH=.                 # $env:PYTHONPATH="." in PowerShell
python tests/test_carbon_logic.py
python tests/test_forecast.py

# end-to-end analysis + forecast demo -> writes sample_output/grid_analysis.xlsx
python scripts/demo_analysis.py

# launch the dashboard
streamlit run app.py

The AI Assistant tab needs a free Groq API key from console.groq.com/keys — paste it in the sidebar, or set GROQ_API_KEY as an environment variable. The other two tabs work without it.

Honest limitations
The forecast is a seasonal baseline (climatology), not a trained ML model. It's a legitimate, evaluated baseline — but I describe it as one rather than overselling it.
The headline backtest number is currently on synthetic demo data; real figures require logging live data first (see Roadmap).
The Elexon price endpoint is parsed defensively, but field names/paths can change — verify against current Elexon docs. The cheapest-window feature depends on it.
Live features need network access; only the carbon API is key-free (the agent needs a Groq key).
There's no automated collector yet — logging is run manually or via the demo, so a real time-series has to be accumulated before the analysis reflects live behaviour.
Roadmap
Scheduled collector (cron / Task Scheduler) to build a real logged history, then re-run the backtest for genuine live-grid forecast metrics.
Blend the seasonal profile with a recent-level offset to capture short-term drift.
Surface the price series and cheapest-window directly in the dashboard's forecast tab (£/MWh chart).
Deploy to Streamlit Community Cloud with secrets-based key handling.
Add a generation-mix forecast (supply-side outlook), not just intensity.# Carbon-Aware-Energy-Assistant
