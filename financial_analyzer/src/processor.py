# src/processor.py
"""
Process raw_data -> DataFrame with calculated metrics.
Key things:
  - Merge daily prices with forward-filled fundamentals.
  - Compute 50/200-day SMA.
  - Compute 52-week high and % below high.
  - Compute BVPS, P/B, simple EV.
"""
from __future__ import annotations
from typing import Dict, Any
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _normalize_date_series(s: pd.Series) -> pd.Series:
    """Safely convert DatetimeSeries to timezone-naive pandas datetime."""
    dt = pd.to_datetime(s, errors="coerce")
    if getattr(dt.dt, "tz", None) is not None:
        return dt.dt.tz_convert(None)
    return dt


def process_data(raw_data: Dict[str, Any]) -> pd.DataFrame:
    """
    Given the raw_data from fetch_stock_data, return a DataFrame with metrics.
    The returned DataFrame has a 'date' column (datetime) and index is default.
    """
    ticker = raw_data["ticker"]
    prices_df: pd.DataFrame = raw_data["prices"].copy()
    fundamentals = raw_data.get("fundamentals", [])

    if "date" not in prices_df.columns:
        raise ValueError("prices must contain 'date' column")

    # Store normalized naive dates for internal calculations
    prices_df["date"] = _normalize_date_series(prices_df["date"])
    prices_df = prices_df.sort_values("date").reset_index(drop=True)

    # Standardize price column names
    for col in ("open", "high", "low", "close", "adj_close", "volume"):
        if col not in prices_df.columns:
            if col.capitalize() in prices_df.columns:
                prices_df[col] = prices_df[col.capitalize()]
            else:
                prices_df[col] = np.nan

    # Compute SMAs (rolling)
    prices_df["sma50"] = prices_df["close"].rolling(window=50, min_periods=1).mean()
    prices_df["sma200"] = prices_df["close"].rolling(window=200, min_periods=1).mean()

    # 52-week high and percent from high
    prices_df["52w_high"] = prices_df["close"].rolling(window=252, min_periods=1).max()
    prices_df["pct_from_52w_high"] = (prices_df["close"] / prices_df["52w_high"] - 1.0) * 100.0

    fundamental_cols = [
        "total_stockholder_equity",
        "total_debt",
        "cash_and_cash_equivalents",
        "shares_outstanding",
        "market_cap",
    ]

    # Create fundamentals DataFrame (quarterly snapshots)
    if fundamentals:
        fdf = pd.DataFrame(fundamentals)
        fdf["as_of"] = _normalize_date_series(fdf["as_of"])
        
        for col in fundamental_cols:
            if col in fdf.columns:
                fdf[col] = pd.to_numeric(fdf[col], errors="coerce")
            else:
                fdf[col] = np.nan

        fdf = fdf.sort_values("as_of").drop_duplicates("as_of", keep="last")

        merge_left = prices_df[["date"]].copy().sort_values("date")
        fdf_for_merge = fdf[["as_of"] + fundamental_cols].copy().sort_values("as_of")

        merged = pd.merge_asof(
            merge_left,
            fdf_for_merge,
            left_on="date",
            right_on="as_of",
            direction="backward",
        )

        for col in fundamental_cols:
            prices_df[col] = merged[col].values

        # Forward fill and backfill remaining values across daily dates
        prices_df[fundamental_cols] = prices_df[fundamental_cols].ffill().bfill()
    else:
        for col in fundamental_cols:
            prices_df[col] = np.nan

    # Compute Market Cap if missing but shares and close exist
    missing_mc = prices_df["market_cap"].isna() & prices_df["shares_outstanding"].notna() & prices_df["close"].notna()
    if missing_mc.any():
        prices_df.loc[missing_mc, "market_cap"] = prices_df.loc[missing_mc, "shares_outstanding"] * prices_df.loc[missing_mc, "close"]

    # Fundamental ratios:
    # BVPS = total_stockholder_equity / shares_outstanding
    prices_df["bvps"] = np.where(
        prices_df["total_stockholder_equity"].notna() & prices_df["shares_outstanding"].notna() & (prices_df["shares_outstanding"] != 0),
        prices_df["total_stockholder_equity"] / prices_df["shares_outstanding"],
        np.nan,
    )

    # Price-to-Book = close / bvps
    prices_df["price_to_book"] = np.where(
        prices_df["bvps"].notna() & (prices_df["bvps"] != 0),
        prices_df["close"] / prices_df["bvps"],
        np.nan,
    )

    # Enterprise Value (simplified): market_cap + total_debt - cash
    prices_df["enterprise_value"] = np.where(
        prices_df["market_cap"].notna(),
        prices_df["market_cap"] + prices_df["total_debt"].fillna(0) - prices_df["cash_and_cash_equivalents"].fillna(0),
        np.nan,
    )

    prices_df["ticker"] = ticker
    prices_df["generated_at"] = datetime.now(timezone.utc).isoformat()

    keep_cols = [
        "ticker",
        "date",
        "open",
        "high",
        "low",
        "close",
        "adj_close",
        "volume",
        "sma50",
        "sma200",
        "52w_high",
        "pct_from_52w_high",
        "bvps",
        "price_to_book",
        "enterprise_value",
        "total_stockholder_equity",
        "total_debt",
        "cash_and_cash_equivalents",
        "shares_outstanding",
        "market_cap",
        "generated_at",
    ]
    keep_cols = [c for c in keep_cols if c in prices_df.columns]
    out = prices_df[keep_cols].copy()
    return out

