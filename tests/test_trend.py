"""Frozen sustained-growth tests."""

import pandas as pd
import pytest

from procure.calc.stockout import restore_stockout_demand
from procure.calc.trend import calculate_trend


def _timeline(tmp_path) -> pd.DataFrame:
    sales = pd.read_csv(tmp_path / "sales.csv")
    stockout = pd.read_csv(tmp_path / "stockout.csv")
    return restore_stockout_demand(sales, stockout)[1]


def test_a300_growth_is_capped_at_thirty_percent(tmp_path) -> None:
    from procure.data.generate import generate_dataset

    generate_dataset(tmp_path)
    result = calculate_trend(_timeline(tmp_path)).set_index("sku").loc["A-300"]
    assert result["trend_pct"] == pytest.approx(30.0)
    assert result["trend_factor"] == pytest.approx(1.30)


def test_stable_sku_and_short_history_have_no_trend(tmp_path) -> None:
    from procure.data.generate import generate_dataset

    generate_dataset(tmp_path)
    results = calculate_trend(_timeline(tmp_path)).set_index("sku")
    assert results.loc["A-100", "trend_pct"] == 0
    assert calculate_trend(_timeline(tmp_path).query("sku == 'A-100'").head(12)).iloc[0]["trend_pct"] == 0


def test_one_spike_does_not_create_sustained_growth() -> None:
    demand = [100] * 17 + [200]
    timeline = pd.DataFrame({"sku": "TEST", "month": pd.period_range("2025-01", periods=18, freq="M").astype(str), "restored_monthly_demand": demand})
    result = calculate_trend(timeline).iloc[0]
    assert result["support"] == 1
    assert result["trend_pct"] == 0
