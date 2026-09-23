"""Deterministic detection of one-off customer demand anomalies."""

from __future__ import annotations

import pandas as pd


_REQUIRED_COLUMNS = {"date", "sku", "qty", "customer_id"}
_EVENT_COLUMNS = ["sku", "month", "customer_id", "excluded_qty", "month_total", "median_month", "mad", "robust_z", "customer_share", "reason"]


def _with_month(sales: pd.DataFrame) -> pd.DataFrame:
    """Validate sales rows and attach their calendar month without mutating input."""
    missing = _REQUIRED_COLUMNS.difference(sales.columns)
    if missing:
        raise ValueError(f"sales is missing required columns: {sorted(missing)}")
    result = sales.copy()
    result["month"] = pd.to_datetime(result["date"], errors="raise").dt.to_period("M").astype(str)
    return result


def detect_one_off_orders(sales: pd.DataFrame) -> pd.DataFrame:
    """Return evidence for large, concentrated, non-repeating customer purchases."""
    rows = _with_month(sales)
    monthly = rows.groupby(["sku", "month"], as_index=False)["qty"].sum().rename(columns={"qty": "month_total"})
    monthly = monthly.join(monthly.groupby("sku")["month_total"].median().rename("median_month"), on="sku")
    monthly["abs_deviation"] = (monthly["month_total"] - monthly["median_month"]).abs()
    monthly = monthly.join(monthly.groupby("sku")["abs_deviation"].median().rename("mad"), on="sku")
    positive_mad = monthly["mad"] > 0
    monthly["robust_z"] = float("nan")
    monthly.loc[positive_mad, "robust_z"] = (0.6745 * (monthly.loc[positive_mad, "month_total"] - monthly.loc[positive_mad, "median_month"]) / monthly.loc[positive_mad, "mad"])
    fallback_threshold = 3 * monthly["median_month"].clip(lower=1)
    monthly["is_candidate"] = ((positive_mad & (monthly["robust_z"].astype(float) > 3.5)) | (~positive_mad & (monthly["month_total"] >= fallback_threshold)))
    customer_monthly = rows.groupby(["sku", "month", "customer_id"], as_index=False)["qty"].sum().rename(columns={"qty": "customer_qty"})
    candidates = monthly.loc[monthly["is_candidate"], ["sku", "month", "month_total", "median_month", "mad", "robust_z"]]
    candidate_customers = candidates.merge(customer_monthly, on=["sku", "month"], validate="one_to_many")
    if candidate_customers.empty:
        return pd.DataFrame(columns=_EVENT_COLUMNS)
    candidate_customers["customer_share"] = candidate_customers["customer_qty"] / candidate_customers["month_total"]
    candidate_customers = candidate_customers.loc[(candidate_customers["customer_share"] >= 0.50) & (candidate_customers["customer_qty"] >= 3 * candidate_customers["median_month"].clip(lower=1))].copy()
    events: list[dict[str, object]] = []
    for candidate in candidate_customers.itertuples(index=False):
        same_customer = customer_monthly.loc[(customer_monthly["sku"] == candidate.sku) & (customer_monthly["customer_id"] == candidate.customer_id) & (customer_monthly["month"] != candidate.month)]
        if (same_customer["customer_qty"] >= 0.50 * candidate.customer_qty).any():
            continue
        events.append({"sku": candidate.sku, "month": candidate.month, "customer_id": candidate.customer_id, "excluded_qty": candidate.customer_qty, "month_total": candidate.month_total, "median_month": candidate.median_month, "mad": candidate.mad, "robust_z": candidate.robust_z, "customer_share": candidate.customer_share, "reason": "monthly_spike_concentrated_non_repeating_customer"})
    return pd.DataFrame(events, columns=_EVENT_COLUMNS).sort_values(["sku", "month", "customer_id"], ignore_index=True)


def clean_outlier_demand(sales: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Preserve sales rows while excluding detected events from ``cleaned_qty``."""
    cleaned = _with_month(sales)
    events = detect_one_off_orders(sales)
    event_keys = set(events[["sku", "month", "customer_id"]].itertuples(index=False, name=None))
    cleaned["is_one_off"] = [(sku, month, customer_id) in event_keys for sku, month, customer_id in cleaned[["sku", "month", "customer_id"]].itertuples(index=False, name=None)]
    cleaned["cleaned_qty"] = cleaned["qty"].where(~cleaned["is_one_off"], 0.0)
    return cleaned, events
