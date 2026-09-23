"""Command-line entry point for fixture generation and the naive baseline."""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from procure.calc.naive import calculate_naive
from procure.calc.order import assign_urgency, calculate_order_quantity, group_by_supplier
from procure.calc.outliers import detect_one_off_orders
from procure.calc.season import calculate_seasonality
from procure.calc.stockout import restore_stockout_demand
from procure.calc.trend import calculate_trend
from procure.contracts import ItemFacts
from procure.data.generate import generate_dataset
from procure.export import export_orders


def build_item_facts(data_dir: Path | str = "data", as_of: date | None = None) -> list[ItemFacts]:
    """Assemble all deterministic calculation stages into frozen item facts."""
    source = Path(data_dir)
    sales = pd.read_csv(source / "sales.csv")
    stock = pd.read_csv(source / "stock.csv")
    stockout = pd.read_csv(source / "stockout.csv")
    summaries, timeline = restore_stockout_demand(sales, stockout)
    trends = calculate_trend(timeline).set_index("sku")
    seasons = calculate_seasonality(timeline, trends.reset_index())
    events = detect_one_off_orders(sales).set_index("sku")
    naive_monthly = sales.assign(month=sales["date"].str[:7]).groupby("sku")["qty"].sum() / 24
    summary_by_sku = summaries.set_index("sku")
    now = as_of or date.today()
    facts: list[ItemFacts] = []
    for row in stock.sort_values("sku").itertuples(index=False):
        summary = summary_by_sku.loc[row.sku]
        trend = trends.loc[row.sku]
        arrival_month = (now + timedelta(days=int(row.lead_time_days))).month
        seasonal = seasons[(seasons["sku"] == row.sku) & (pd.to_datetime(seasons["month"] + "-01").dt.month == arrival_month)]
        season_factor = float(seasonal["season_factor"].iloc[0]) if not seasonal.empty else 1.0
        recommended, expected_daily, horizon_need = calculate_order_quantity(float(summary.restored_demand), season_factor, float(trend.trend_factor), int(row.lead_time_days), float(row.stock), float(row.in_transit), int(row.pack_size))
        raw_demand = float(naive_monthly.loc[row.sku])
        naive_qty, _, _ = calculate_order_quantity(raw_demand, season_factor, float(trend.trend_factor), int(row.lead_time_days), float(row.stock), float(row.in_transit), int(row.pack_size))
        reliable = "insufficient_history" not in summary["flags"] and "incomplete_stockout_coverage" not in summary["flags"]
        urgency, cover = assign_urgency(expected_daily, float(row.stock), int(row.lead_time_days), reliable)
        event = events.loc[row.sku] if row.sku in events.index else None
        flags = tuple(summary["flags"]) + tuple(trend["flags"]) + (("NO_SUPPLIER",) if not row.supplier else ())
        facts.append(ItemFacts(sku=row.sku, name=row.name, supplier=row.supplier or "NO_SUPPLIER", raw_demand=raw_demand, base_demand=float(summary.base_demand), restored_demand=float(summary.restored_demand), season_factor=season_factor, trend_pct=float(trend.trend_pct), lead_time_days=int(row.lead_time_days), review_days=14, horizon_need=horizon_need, safety_stock=0.0, stock=float(row.stock), in_transit=float(row.in_transit), days_of_cover=cover, history_months=int((timeline["sku"] == row.sku).sum()), stockout_months=len(summary.stockout_months), outlier_qty=None if event is None else float(event.excluded_qty), outlier_client=None if event is None else str(event.customer_id), pack_size=int(row.pack_size), naive_qty=float(naive_qty), recommended_qty=float(recommended), urgency=urgency, flags=flags))
    return facts


def main() -> None:
    """Run the selected currently available pipeline action."""
    parser = argparse.ArgumentParser()
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--generate", action="store_true")
    actions.add_argument("--naive", action="store_true")
    arguments = parser.parse_args()

    if arguments.generate:
        generate_dataset()
    elif arguments.naive:
        print(calculate_naive().to_string(index=False))
    else:
        items = build_item_facts()
        export_orders(items)
        rows = []
        for supplier, members in group_by_supplier(items).items():
            for item in members:
                rows.append({"supplier": supplier, "sku": item.sku, "name": item.name, "naive_qty": item.naive_qty, "recommended_qty": item.recommended_qty, "urgency": item.urgency, "days_of_cover": item.days_of_cover})
        print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
