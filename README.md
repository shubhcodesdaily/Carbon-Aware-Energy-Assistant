
<img width="535" height="79" alt="image" src="https://github.com/user-attachments/assets/c61973e1-5619-406d-8de2-e6291fec1ca4" />

# GreenSlot — Carbon-Aware Energy Assistant

### A Live GB Grid Forecasting & Decision Platform



### Tech stack

Python · pandas · NumPy · Requests · LangGraph · LangChain · Groq · Streamlit · openpyxl · NESO Carbon Intensity API · Elexon BMRS · Git/GitHub

## Why I built this

The GB grid isn't equally clean at every hour — carbon intensity swings from ~50 gCO₂/kWh overnight to 250+ in the evening peak, and wholesale prices move with it. Shift *when* a flexible load runs — an EV charge, a dishwasher, a batch job — and you cut both emissions and cost without changing what you actually do.

I didn't want to stop at "call an API, print a number." I wanted the thing an energy-aware tool would really need: a live data layer, an optimiser that finds the best window on carbon *or* price, a forecast I could actually defend, and a dashboard a human could work from. It's as much about engineering judgment as the result — one algorithm reused for two jobs, parsing that survives a flaky third-party API, and a forecast I call a *baseline* because that's honestly what it is.

## How I built it

**Live grid data.** A thin client over the NESO Carbon Intensity API (free, no key) pulls current intensity, the generation mix, and a 48-hour half-hourly forecast — national or by postcode. A second client over Elexon's BMRS pulls the wholesale price (£/MWh) per settlement period, parsed defensively so Elexon's field-name changes don't break it.

**One optimiser, two jobs.** A sliding-window search finds the lowest-average block of a given length. It optimises whatever metric sits in the data — feed it carbon and you get the **greenest** window; feed it price and you get the **cheapest** — from the exact same tested function.

**Forecasting.** Grid intensity is ruled by daily and weekly cycles, so I learn the average level for each half-hour-of-week from logged history — a proper seasonal baseline. I evaluate it honestly with a time-based hold-out **backtest** against a persistence baseline (MAE, RMSE, sMAPE), rather than quoting an unqualified accuracy number.

**Analysis.** Logged readings become an hour-of-day profile, a peak/off-peak spread, and **anomaly flags** for anything more than *z* standard deviations from its own hour-of-day norm.

**Agent.** A small LangGraph loop lets an LLM (via Groq) call the four data tools itself and answer in plain English — always from real numbers, never invented ones.

**Reporting.** The analysis exports to a formatted Excel workbook (summary, profile chart, conditionally-formatted anomalies) — something a non-technical stakeholder can open.

## What I gained from building it

A system I understand end to end — live data in, optimisation and a backtested forecast out, surfaced through both a chat agent and a dashboard. Real practice with the unglamorous parts: wiring two independent public APIs together, writing parsing that survives schema drift, reusing one algorithm instead of copy-pasting it, and evaluating a forecast the honest way. And a clear-eyed list of what it still can't do, which I've kept in rather than hidden.

## Screenshots

**Dashboard overview**

<img width="708" height="140" alt="image" src="https://github.com/user-attachments/assets/686d6e9b-d2d8-451e-ac5a-092ec5783439" />


**Live grid & 48h forecast**

<img width="1483" height="733" alt="image" src="https://github.com/user-attachments/assets/53e9939b-166e-45fa-8baf-d170227436bb" />

<img width="1480" height="562" alt="image" src="https://github.com/user-attachments/assets/6d2d519a-d10a-4ae5-9c5f-83db8944e0bf" />

**Greenest / cheapest window**

<img width="1033" height="267" alt="image" src="https://github.com/user-attachments/assets/11c2b2bb-d13d-44c1-914e-3bbe8ffe7a12" />


**Analysis: profile & anomalies**

<img width="1471" height="859" alt="image" src="https://github.com/user-attachments/assets/5d59a80e-af56-4dff-b49e-35180fbb9394" />


**Backtest: actual vs forecast**

<img width="1405" height="177" alt="image" src="https://github.com/user-attachments/assets/353379ee-5a36-4ba0-a947-97b418a13184" />


**AI assistant**

