"""Explicit stockout lost-demand restoration after outlier cleaning."""

from __future__ import annotations

import pandas as pd

from procure.calc.outliers import clean_outlier_demand


_STOCKOUT_COLUMNS = {"sku", "month", "is_stockout"}
_SUMMARY_COLUMNS = [
    "sku", "base_demand", "restored_demand", "stockout_correction",
    "total_lost_demand", "stockout_months", "reference_level", "flags",
]


def _stockout_flags(stockout: pd.DataFrame) -> pd.DataFrame:
    """Validate the explicit stockout source and normalize its boolean flag."""
    missing = _STOCKOUT_COLUMNS.difference(stockout.columns)
    if missing:
        raise ValueError(f"stockout is missing required columns: {sorted(missing)}")
    flags = stockout[["sku", "month", "is_stockout"]].copy()
    normalized = flags["is_stockout"].astype(str).str.lower().map({"true": True, "false": False})
    if normalized.isna().any():
        raise ValueError("is_stockout must contain only true or false values")
    flags["is_stockout"] = normalized
    if flags.duplicated(["sku", "month"]).any():
        raise ValueError("stockout contains duplicate sku/month rows")
    return flags


def restore_stockout_demand(sales: pd.DataFrame, stockout: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return SKU restoration summaries and monthly evidence from explicit stockouts.

    ``base_demand`` is the mean cleaned demand across all observed months.  For a
    flagged month, only demand below the median of explicitly non-stockout months
    is restored.  Missing explicit coverage or fewer than six non-stockout months
    safely produces no correction.
    """
    cleaned_sales, _ = clean_outlier_demand(sales)
    monthly = cleaned_sales.groupby(["sku", "month"], as_index=False)["cleaned_qty"].sum()
    monthly = _stockout_flags(stockout).merge(monthly, on=["sku", "month"], how="outer", validate="one_to_one")
    monthly["has_explicit_stockout_state"] = monthly["is_stockout"].notna()
    monthly["observed_cleaned_demand"] = monthly["cleaned_qty"].fillna(0.0)

    summaries: list[dict[str, object]] = []
    evidence: list[pd.DataFrame] = []
    for sku, sku_months in monthly.groupby("sku", sort=True):
        item = sku_months.copy()
        base = float(item["observed_cleaned_demand"].mean())
        flags: list[str] = []
        reference: float | None = None
        if not item["has_explicit_stockout_state"].all():
            flags.append("incomplete_stockout_coverage")
        item["is_stockout"] = item["is_stockout"].fillna(False).astype(bool)
        non_stockout = item.loc[~item["is_stockout"]]
        if len(non_stockout) < 6:
            flags.append("insufficient_history")
        elif item["has_explicit_stockout_state"].all():
            reference = float(non_stockout["observed_cleaned_demand"].median())

        item["reference_level"] = reference
        item["lost_demand"] = 0.0
        if reference is not None:
            item.loc[item["is_stockout"], "lost_demand"] = (
                reference - item.loc[item["is_stockout"], "observed_cleaned_demand"]
            ).clip(lower=0)
        item["restored_monthly_demand"] = item["observed_cleaned_demand"] + item["lost_demand"]
        total_lost = float(item["lost_demand"].sum())
        restored = float(item["restored_monthly_demand"].mean())
        summaries.append({
            "sku": sku,
            "base_demand": base,
            "restored_demand": restored,
            "stockout_correction": restored - base,
            "total_lost_demand": total_lost,
            "stockout_months": tuple(item.loc[item["is_stockout"], "month"]),
            "reference_level": reference,
            "flags": tuple(flags),
        })
        evidence.append(item[["sku", "month", "is_stockout", "observed_cleaned_demand", "reference_level", "lost_demand", "restored_monthly_demand"]])
    return pd.DataFrame(summaries, columns=_SUMMARY_COLUMNS), pd.concat(evidence, ignore_index=True)
