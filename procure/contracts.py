"""Frozen data contracts for the replenishment pipeline."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SalesRow:
    date: str
    sku: str
    qty: float
    price: float
    client_id: str
    warehouse: str


@dataclass(frozen=True)
class ItemFacts:
    sku: str
    name: str
    supplier: str
    raw_demand: float
    base_demand: float
    restored_demand: float
    season_factor: float
    trend_pct: float
    lead_time_days: int
    review_days: int
    horizon_need: float
    safety_stock: float
    stock: float
    in_transit: float
    days_of_cover: float
    history_months: int
    stockout_months: int
    outlier_qty: float | None
    outlier_client: str | None
    pack_size: int
    naive_qty: float
    recommended_qty: float
    urgency: str
    flags: tuple[str, ...]


@dataclass(frozen=True)
class Explanation:
    sku: str
    text: str
    source: str
