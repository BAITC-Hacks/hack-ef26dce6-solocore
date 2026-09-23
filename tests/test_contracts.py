"""Tests for frozen data contracts."""

from dataclasses import FrozenInstanceError

import pytest

from procure.contracts import Explanation, ItemFacts, SalesRow


def test_contracts_are_frozen() -> None:
    sales_row = SalesRow("2026-01-01", "SKU-1", 1.0, 2.0, "client-1", "WH-1")
    explanation = Explanation("SKU-1", "text", "template")

    with pytest.raises(FrozenInstanceError):
        sales_row.qty = 2.0
    with pytest.raises(FrozenInstanceError):
        explanation.text = "changed"


def test_item_facts_can_be_constructed_and_is_frozen() -> None:
    facts = ItemFacts(
        sku="SKU-1",
        name="Item",
        supplier="Supplier",
        raw_demand=10.0,
        base_demand=9.0,
        restored_demand=10.0,
        season_factor=1.0,
        trend_pct=0.0,
        lead_time_days=7,
        review_days=14,
        horizon_need=210.0,
        safety_stock=20.0,
        stock=100.0,
        in_transit=50.0,
        days_of_cover=10.0,
        history_months=12,
        stockout_months=1,
        outlier_qty=None,
        outlier_client=None,
        pack_size=1,
        naive_qty=60.0,
        recommended_qty=80.0,
        urgency="medium",
        flags=("synthetic",),
    )

    assert facts.sku == "SKU-1"
    with pytest.raises(FrozenInstanceError):
        facts.recommended_qty = 90.0
