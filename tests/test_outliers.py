"""Proof for deterministic one-off customer order detection."""

from __future__ import annotations

import inspect

import pandas as pd

from procure.calc.outliers import clean_outlier_demand, detect_one_off_orders
from procure.data.generate import generate_dataset


def _sales(tmp_path) -> pd.DataFrame:
    generate_dataset(tmp_path)
    return pd.read_csv(tmp_path / "sales.csv")


def _rows(records: list[tuple[str, str, int]]) -> pd.DataFrame:
    return pd.DataFrame(records, columns=["date", "customer_id", "qty"]).assign(
        sku="TEST", price=100.0, warehouse="WH-01"
    )[["date", "sku", "qty", "price", "customer_id", "warehouse"]]


def test_a500_one_off_customer_purchase_is_detected(tmp_path) -> None:
    events = detect_one_off_orders(_sales(tmp_path))
    event = events.loc[(events["sku"] == "A-500") & (events["customer_id"] == "CUST-017")].iloc[0]
    assert event["month"] == "2026-03"
    assert event["excluded_qty"] == 500
    assert event["customer_share"] >= 0.50
    assert event["reason"] == "monthly_spike_concentrated_non_repeating_customer"


def test_a500_outlier_is_excluded_from_clean_demand(tmp_path) -> None:
    cleaned, events = clean_outlier_demand(_sales(tmp_path))
    excluded = cleaned[(cleaned["sku"] == "A-500") & (cleaned["customer_id"] == "CUST-017") & (cleaned["month"] == "2026-03")]
    assert events.loc[events["sku"] == "A-500", "excluded_qty"].iloc[0] == 500
    assert excluded["qty"].tolist() == [500]
    assert excluded["cleaned_qty"].tolist() == [0.0]


def test_a500_clean_monthly_demand_is_materially_lower_than_raw(tmp_path) -> None:
    cleaned, _ = clean_outlier_demand(_sales(tmp_path))
    a500 = cleaned.loc[cleaned["sku"] == "A-500"]
    raw = a500.groupby("month")["qty"].sum().mean()
    clean = a500.groupby("month")["cleaned_qty"].sum().mean()
    assert clean < raw
    assert raw - clean > 15


def test_stable_and_growth_skus_do_not_create_false_positives(tmp_path) -> None:
    events = detect_one_off_orders(_sales(tmp_path))
    assert not events["sku"].isin(["A-100", "A-300"]).any()


def test_repeating_bulk_customer_is_not_one_off() -> None:
    sales = _rows([
        ("2026-01-01", "BULK", 10), ("2026-02-01", "BULK", 10), ("2026-03-01", "BULK", 10),
        ("2026-04-01", "BULK", 10), ("2026-05-01", "BULK", 100), ("2026-06-01", "BULK", 100),
    ])
    assert detect_one_off_orders(sales).empty


def test_distributed_spike_is_not_one_off() -> None:
    sales = _rows([
        ("2026-01-01", "BASE", 10), ("2026-02-01", "BASE", 10), ("2026-03-01", "BASE", 10),
        ("2026-04-01", "BASE", 10), ("2026-05-01", "A", 40), ("2026-05-01", "B", 35), ("2026-05-01", "C", 25),
    ])
    assert detect_one_off_orders(sales).empty


def test_mad_zero_fallback_detects_one_off_without_division_by_zero() -> None:
    sales = _rows([
        ("2026-01-01", "BASE", 10), ("2026-02-01", "BASE", 10), ("2026-03-01", "BASE", 10), ("2026-04-01", "ONE", 50),
    ])
    events = detect_one_off_orders(sales)
    assert events["excluded_qty"].tolist() == [50]
    assert pd.isna(events["robust_z"].iloc[0])


def test_input_rows_and_event_metadata_remain_traceable(tmp_path) -> None:
    sales = _sales(tmp_path)
    cleaned, events = clean_outlier_demand(sales)
    event = events.loc[events["sku"] == "A-500"].iloc[0]
    assert len(cleaned) == len(sales)
    assert set(sales.columns).issubset(cleaned.columns)
    assert ((cleaned["sku"] == event["sku"]) & (cleaned["month"] == event["month"]) & (cleaned["customer_id"] == event["customer_id"])).any()


def test_detection_is_not_hardcoded_to_frozen_sku_or_customer(tmp_path) -> None:
    sales = _sales(tmp_path).replace({"A-500": "RENAMED", "CUST-017": "CUSTOMER-X"})
    events = detect_one_off_orders(sales)
    assert ((events["sku"] == "RENAMED") & (events["customer_id"] == "CUSTOMER-X")).any()
    source = inspect.getsource(detect_one_off_orders)
    assert "A-500" not in source
    assert "CUST-017" not in source
