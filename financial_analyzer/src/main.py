# src/main.py
from __future__ import annotations
import typer
import logging
import json
import pandas as pd
from datetime import datetime, timezone
from .signals import detect_golden_crossover, detect_death_cross
from .database import init_db, get_engine, save_daily_metrics, save_signal_events
from .config import load_config
from .data_fetcher import fetch_stock_data
from .processor import process_data

app = typer.Typer(help="Financial Analyzer CLI tool for analyzing stocks.")
logger = logging.getLogger("financial_analyzer")


def setup_logging(cfg):
    level = cfg.get("logging", {}).get("level", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        force=True,
    )


@app.callback()
def callback():
    """
    Financial Analyzer CLI.
    """
    pass


@app.command("run")
def run(
    ticker: str = typer.Option(..., help="Ticker symbol e.g. NVDA, AAPL, RELIANCE.NS"),
    output: str = typer.Option("analysis.json", help="Output JSON file"),
    initdb: bool = typer.Option(True, help="Initialize DB tables if needed")
):
    """
    Run full pipeline for a single ticker:
      1. Init DB
      2. Fetch and validate data
      3. Process metrics
      4. Detect signals
      5. Save to DB and JSON
      6. Log success/failure
    """
    cfg = load_config()
    setup_logging(cfg)

    logger.info("Starting pipeline for %s", ticker)

    # Initialize DB if requested
    if initdb:
        engine = get_engine()
        init_db(engine)
        logger.info("Database initialized")

    raw = fetch_stock_data(ticker)
    processed = process_data(raw)
  
    processed = processed.assign(
        date=pd.to_datetime(processed["date"]).dt.tz_localize(None)
    )
    # Detect signals
    logger.info("Detecting signals...")
    golden_dates = detect_golden_crossover(processed.assign(date=pd.to_datetime(processed["date"])))
    death_dates = detect_death_cross(processed.assign(date=pd.to_datetime(processed["date"])))
    logger.info("Signals detected: %d golden, %d death", len(golden_dates), len(death_dates))

    # Convert signal dates to ISO strings to ensure DB compatibility
    events = []
    for d in golden_dates:
        events.append({"date": pd.to_datetime(d).isoformat(), "signal_type": "golden_cross", "meta": {}})
    for d in death_dates:
        events.append({"date": pd.to_datetime(d).isoformat(), "signal_type": "death_cross", "meta": {}})

    # Save to DB
    engine = get_engine()
    save_daily_metrics(processed.assign(date=pd.to_datetime(processed["date"])), engine=engine)
    save_signal_events(ticker, events, engine=engine)

    # Export JSON summary
    payload = {
        "ticker": ticker,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "price_rows_count": int(len(processed)),
        "fundamentals_used": raw.get("source_info", {}).get("used", "unknown"),
        "signals": events,
    }
    with open(output, "w", encoding="utf8") as f:
        json.dump(payload, f, indent=2)

    logger.info("Finished. JSON exported to %s", output)


if __name__ == "__main__":
    app()

