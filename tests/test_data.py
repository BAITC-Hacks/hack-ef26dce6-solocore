"""Tests for the deterministic synthetic fixture and naive baseline."""

from hashlib import sha256

import pandas as pd

from procure.calc.naive import calculate_naive
from procure.data.generate import generate_dataset


def _hashes(directory) -> dict[str, str]:
    return {
        filename: sha256((directory / filename).read_bytes()).hexdigest()
        for filename in ("sales.csv", "stock.csv", "stockout.csv")
    }


def test_generation_is_byte_identical(tmp_path) -> None:
    generate_dataset(tmp_path)
    first = _hashes(tmp_path)
    generate_dataset(tmp_path)
    assert _hashes(tmp_path) == first


def test_sales_contains_all_skus_across_24_months(tmp_path) -> None:
    generate_dataset(tmp_path)
    sales = pd.read_csv(tmp_path / "sales.csv")
    expected_skus = {"A-100", "A-200", "A-300", "A-400", "A-500", "A-600", "A-700", "A-800", "A-900", "A-1000", "A-1100", "A-1200"}

    assert set(sales["sku"]) == expected_skus
    assert sales.assign(month=sales["date"].str[:7]).groupby("sku")["month"].nunique().to_dict() == {
        sku: 24 for sku in expected_skus
    }


def test_stock_catalogue_has_twelve_priced_items_for_three_suppliers(tmp_path) -> None:
    generate_dataset(tmp_path)
    stock = pd.read_csv(tmp_path / "stock.csv")
    assert len(stock) == 12
    assert set(stock["supplier"]) == {"SUP-01", "SUP-02", "SUP-03"}
    assert stock[["category", "unit", "price_kzt"]].notna().all().all()
    assert (stock["price_kzt"] > 0).all()


def test_a500_has_one_visible_client_outlier(tmp_path) -> None:
    generate_dataset(tmp_path)
    sales = pd.read_csv(tmp_path / "sales.csv")
    outlier = sales[
        (sales["sku"] == "A-500")
        & (sales["date"] == "2026-03-01")
        & (sales["customer_id"] == "CUST-017")
        & (sales["qty"] == 1500)
    ]
    assert len(outlier) == 1
    assert len(sales[sales["qty"] == 1500]) == 1


def test_a400_has_exactly_two_stockout_months(tmp_path) -> None:
    generate_dataset(tmp_path)
    stockout = pd.read_csv(tmp_path / "stockout.csv")
    flagged = stockout[(stockout["sku"] == "A-400") & stockout["is_stockout"]]

    assert flagged["month"].tolist() == ["2026-04", "2026-05"]


def test_naive_baseline_keeps_a500_outlier(tmp_path) -> None:
    generate_dataset(tmp_path)
    naive = calculate_naive(tmp_path).set_index("sku")

    assert naive.loc["A-500", "naive_monthly_demand"] > 60
