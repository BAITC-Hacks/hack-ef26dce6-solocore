"""End-to-end regression scenarios for the deterministic pipeline."""

from __future__ import annotations

from datetime import date

import pandas as pd

from procure.calc.season import calculate_seasonality
from procure.calc.stockout import restore_stockout_demand
from procure.calc.trend import calculate_trend
from procure.data.generate import generate_dataset
from procure.run import build_item_facts


_AS_OF = date(2026, 9, 23)


def _pipeline(data_dir):
    generate_dataset(data_dir)
    return {item.sku: item for item in build_item_facts(data_dir, _AS_OF)}


def _numeric_snapshot(items) -> dict[str, tuple[object, ...]]:
    return {
        sku: (
            item.raw_demand,
            item.base_demand,
            item.restored_demand,
            item.season_factor,
            item.trend_pct,
            item.lead_time_days,
            item.review_days,
            item.horizon_need,
            item.safety_stock,
            item.stock,
            item.in_transit,
            item.days_of_cover,
            item.history_months,
            item.stockout_months,
            item.outlier_qty,
            item.pack_size,
            item.naive_qty,
            item.recommended_qty,
        )
        for sku, item in items.items()
    }


def test_scn_happy_stable_item_has_comparable_naive_and_clean_orders(tmp_path) -> None:
    item = _pipeline(tmp_path)["A-100"]

    assert item.recommended_qty > 0
    assert item.naive_qty > 0
    assert abs(item.naive_qty - item.recommended_qty) / item.naive_qty <= 0.30


def test_scn_outlier_clean_order_excludes_the_one_off_sale(tmp_path) -> None:
    item = _pipeline(tmp_path)["A-500"]
    sales = pd.read_csv(tmp_path / "sales.csv")
    client_sales = sales.loc[
        (sales["sku"] == item.sku) & (sales["customer_id"] == "CUST-017"),
        "qty",
    ]
    one_off_sale = float(client_sales.max())

    assert item.recommended_qty <= item.naive_qty * 0.70
    assert item.outlier_qty == one_off_sale


def test_scn_stockout_restores_demand_above_observed_level(tmp_path) -> None:
    item = _pipeline(tmp_path)["A-400"]

    assert item.restored_demand > item.base_demand


def test_scn_season_peak_month_factors_are_above_threshold(tmp_path) -> None:
    generate_dataset(tmp_path)
    sales = pd.read_csv(tmp_path / "sales.csv")
    stockout = pd.read_csv(tmp_path / "stockout.csv")
    _, timeline = restore_stockout_demand(sales, stockout)
    trends = calculate_trend(timeline)
    seasons = calculate_seasonality(timeline, trends)
    a200 = seasons.loc[seasons["sku"] == "A-200"].copy()
    a200["calendar_month"] = pd.to_datetime(a200["month"] + "-01").dt.month
    peak = a200.loc[a200["calendar_month"].isin({11, 12, 1})]

    assert set(peak["calendar_month"]) == {11, 12, 1}
    assert (peak["season_factor"] > 1.30).all()


def test_scn_growth_has_positive_trend_factor(tmp_path) -> None:
    item = _pipeline(tmp_path)["A-300"]
    trend_factor = 1.0 + item.trend_pct / 100.0

    assert trend_factor > 1.0


def test_scn_change_in_transit_reduces_only_a500_by_twenty(tmp_path) -> None:
    before = _pipeline(tmp_path)
    stock = pd.read_csv(tmp_path / "stock.csv")
    assert float(stock.loc[stock["sku"] == "A-500", "in_transit"].iloc[0]) == 0
    stock.loc[stock["sku"] == "A-500", "in_transit"] = 20
    stock.to_csv(tmp_path / "stock.csv", index=False)

    after = {item.sku: item for item in build_item_facts(tmp_path, _AS_OF)}

    assert before["A-500"].recommended_qty - after["A-500"].recommended_qty == 20
    assert all(
        before[sku].recommended_qty == after[sku].recommended_qty
        for sku in before
        if sku != "A-500"
    )


def test_scn_fallback_ai_off_keeps_numeric_output_identical(
    tmp_path, monkeypatch
) -> None:
    generate_dataset(tmp_path)
    monkeypatch.delenv("AI_MODE", raising=False)
    unset = {item.sku: item for item in build_item_facts(tmp_path, _AS_OF)}
    monkeypatch.setenv("AI_MODE", "off")
    off = {item.sku: item for item in build_item_facts(tmp_path, _AS_OF)}

    assert _numeric_snapshot(off) == _numeric_snapshot(unset)
