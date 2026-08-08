# tests/test_processor.py
import pandas as pd
from src.processor import process_data
from decimal import Decimal

def test_process_calculations(simple_price_df):
    raw = {"ticker": "TEST", "prices": simple_price_df, "fundamentals": [], "source_info": {}}
    out = process_data(raw)
    assert "sma50" in out.columns
    assert "sma200" in out.columns
    assert "52w_high" in out.columns
    assert out["sma200"].notna().any()


def test_process_fundamentals(simple_price_df):
    fundamentals = [
        {
            "as_of": "2023-01-01",
            "total_stockholder_equity": Decimal("500000"),
            "cash_and_cash_equivalents": Decimal("50000"),
            "total_debt": Decimal("100000"),
            "shares_outstanding": Decimal("10000"),
            "market_cap": Decimal("1000000"),
        }
    ]
    raw = {"ticker": "TEST", "prices": simple_price_df, "fundamentals": fundamentals, "source_info": {}}
    out = process_data(raw)
    assert "bvps" in out.columns
    assert "price_to_book" in out.columns
    assert "enterprise_value" in out.columns
    # bvps should be 500000 / 10000 = 50.0
    assert (out["bvps"] == 50.0).all()
    # enterprise value should be 1000000 + 100000 - 50000 = 1050000.0
    assert (out["enterprise_value"] == 1050000.0).all()


def test_process_with_invalid_and_tz_dates(simple_price_df):
    df_copy = simple_price_df.copy()
    # insert a timezone-aware date and an invalid date
    df_copy["date"] = pd.date_range("2023-01-01", periods=len(df_copy), tz="UTC")
    df_copy.loc[0, "date"] = pd.NaT
    raw = {"ticker": "TZ_TEST", "prices": df_copy, "fundamentals": [], "source_info": {}}
    out = process_data(raw)
    assert len(out) == len(simple_price_df) - 1
    assert out["date"].dt.tz is None

