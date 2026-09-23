"""Deterministic monthly seasonality factors from restored demand."""

from __future__ import annotations

import pandas as pd

from procure.calc.trend import calculate_trend


_REQUIRED_COLUMNS = {"sku", "month", "restored_monthly_demand", "is_stockout"}


def calculate_seasonality(timeline: pd.DataFrame, trends: pd.DataFrame | None = None) -> pd.DataFrame:
    """Return one season factor per observed SKU/month.

    Factors use trend-removed demand from explicitly non-stockout months only.
    Fewer than 24 months of history, or fewer than two usable observations for a
    calendar month, receives the neutral factor 1.0.
    """
    missing = _REQUIRED_COLUMNS.difference(timeline.columns)
    if missing:
        raise ValueError(f"timeline is missing required columns: {sorted(missing)}")
    trend_table = calculate_trend(timeline) if trends is None else trends
    factor_by_sku = trend_table.set_index("sku")["trend_factor"].to_dict()
    results: list[pd.DataFrame] = []
    for sku, item in timeline.groupby("sku", sort=True):
        item = item.sort_values("month").copy().reset_index(drop=True)
        item["calendar_month"] = pd.to_datetime(item["month"] + "-01").dt.month
        item["observations"] = 0
        item["season_factor"] = 1.0
        item["flags"] = ""
        if len(item) < 24:
            item["flags"] = "insufficient_history"
            results.append(item[["sku", "month", "season_factor", "observations", "flags"]])
            continue
        trend_factor = float(factor_by_sku.get(sku, 1.0))
        item["residual_demand"] = item["restored_monthly_demand"] / (trend_factor ** (item.index / 12))
        usable = item.loc[~item["is_stockout"].astype(bool)].copy()
        grouped = usable.groupby("calendar_month")["residual_demand"].agg(["mean", "count"])
        valid = grouped.loc[grouped["count"] >= 2, "mean"]
        if not valid.empty:
            normalized = valid / valid.mean()
            factors = normalized.clip(lower=0.5, upper=2.0).to_dict()
            counts = grouped["count"].to_dict()
            item["observations"] = item["calendar_month"].map(counts).fillna(0).astype(int)
            item["season_factor"] = item["calendar_month"].map(factors).fillna(1.0)
        item.loc[item["observations"] < 2, "flags"] = "insufficient_month_observations"
        results.append(item[["sku", "month", "season_factor", "observations", "flags"]])
    return pd.concat(results, ignore_index=True)
