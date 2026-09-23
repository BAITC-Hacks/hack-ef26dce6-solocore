"""Proof for explicit stockout lost-demand restoration."""

from __future__ import annotations

import inspect

import pandas as pd
import pytest

from procure.calc.stockout import restore_stockout_demand
from procure.data.generate import generate_dataset


def _inputs(tmp_path) -> tuple[pd.DataFrame, pd.DataFrame]:
    generate_dataset(tmp_path)
    return pd.read_csv(tmp_path / "sales.csv"), pd.read_csv(tmp_path / "stockout.csv")


def _summary(summary: pd.DataFrame, sku: str) -> pd.Series:
    return summary.set_index("sku").loc[sku]


def _simple_sales(values: list[int]) -> pd.DataFrame:
    return pd.DataFrame({
        "date": [f"2026-{month:02d}-01" for month in range(1, len(values) + 1)],
        "sku": "TEST", "qty": values, "price": 100.0,
        "customer_id": [f"C-{month}" for month in range(1, len(values) + 1)], "warehouse": "WH-01",
    })


def _flags(months: list[str]) -> pd.DataFrame:
    return pd.DataFrame({"sku": "TEST", "month": months, "is_stockout": [month in {"2026-07", "2026-08"} for month in months]})


def test_a400_explicit_stockouts_are_detected_and_restored(tmp_path) -> None:
    summary, evidence = restore_stockout_demand(*_inputs(tmp_path))
    a400 = _summary(summary, "A-400")
    months = evidence[(evidence["sku"] == "A-400") & evidence["is_stockout"]]["month"].tolist()
    assert months == ["2026-04", "2026-05"]
    assert a400["restored_demand"] > a400["base_demand"]
    assert a400["total_lost_demand"] == pytest.approx(140.0)
    assert a400["stockout_correction"] == pytest.approx(a400["restored_demand"] - a400["base_demand"])


def test_no_stockout_has_zero_correction(tmp_path) -> None:
    summary, _ = restore_stockout_demand(*_inputs(tmp_path))
    a100 = _summary(summary, "A-100")
    assert a100["stockout_correction"] == 0
    assert a100["restored_demand"] == a100["base_demand"]


def test_low_sales_without_explicit_flag_are_not_restored() -> None:
    sales = _simple_sales([100, 100, 100, 100, 100, 100, 10])
    stockout = pd.DataFrame({"sku": "TEST", "month": sales["date"].str[:7], "is_stockout": False})
    summary, evidence = restore_stockout_demand(sales, stockout)
    result = _summary(summary, "TEST")
    assert result["stockout_correction"] == 0
    assert evidence.loc[evidence["month"] == "2026-07", "lost_demand"].iloc[0] == 0


def test_high_observed_stockout_month_is_not_reduced() -> None:
    sales = _simple_sales([100, 100, 100, 100, 100, 100, 120])
    stockout = pd.DataFrame({"sku": "TEST", "month": sales["date"].str[:7], "is_stockout": [False] * 6 + [True]})
    summary, evidence = restore_stockout_demand(sales, stockout)
    assert _summary(summary, "TEST")["stockout_correction"] == 0
    assert evidence.loc[evidence["is_stockout"], "lost_demand"].iloc[0] == 0


def test_insufficient_non_stockout_history_has_no_correction() -> None:
    sales = _simple_sales([100, 100, 100, 100, 100, 20, 20])
    stockout = pd.DataFrame({"sku": "TEST", "month": sales["date"].str[:7], "is_stockout": [False] * 5 + [True, True]})
    summary, _ = restore_stockout_demand(sales, stockout)
    result = _summary(summary, "TEST")
    assert result["stockout_correction"] == 0
    assert "insufficient_history" in result["flags"]


def test_outlier_cleaning_prevents_anomaly_from_reentering_restoration(tmp_path) -> None:
    sales, stockout = _inputs(tmp_path)
    injected = pd.concat([sales, pd.DataFrame([{"date": "2026-04-01", "sku": "A-400", "qty": 500, "price": 100.0, "customer_id": "ONE-OFF", "warehouse": "WH-01"}])], ignore_index=True)
    original, _ = restore_stockout_demand(sales, stockout)
    corrected, evidence = restore_stockout_demand(injected, stockout)
    assert _summary(corrected, "A-400")["total_lost_demand"] == _summary(original, "A-400")["total_lost_demand"]
    assert evidence.loc[(evidence["sku"] == "A-400") & (evidence["month"] == "2026-04"), "observed_cleaned_demand"].iloc[0] == 20


def test_evidence_and_logic_are_not_sku_specific(tmp_path) -> None:
    sales, stockout = _inputs(tmp_path)
    sales = sales.replace("A-400", "RENAMED")
    stockout = stockout.replace("A-400", "RENAMED")
    summary, evidence = restore_stockout_demand(sales, stockout)
    assert _summary(summary, "RENAMED")["total_lost_demand"] == pytest.approx(140.0)
    assert {"month", "reference_level", "lost_demand", "observed_cleaned_demand"}.issubset(evidence.columns)
    source = inspect.getsource(restore_stockout_demand)
    assert "A-400" not in source


def test_missing_explicit_stockout_coverage_is_reported_not_assumed_false(tmp_path) -> None:
    sales, stockout = _inputs(tmp_path)
    incomplete = stockout.loc[~((stockout["sku"] == "A-400") & (stockout["month"] == "2026-04"))]
    summary, _ = restore_stockout_demand(sales, incomplete)

    assert "incomplete_stockout_coverage" in _summary(summary, "A-400")["flags"]


def test_explicit_zero_sales_stockout_month_remains_in_evidence() -> None:
    sales = pd.DataFrame({
        "date": [f"2026-{month:02d}-01" for month in range(1, 7)],
        "sku": "TEST", "qty": 100, "price": 100.0,
        "customer_id": [f"C-{month}" for month in range(1, 7)], "warehouse": "WH-01",
    })
    stockout = pd.DataFrame({
        "sku": "TEST",
        "month": [f"2026-{month:02d}" for month in range(1, 8)],
        "is_stockout": [False] * 6 + [True],
    })
    summary, evidence = restore_stockout_demand(sales, stockout)
    july = evidence.loc[(evidence["sku"] == "TEST") & (evidence["month"] == "2026-07")].iloc[0]

    assert july["is_stockout"]
    assert july["observed_cleaned_demand"] == 0
    assert july["lost_demand"] == 100
    assert _summary(summary, "TEST")["total_lost_demand"] == 100
