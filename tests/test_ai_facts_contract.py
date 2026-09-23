"""AI-facing numbers must come from deterministic pipeline facts."""

import re
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


def system_facts(item):
    """Project core output and deterministic comparisons, with no AI calculation."""
    return {
        "sku": item.sku,
        "naive_qty": item.naive_qty,
        "recommended_qty": item.recommended_qty,
        "stock": item.stock,
        "in_transit": item.in_transit,
        "lead_time_days": item.lead_time_days,
        # The 14-day planning buffer is review_days in the core contract.
        "safety_days": item.review_days,
        "horizon_days": item.lead_time_days + item.review_days,
        "excluded_outlier_qty": item.outlier_qty or 0,
        "customer": item.outlier_client,
        "season_factor": item.season_factor,
        "trend_factor": 1 + item.trend_pct / 100,
        "difference_qty": abs(item.naive_qty - item.recommended_qty),
        "stockout_months": item.stockout_months,
        "restored_demand_correction": item.restored_demand - item.base_demand,
    }


def test_a500_baseline_system_facts(items) -> None:
    facts = system_facts(items["A-500"])
    assert (
        facts["sku"], facts["naive_qty"], facts["recommended_qty"],
        facts["stock"], facts["in_transit"], facts["lead_time_days"],
        facts["safety_days"], facts["horizon_days"],
        facts["excluded_outlier_qty"], facts["customer"], facts["trend_factor"],
    ) == ("A-500", 120, 49, 10, 0, 21, 14, 35, 1500, "CUST-017", 1.0)
    assert abs(facts["season_factor"] - 1.034482759) < 1e-9


def test_a500_transit_system_facts(items, tmp_path) -> None:
    scenario = tmp_path / "transit-20"
    scenario.mkdir()
    for filename in ("sales.csv", "stock.csv", "stockout.csv"):
        copyfile(DATA_DIR / filename, scenario / filename)
    stock = pd.read_csv(scenario / "stock.csv")
    stock.loc[stock["sku"] == "A-500", "in_transit"] = 20
    stock.to_csv(scenario / "stock.csv", index=False)

    changed = {item.sku: item for item in build_item_facts(scenario, AS_OF)}
    facts = system_facts(changed["A-500"])
    assert (facts["in_transit"], facts["naive_qty"], facts["recommended_qty"]) == (20, 100, 29)
    assert facts["difference_qty"] == 71
    assert facts["difference_qty"] == system_facts(items["A-500"])["difference_qty"]


def test_season_trend_and_stockout_system_facts(items) -> None:
    a200 = system_facts(items["A-200"])
    assert (a200["naive_qty"], a200["recommended_qty"], a200["difference_qty"]) == (93, 209, 116)
    assert abs(a200["season_factor"] - 1.7375) < 1e-9

    a300 = system_facts(items["A-300"])
    assert abs(a300["season_factor"] - 0.88) < 0.01
    assert a300["trend_factor"] == 1.30
    assert a300["recommended_qty"] == 79

    a400 = system_facts(items["A-400"])
    assert a400["stockout_months"] == 2
    assert abs(a400["restored_demand_correction"] - 5.833333) < 1e-6
    assert a400["recommended_qty"] == 117


def test_customer_facts_remain_anonymized(items) -> None:
    customer_ids = [system_facts(item)["customer"] for item in items.values() if item.outlier_client]
    assert "CUST-017" in customer_ids
    assert all(re.fullmatch(r"CUST-\d{3}", customer_id) for customer_id in customer_ids)
