"""Deterministic order quantity, urgency, and supplier grouping."""

from __future__ import annotations

from collections import OrderedDict
from math import ceil

from procure.contracts import ItemFacts


def calculate_order_quantity(demand: float, season_factor: float, trend_factor: float, lead_time_days: int, stock: float, in_transit: float, pack_size: int) -> tuple[int, float, float]:
    """Return final order quantity, expected daily demand, and horizon need."""
    expected_daily = demand * season_factor * trend_factor / 30
    horizon_need = expected_daily * (lead_time_days + 14)
    raw = max(0.0, horizon_need - stock - in_transit)
    quantity = ceil(raw)
    if pack_size > 0:
        quantity = ceil(raw / pack_size) * pack_size
    return int(quantity), expected_daily, horizon_need


def assign_urgency(expected_daily: float, stock: float, lead_time_days: int, reliable_demand: bool = True) -> tuple[str, float]:
    """Return urgency and physical-stock days of cover."""
    if expected_daily <= 0:
        return "unknown", 0.0
    cover = stock / expected_daily
    if cover < lead_time_days:
        return "high", cover
    if cover < lead_time_days + 14:
        return "medium", cover
    return "low", cover


def group_by_supplier(items: list[ItemFacts]) -> OrderedDict[str, list[ItemFacts]]:
    """Group items by supplier in the frozen urgency and cover order."""
    urgency_rank = {"high": 0, "unknown": 1, "medium": 2, "low": 3}
    grouped: dict[str, list[ItemFacts]] = {}
    for item in items:
        grouped.setdefault(item.supplier or "NO_SUPPLIER", []).append(item)
    for supplier, members in grouped.items():
        grouped[supplier] = sorted(members, key=lambda item: (urgency_rank[item.urgency], item.days_of_cover, item.sku))
    supplier_order = sorted(grouped, key=lambda supplier: (urgency_rank[grouped[supplier][0].urgency], grouped[supplier][0].days_of_cover, supplier))
    return OrderedDict((supplier, grouped[supplier]) for supplier in supplier_order)
