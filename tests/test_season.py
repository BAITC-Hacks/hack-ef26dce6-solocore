"""Frozen monthly-seasonality tests."""

import pandas as pd

from procure.calc.season import calculate_seasonality
from procure.calc.stockout import restore_stockout_demand


def _timeline(tmp_path) -> pd.DataFrame:
    sales = pd.read_csv(tmp_path / "sales.csv")
    stockout = pd.read_csv(tmp_path / "stockout.csv")
    return restore_stockout_demand(sales, stockout)[1]


def test_a200_peak_and_low_months_and_a100_stability(tmp_path) -> None:
    from procure.data.generate import generate_dataset

    generate_dataset(tmp_path)
    result = calculate_seasonality(_timeline(tmp_path))
    a200 = result[result["sku"] == "A-200"]
    peak = a200[a200["month"].str[-2:].isin(["11", "12", "01"])]["season_factor"]
    low = a200[a200["month"].str[-2:].isin(["04", "05", "06"])]["season_factor"]
    stable = result[result["sku"] == "A-100"]["season_factor"]
    assert (peak > 1.3).all()
    assert (low < 0.8).all()
    assert stable.between(0.9, 1.1).all()


def test_short_history_is_neutral_and_stockout_months_do_not_set_a400_factor(tmp_path) -> None:
    from procure.data.generate import generate_dataset

    generate_dataset(tmp_path)
    timeline = _timeline(tmp_path)
    short = calculate_seasonality(timeline[timeline["sku"] == "A-100"].head(12))
    result = calculate_seasonality(timeline)
    a400 = result[(result["sku"] == "A-400") & result["month"].isin(["2026-04", "2026-05"])]
    assert (short["season_factor"] == 1.0).all()
    assert (a400["season_factor"] == 1.0).all()