<img width="1072" height="868" alt="image" src="https://github.com/user-attachments/assets/1fff84c9-5ee0-45db-8fd5-a9e6951d5e1c" />


## Architecture

```
NESO Carbon Intensity API          Elexon BMRS Insights API
(intensity, 48h forecast,          (Market Index price,
 generation mix, by postcode)       £/MWh per settlement period)
        |                                 |
        v                                 v
   carbon_client.py                  price_client.py
        |                                 |
        +---------------+-----------------+
                        v
                  carbon_logic.py
        (Slot/Window model, sliding-window search)
                        |   one search, two uses:
                        |   carbon -> greenest window
                        |   price  -> cheapest window
        +---------------+------------------------+
        v                                        v
  analysis/                                 agent/graph.py
  timeseries.py  (profile, anomalies)       (LangGraph loop)
  forecast.py    (seasonal + backtest)            |
  excel_report.py (formatted .xlsx)               v
        |                                    agent_tools.py
        +----------------+-------------------(4 LLM tools)
                         v
                 ui/streamlit_ui.py
        (Assistant | Live grid & forecast | Analysis)
                run via  app.py
```

> **An honest note:** there's no automated collector yet — logging is run manually or via the demo — so a real time-series has to accumulate before the analysis reflects live grid behaviour. I know exactly how I'd schedule it (see Roadmap); I prioritised getting the pipeline right first.

## Results (forecast backtest, on the bundled sample week)

Seasonal model vs a persistence baseline, 48-hour time-based hold-out:

| Model | MAE | RMSE | sMAPE |
|---|---|---|---|
| Persistence (last value) | 59.1 | 67.8 | 40.2% |
| **Seasonal (half-hour-of-week)** | **13.1** | **17.6** | **10.7%** |

That's a **~78% cut in MAE** over the naive baseline across a 48-hour horizon.

> These numbers are on the **synthetic sample week** shipped with the repo, included to show the method works. Log real grid data and re-run the backtest for live figures — they'll be messier, which is exactly why they're the ones worth quoting.

## Feature list

- Live GB carbon intensity — national or by postcode
- 48-hour half-hourly carbon forecast, national and regional
- Live generation mix with renewable / low-carbon share
- Wholesale power price (£/MWh) per settlement period (Elexon)
- Greenest-window finder (lowest carbon for a task of any length)
- Cheapest-window finder (same optimiser, run on price)
- Hour-of-day profile, peak/off-peak spread
- Anomaly detection (z-score vs hour-of-day norm)
- Seasonal forecast with a backtest vs persistence (MAE / RMSE / sMAPE)
- Formatted Excel report (summary, profile chart, anomalies)
- LangGraph LLM agent (Groq) calling all four tools in plain English
- Three-tab Streamlit dashboard, run via `app.py`
- Unit tests for the window logic and the forecaster

## Getting started

```bash
python -m venv .venv
.venv\Scripts\activate                 # source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt

$env:PYTHONPATH="."                     # set PYTHONPATH=.  on cmd
python tests/test_forecast.py           # expect 4/4
python scripts/demo_analysis.py         # writes sample_output/grid_analysis.xlsx
streamlit run app.py
```

The Assistant tab needs a free Groq key ([console.groq.com/keys](https://console.groq.com/keys)) in the sidebar or as `GROQ_API_KEY`. The other two tabs work without it.

## Honest limitations

- The forecast is a **seasonal baseline**, not a trained ML model — a real, evaluated baseline, but I call it what it is.
- The headline backtest number is on **synthetic demo data**; real figures need real logged data first.
- The Elexon price endpoint is parsed defensively, but paths/fields can change — verify against current docs. The cheapest-window feature depends on it.
- Live features need network; only the carbon API is key-free (the agent needs a Groq key).
- No scheduled collector yet — logging is manual/demo for now.

## Roadmap

- Scheduled collector (cron / Task Scheduler) to build real history, then re-run the backtest for live metrics.
- Blend the seasonal profile with a recent-level offset for short-term drift.
- Surface the price series and cheapest window in the dashboard's forecast tab.
- Deploy to Streamlit Community Cloud with secrets-based key handling.
- Add a generation-mix (supply-side) forecast, not just intensity.
