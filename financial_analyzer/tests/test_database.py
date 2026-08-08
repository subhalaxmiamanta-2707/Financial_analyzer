# tests/test_database.py
import pandas as pd
import numpy as np
import sqlalchemy as sa
from src.database import get_engine, init_db, save_daily_metrics, save_signal_events

def test_database_operations(tmp_path):
    db_file = tmp_path / "test.db"
    engine = get_engine(str(db_file))
    init_db(engine)

    df = pd.DataFrame({
        "ticker": ["TEST", "TEST"],
        "date": [pd.Timestamp("2023-01-01"), pd.Timestamp("2023-01-02")],
        "open": [100.0, np.nan],
        "high": [105.0, 110.0],
        "low": [95.0, 100.0],
        "close": [102.0, 108.0],
        "volume": [1000, 2000],
        "sma50": [100.0, 101.0],
        "sma200": [pd.NA, 99.0],
        "price_to_book": [2.5, np.nan],
        "bvps": [40.0, 40.0],
        "enterprise_value": [1000000.0, 1050000.0],
    })

    save_daily_metrics(df, engine=engine)

    events = [
        {"date": "2023-01-02", "signal_type": "golden_cross", "meta": {"test": "val"}},
        {"date": None, "signal_type": "death_cross", "meta": {}},
    ]
    save_signal_events("TEST", events, engine=engine)

    with engine.connect() as conn:
        metrics_count = conn.execute(sa.text("SELECT COUNT(*) FROM daily_metrics")).scalar()
        assert metrics_count == 2

        signals_count = conn.execute(sa.text("SELECT COUNT(*) FROM signal_events")).scalar()
        assert signals_count == 2
