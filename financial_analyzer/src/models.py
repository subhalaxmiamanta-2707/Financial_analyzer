# src/models.py
"""
Pydantic schemas for validating API data structures.
"""
from __future__ import annotations
from pydantic import BaseModel, field_validator, ValidationInfo
from decimal import Decimal
from typing import Optional, Dict, Any


class PriceRow(BaseModel):
    date: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    adj_close: Optional[Decimal]
    volume: int

    @field_validator("low")
    @classmethod
    def low_le_high(cls, v: Decimal, info: ValidationInfo) -> Decimal:
        high = info.data.get("high")
        if high is not None and v > high:
            raise ValueError("low > high")
        return v


class FundamentalsQuarter(BaseModel):
    as_of: str
    total_stockholder_equity: Optional[Decimal] = None
    total_assets: Optional[Decimal] = None
    total_liab: Optional[Decimal] = None
    cash_and_cash_equivalents: Optional[Decimal] = None
    total_debt: Optional[Decimal] = None
    shares_outstanding: Optional[Decimal] = None
    market_cap: Optional[Decimal] = None
    extra: Optional[Dict[str, Any]] = None


class SignalEvent(BaseModel):
    ticker: str
    date: str
    signal_type: str  # "golden_cross" | "death_cross"
    sma50: Optional[Decimal]
    sma200: Optional[Decimal]
    meta: Optional[Dict[str, Any]] = None


class ExportPayload(BaseModel):
    ticker: str
    generated_at: str
    price_rows_count: int
    fundamentals_used: str
    signals: list[SignalEvent]
