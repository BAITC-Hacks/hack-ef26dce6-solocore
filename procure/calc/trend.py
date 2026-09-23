"""Deterministic sustained-growth calculation from restored monthly demand."""

from __future__ import annotations

import pandas as pd


_REQUIRED_COLUMNS = {"sku", "month", "restored_monthly_demand"}


def calculate_trend(timeline: pd.DataFrame) -> pd.DataFrame:
    """Return capped year-over-year trend for the latest six monthly observations."""
    missing = _REQUIRED_COLUMNS.difference(timeline.columns)
    if missing:
        raise ValueError(f"timeline is missing required columns: {sorted(missing)}")
    results: list[dict[str, object]] = []
    for sku, item in timeline.groupby("sku", sort=True):
        item = item.sort_values("month").reset_index(drop=True)
        flags: list[str] = []
        trend_pct = 0.0
        support = 0
        if len(item) < 18:
            flags.append("insufficient_history")
        else:
            recent = item.iloc[-6:].copy().reset_index(drop=True)
            prior = item.iloc[-18:-12]["restored_monthly_demand"].reset_index(drop=True)
            recent["prior_demand"] = prior
            valid = recent["prior_demand"] > 0
            growth = recent.loc[valid, "restored_monthly_demand"] / recent.loc[valid, "prior_demand"] - 1
            support = int((growth > 0).sum())
            if support >= 5:
                trend_pct = 100 * min(max(float(growth.median()), 0.0), 0.30)
            else:
                flags.append("insufficient_positive_support")
        results.append({"sku": sku, "trend_pct": trend_pct, "trend_factor": 1 + trend_pct / 100, "support": support, "flags": tuple(flags)})
    return pd.DataFrame(results, columns=["sku", "trend_pct", "trend_factor", "support", "flags"])
