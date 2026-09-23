"""Order, urgency, supplier grouping, and export acceptance tests."""

from datetime import date

import pandas as pd

from procure.calc.order import assign_urgency, group_by_supplier
from procure.data.generate import generate_dataset
from procure.export import export_orders
from procure.run import build_item_facts


_AS_OF = date(2026, 9, 23)


def _items(tmp_path):
    generate_dataset(tmp_path)
    return build_item_facts(tmp_path, _AS_OF)


def test_all_five_items_have_nonnegative_integer_recommendations_and_urgency(tmp_path) -> None:
    items = _items(tmp_path)
    assert len(items) == 5
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
    assert list(grouped) == ["SUP-03", "SUP-02", "SUP-01"]


def test_export_orders_is_supplier_grouped_with_required_columns(tmp_path) -> None:
    output = export_orders(_items(tmp_path), tmp_path / "out" / "orders.csv")
    exported = pd.read_csv(output)
    assert list(exported.columns) == ["supplier", "sku", "name", "recommended_qty", "urgency", "naive_qty", "base_demand", "restored_demand", "season_factor", "trend_factor", "excluded_outlier", "stock", "in_transit", "lead_time_days"]
    assert len(exported) == 5
    assert exported["supplier"].tolist() == sorted(exported["supplier"].tolist(), key=lambda value: {"SUP-03": 0, "SUP-02": 1, "SUP-01": 2}[value])
