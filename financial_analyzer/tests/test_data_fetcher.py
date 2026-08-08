# tests/test_data_fetcher.py
import pandas as pd
from decimal import Decimal
from src.data_fetcher import _get_series_val, EQUITY_KEYS

def test_get_series_val():
    series = pd.Series({"Stockholders Equity": 1234567, "Other": 99})
    val = _get_series_val(series, EQUITY_KEYS)
    assert val == Decimal("1234567")

def test_get_series_val_missing():
    series = pd.Series({"Random Key": 100})
    val = _get_series_val(series, EQUITY_KEYS)
    assert val is None

def test_get_series_val_duplicate_index():
    # Duplicate keys in Series index should not raise an ambiguous truth value error
    series = pd.Series([1000, 2000], index=["Stockholders Equity", "Stockholders Equity"])
    val = _get_series_val(series, EQUITY_KEYS)
    assert val == Decimal("1000")
