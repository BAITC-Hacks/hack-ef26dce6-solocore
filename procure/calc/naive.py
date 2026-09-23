"""Unadjusted Excel-style demand reference calculation."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def calculate_naive(data_dir: Path | str = "data") -> pd.DataFrame:
    """Return uncleaned mean monthly demand and the resulting naive quantity."""
    source = Path(data_dir)
    sales = pd.read_csv(source / "sales.csv")
    stock = pd.read_csv(source / "stock.csv")

    sales["month"] = sales["date"].str.slice(0, 7)
    monthly_demand = sales.groupby(["sku", "month"], as_index=False)["qty"].sum()
    averages = (
        monthly_demand.groupby("sku", as_index=False)["qty"]
        .mean()
        .rename(columns={"qty": "naive_monthly_demand"})
    )
    result = averages.merge(stock[["sku", "lead_time_days", "stock", "in_transit"]], on="sku", validate="one_to_one")
    result["naive_qty"] = (
        result["naive_monthly_demand"] * (result["lead_time_days"] / 30)
        - result["stock"]
        - result["in_transit"]
    ).clip(lower=0)
    return result[["sku", "naive_monthly_demand", "naive_qty"]].sort_values("sku").reset_index(drop=True)
