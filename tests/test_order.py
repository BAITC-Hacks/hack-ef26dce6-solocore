"""Order, urgency, supplier grouping, and export acceptance tests."""

from datetime import date

import pandas as pd

from procure.calc.naive import calculate_naive
from procure.calc.order import assign_urgency, group_by_supplier
from procure.data.generate import generate_dataset
from procure.export import export_orders
from procure.run import build_item_facts


_AS_OF = date(2026, 9, 23)


def _items(tmp_path):
    generate_dataset(tmp_path)
    return build_item_facts(tmp_path, _AS_OF)


def test_all_catalogue_items_have_nonnegative_integer_recommendations_and_urgency(tmp_path) -> None:
    items = _items(tmp_path)
    assert len(items) == 12
    assert all(item.recommended_qty >= 0 and float(item.recommended_qty).is_integer() for item in items)
    assert {item.urgency for item in items}.issubset({"high", "medium", "low", "unknown"})


def test_a500_clean_order_is_lower_and_in_transit_change_is_exact(tmp_path) -> None:
    items = {item.sku: item for item in _items(tmp_path)}
    assert items["A-500"].recommended_qty < items["A-500"].naive_qty
    stock = pd.read_csv(tmp_path / "stock.csv")
    stock.loc[stock["sku"] == "A-500", "in_transit"] = 50
    stock.to_csv(tmp_path / "stock.csv", index=False)
    changed = {item.sku: item for item in build_item_facts(tmp_path, _AS_OF)}
    if items["A-500"].recommended_qty >= 50:
        assert items["A-500"].recommended_qty - changed["A-500"].recommended_qty == 50
    else:
        assert changed["A-500"].recommended_qty == 0
    assert all(items[sku].recommended_qty == changed[sku].recommended_qty for sku in items if sku != "A-500")


def test_unknown_urgency_and_supplier_grouping(tmp_path) -> None:
    urgency, cover = assign_urgency(0, 10, 30)
    assert (urgency, cover) == ("unknown", 0.0)
    grouped = group_by_supplier(_items(tmp_path))
    assert set(grouped) == {"SUP-01", "SUP-02", "SUP-03"}


def test_plain_skus_have_low_urgency_and_suppliers_follow_most_urgent_item(tmp_path) -> None:
    items = _items(tmp_path)
    by_sku = {item.sku: item for item in items}
    for sku in ("A-700", "A-900", "A-1000", "A-1200"):
        item = by_sku[sku]
        assert item.urgency == "low"
        assert item.days_of_cover >= item.lead_time_days + 14

    grouped = group_by_supplier(items)
    priority = {"high": 0, "unknown": 1, "medium": 2, "low": 3}
    first_items = [members[0] for members in grouped.values()]
    assert all(
        (priority[members[0].urgency], members[0].days_of_cover, members[0].sku)
        == min((priority[item.urgency], item.days_of_cover, item.sku) for item in members)
        for members in grouped.values()
    )
    assert [(priority[item.urgency], item.days_of_cover, item.supplier) for item in first_items] == sorted(
        (priority[item.urgency], item.days_of_cover, item.supplier) for item in first_items
    )


def test_naive_uses_the_same_horizon_as_stable_recommendation_and_unknown_is_zero_only(tmp_path) -> None:
    generate_dataset(tmp_path)
    items = {item.sku: item for item in build_item_facts(tmp_path, _AS_OF)}
    naive = calculate_naive(tmp_path).set_index("sku")
    assert {sku: item.naive_qty for sku, item in items.items()} == naive["naive_qty"].to_dict()
    assert abs(naive.loc["A-100", "naive_qty"] - items["A-100"].recommended_qty) / items["A-100"].recommended_qty <= 0.20
    assert assign_urgency(1, 10, 30) != ("unknown", 0.0)
    assert assign_urgency(1, 10, 30, False) != ("unknown", 0.0)
    assert assign_urgency(0, 10, 30) == ("unknown", 0.0)


def test_raw_naive_baseline_keeps_clean_adjustments_out_of_item_facts(tmp_path) -> None:
    items = {item.sku: item for item in _items(tmp_path)}
    assert items["A-200"].recommended_qty > items["A-200"].naive_qty
    assert items["A-300"].recommended_qty > items["A-300"].naive_qty
    assert items["A-400"].recommended_qty > items["A-400"].naive_qty
    assert items["A-500"].recommended_qty < items["A-500"].naive_qty


def test_headline_excess_uses_positive_differences_only(tmp_path) -> None:
    items = _items(tmp_path)
    excess = sum(max(0, item.naive_qty - item.recommended_qty) for item in items)
    signed = sum(item.naive_qty - item.recommended_qty for item in items)
    assert excess >= 0
    assert excess != signed


def test_export_orders_is_supplier_grouped_with_required_columns(tmp_path) -> None:
    output = export_orders(_items(tmp_path), tmp_path / "out" / "orders.csv")
    exported = pd.read_csv(output)
    assert list(exported.columns) == ["supplier", "sku", "name", "recommended_qty", "urgency", "naive_qty", "base_demand", "restored_demand", "season_factor", "trend_factor", "excluded_outlier", "stock", "in_transit", "lead_time_days"]
    assert len(exported) == 12
    assert exported["supplier"].tolist() == [supplier for supplier, items in group_by_supplier(_items(tmp_path)).items() for _ in items]
