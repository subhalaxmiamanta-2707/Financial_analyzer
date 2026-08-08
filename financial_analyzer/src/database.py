# src/database.py
"""
SQLAlchemy-based SQLite persistence with idempotent inserts.
We implement simple ORM classes and helper functions to upsert records.
"""
from __future__ import annotations
from typing import Iterable
import sqlalchemy as sa
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, String, Float, Date, Text, DateTime
import pandas as pd
import numpy as np
from datetime import datetime, timezone
import logging
from .config import load_config
import pathlib

logger = logging.getLogger(__name__)
CONFIG = load_config()

Base = declarative_base()


class Ticker(Base):
    __tablename__ = "tickers"
    id = Column(Integer, primary_key=True)
    ticker = Column(String, unique=True, nullable=False)
    added_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    info = Column(Text)


class DailyMetric(Base):
    __tablename__ = "daily_metrics"
    id = Column(Integer, primary_key=True)
    ticker = Column(String, index=True)
    date = Column(Date, index=True)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Integer)
    sma50 = Column(Float)
    sma200 = Column(Float)
    price_to_book = Column(Float)
    bvps = Column(Float)
    enterprise_value = Column(Float)

    __table_args__ = (sa.UniqueConstraint("ticker", "date", name="u_ticker_date"),)


class SignalEvent(Base):
    __tablename__ = "signal_events"
    id = Column(Integer, primary_key=True)
    ticker = Column(String, index=True)
    date = Column(Date, index=True)
    signal_type = Column(String)
    meta = Column(Text)

    __table_args__ = (sa.UniqueConstraint("ticker", "date", "signal_type", name="u_signal_unique"),)


def get_engine(db_path: str | None = None):
    if db_path is None:
        db_path = CONFIG["database"]["path"]
    db_url = f"sqlite:///{pathlib.Path(db_path).expanduser().as_posix()}"
    engine = sa.create_engine(db_url, echo=False, future=True)
    return engine


def init_db(engine=None):
    engine = engine or get_engine()
    Base.metadata.create_all(engine)


def save_daily_metrics(df: pd.DataFrame, engine=None):
    """
    Save processed metrics to daily_metrics table in an idempotent way.
    """
    engine = engine or get_engine()
    conn = engine.connect()

    df2 = df.copy()
    if "date" in df2.columns:
        df2["date"] = pd.to_datetime(df2["date"]).dt.date

    cols = ["ticker", "date", "open", "high", "low", "close", "volume",
            "sma50", "sma200", "price_to_book", "bvps", "enterprise_value"]
    df2 = df2[[c for c in cols if c in df2.columns]]

    records = df2.to_dict(orient="records")
    if not records:
        logger.warning("No daily metrics to save")
        return

    cleaned_records = []
    for r in records:
        cleaned = {k: (None if (isinstance(v, float) and np.isnan(v)) else v) for k, v in r.items()}
        cleaned_records.append(cleaned)

    with conn.begin():
        for r in cleaned_records:
            sql = f'INSERT OR REPLACE INTO daily_metrics ({", ".join(r.keys())}) VALUES ({", ".join(f":{k}" for k in r.keys())})'
            conn.execute(sa.text(sql), r)


def save_signal_events(ticker: str, events: Iterable[dict], engine=None):
    """
    Save signal events to DB using INSERT OR REPLACE.
    Each event dict must have: date (ISO/string), signal_type, meta (optional)
    """
    engine = engine or get_engine()
    conn = engine.connect()

    with conn.begin():
        for ev in events:
            if not isinstance(ev, dict):
                continue
            d = ev.get("date")
            if isinstance(d, str):
                d = pd.to_datetime(d).date()
            ttype = ev.get("signal_type")
            meta = str(ev.get("meta", {}))
            sql = 'INSERT OR REPLACE INTO signal_events (ticker, date, signal_type, meta) VALUES (:ticker, :date, :signal_type, :meta)'
            conn.execute(sa.text(sql), {"ticker": ticker, "date": d, "signal_type": ttype, "meta": meta})


