# src/data_fetcher.py
"""
Data ingestion: fetch_stock_data(ticker) -> dict
Uses yfinance and Pydantic models for validation and fallback strategies.
"""
from __future__ import annotations
import logging
from typing import Dict, Any, List
import yfinance as yf
from datetime import datetime, timezone
from decimal import Decimal
import pandas as pd
from .models import FundamentalsQuarter
from .config import load_config

logger = logging.getLogger(__name__)
CONFIG = load_config()


def _decimal_or_none(x) -> Decimal | None:
    if x is None or pd.isna(x):
        return None
    try:
        return Decimal(str(x))
    except Exception:
        return None


def _get_series_val(col_data: pd.Series, keys: List[str]) -> Decimal | None:
    if col_data is None or not hasattr(col_data, "index"):
        return None
    for k in keys:
        if k in col_data.index:
            val = col_data[k]
            if pd.notna(val):
                res = _decimal_or_none(val)
                if res is not None:
                    return res
    return None


EQUITY_KEYS = [
    "Stockholders Equity",
    "Total Stockholder Equity",
    "Stockholder Equity",
    "Common Stock Equity",
    "Total Equity Gross Minority Interest",
    "Total Assets",
]

DEBT_KEYS = [
    "Total Debt",
    "Net Debt",
    "Long Term Debt",
    "Capital Lease Obligations",
    "Total Liabilities Net Minor Interest",
]

CASH_KEYS = [
    "Cash Cash Equivalents And Short Term Investments",
    "Cash And Cash Equivalents",
    "Cash Financial",
    "Cash",
]

SHARES_KEYS = [
    "Ordinary Shares Number",
    "Share Issued",
    "Common Stock Shares Outstanding",
]


def fetch_stock_data(ticker: str, period: str | None = None) -> Dict[str, Any]:
    """
    Fetch price history and fundamental snapshots for ticker.

    Returns raw dict:
      {
        "ticker": "NVDA",
        "prices": pd.DataFrame,
        "fundamentals": list[FundamentalsQuarter dicts],
        "source_info": {"used": "...", "notes": "..."}
      }
    """
    if period is None:
        period = CONFIG["data_settings"].get("historical_period", "5y")

    logger.info("Fetching %s with period=%s", ticker, period)
    t = yf.Ticker(ticker)

    # 1) Fetch prices
    try:
        prices = t.history(period=period, auto_adjust=False)
    except Exception as e:
        logger.exception("Failed to fetch price history for %s: %s", ticker, e)
        raise

    if prices is None or prices.empty:
        raise ValueError(f"No price data returned for ticker '{ticker}'")

    prices = prices.rename_axis("date").reset_index()
    prices.columns = [c.lower().replace(" ", "_") for c in prices.columns]

    # Fetch info once for supplemental fallback values
    info = {}
    try:
        info = t.info or {}
    except Exception:
        logger.debug("Could not fetch info for %s", ticker)

    info_shares = _decimal_or_none(info.get("sharesOutstanding") or info.get("impliedSharesOutstanding"))
    info_market_cap = _decimal_or_none(info.get("marketCap"))
    info_debt = _decimal_or_none(info.get("totalDebt"))
    info_cash = _decimal_or_none(info.get("totalCash") or info.get("cash"))

    # Calculate equity fallback from info if available
    info_equity = None
    if info.get("bookValue") is not None and info_shares is not None:
        try:
            info_equity = Decimal(str(info["bookValue"])) * info_shares
        except Exception:
            pass
    if info_equity is None:
        info_equity = _decimal_or_none(info.get("totalStockholderEquity") or info.get("totalAssets"))

    # 2) Fetch fundamentals with fallback strategy
    source_used = None
    fundamentals = []

    # Try quarterly financials
    try:
        qb = t.quarterly_balance_sheet
        if qb is not None and getattr(qb, "empty", True) is False:
            source_used = "quarterly_balance_sheet"
            for col in qb.columns:
                col_data = qb[col]
                equity = _get_series_val(col_data, EQUITY_KEYS) or info_equity
                debt = _get_series_val(col_data, DEBT_KEYS) or info_debt
                cash = _get_series_val(col_data, CASH_KEYS) or info_cash
                shares = _get_series_val(col_data, SHARES_KEYS) or info_shares

                f = FundamentalsQuarter(
                    as_of=str(col),
                    total_stockholder_equity=equity,
                    cash_and_cash_equivalents=cash,
                    total_debt=debt,
                    shares_outstanding=shares,
                    market_cap=info_market_cap,
                    extra={"raw_column": str(col)},
                )
                fundamentals.append(f.model_dump())
    except Exception as ex:
        logger.debug("quarterly_balance_sheet not usable for %s: %s", ticker, ex)

    # Try annual balance sheet if quarterly failed or returned no items
    if not fundamentals:
        try:
            ab = t.balance_sheet
            if ab is not None and getattr(ab, "empty", True) is False:
                source_used = "annual_balance_sheet"
                for col in ab.columns:
                    col_data = ab[col]
                    equity = _get_series_val(col_data, EQUITY_KEYS) or info_equity
                    debt = _get_series_val(col_data, DEBT_KEYS) or info_debt
                    cash = _get_series_val(col_data, CASH_KEYS) or info_cash
                    shares = _get_series_val(col_data, SHARES_KEYS) or info_shares

                    f = FundamentalsQuarter(
                        as_of=str(col),
                        total_stockholder_equity=equity,
                        cash_and_cash_equivalents=cash,
                        total_debt=debt,
                        shares_outstanding=shares,
                        market_cap=info_market_cap,
                        extra={"raw_column": str(col)},
                    )
                    fundamentals.append(f.model_dump())
        except Exception as ex:
            logger.debug("annual balance_sheet not usable for %s: %s", ticker, ex)

    # Final fallback to info snapshot
    if not fundamentals:
        try:
            f = FundamentalsQuarter(
                as_of=datetime.now(timezone.utc).isoformat(),
                total_stockholder_equity=info_equity,
                cash_and_cash_equivalents=info_cash,
                total_debt=info_debt,
                shares_outstanding=info_shares,
                market_cap=info_market_cap,
                extra={"info_keys": list(info.keys())[:10] if info else []},
            )
            fundamentals.append(f.model_dump())
            source_used = "info"
        except Exception as ex:
            logger.exception("ticker.info fallback failed for %s: %s", ticker, ex)

    source_info = {"used": source_used or "none", "fetched_at": datetime.now(timezone.utc).isoformat()}

    return {
        "ticker": ticker,
        "prices": prices,
        "fundamentals": fundamentals,
        "source_info": source_info,
    }

