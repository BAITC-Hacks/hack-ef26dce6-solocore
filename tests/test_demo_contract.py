"""Lock the accepted demo numbers against the current calculation pipeline."""

from datetime import date
from pathlib import Path
from shutil import copyfile

import pandas as pd
import pytest

from procure.run import build_item_facts


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
AS_OF = date(2026, 9, 23)


@pytest.fixture(scope="module")
def items():
    return {item.sku: item for item in build_item_facts(DATA_DIR, AS_OF)}


def test_five_demo_sku_quantities(items) -> None:
    expected = {
        "A-100": (90, 89),
        "A-200": (93, 209),
        "A-300": (64, 79),
        "A-400": (104, 117),
        "A-500": (120, 49),
    }
    assert {sku: (items[sku].naive_qty, items[sku].recommended_qty) for sku in expected} == expected


def test_outlier_and_season_demo_facts(items) -> None:
    assert items["A-500"].outlier_qty == 1500
    assert items["A-500"].outlier_client == "CUST-017"
    assert abs(items["A-200"].season_factor - 1.7375) < 1e-9
    assert items["A-200"].recommended_qty == 209


def test_a500_in_transit_recalculates_through_pipeline(items, tmp_path) -> None:
    assert items["A-500"].in_transit == 0
    assert items["A-500"].recommended_qty == 49

    recommendations = {0: items["A-500"].recommended_qty}
    for in_transit in (20, 50):
        scenario = tmp_path / f"in-transit-{in_transit}"
        scenario.mkdir()
        for filename in ("sales.csv", "stock.csv", "stockout.csv"):
            copyfile(DATA_DIR / filename, scenario / filename)
        stock = pd.read_csv(scenario / "stock.csv")
        stock.loc[stock["sku"] == "A-500", "in_transit"] = in_transit
        stock.to_csv(scenario / "stock.csv", index=False)
        changed = {item.sku: item for item in build_item_facts(scenario, AS_OF)}
        recommendations[in_transit] = changed["A-500"].recommended_qty

    assert recommendations == {0: 49, 20: 29, 50: 0}
    assert recommendations[20] - recommendations[0] == -20
    assert recommendations[50] - recommendations[0] == -49


def test_catalogue_kpis_and_nonnegative_integer_orders(items) -> None:
    assert len(items) == 12
    excess = sum(max(item.naive_qty - item.recommended_qty, 0) for item in items.values())
    shortage = sum(max(item.recommended_qty - item.naive_qty, 0) for item in items.values())
    signed = sum(item.naive_qty - item.recommended_qty for item in items.values())
    assert (excess, shortage, signed) == (78, 154, -76)
    assert all(
        value >= 0 and float(value).is_integer()
        for item in items.values()
        for value in (item.naive_qty, item.recommended_qty)
    )
