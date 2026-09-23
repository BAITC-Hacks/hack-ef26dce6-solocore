"""CSV export for reviewed supplier recommendations."""

from __future__ import annotations

import csv
from pathlib import Path

from procure.calc.order import group_by_supplier
from procure.contracts import ItemFacts


_COLUMNS = ["supplier", "sku", "name", "recommended_qty", "urgency", "naive_qty", "base_demand", "restored_demand", "season_factor", "trend_factor", "excluded_outlier", "stock", "in_transit", "lead_time_days"]


def export_orders(items: list[ItemFacts], destination: Path | str = "out/orders.csv") -> Path:
    """Write supplier-grouped recommendation rows and return the CSV path."""
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=_COLUMNS)
        writer.writeheader()
        for supplier, members in group_by_supplier(items).items():
            for item in members:
                writer.writerow({"supplier": supplier, "sku": item.sku, "name": item.name, "recommended_qty": item.recommended_qty, "urgency": item.urgency, "naive_qty": item.naive_qty, "base_demand": item.base_demand, "restored_demand": item.restored_demand, "season_factor": item.season_factor, "trend_factor": 1 + item.trend_pct / 100, "excluded_outlier": item.outlier_qty or 0, "stock": item.stock, "in_transit": item.in_transit, "lead_time_days": item.lead_time_days})
    return path
