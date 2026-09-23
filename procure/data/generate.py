"""Deterministic synthetic fixture generation for the demo."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np


SEED = 20260920
WAREHOUSE = "WH-01"
MONTHS = tuple(
    f"{year}-{month:02d}"
    for year in (2024, 2025, 2026)
    for month in range(1, 13)
    if "2024-10" <= f"{year}-{month:02d}" <= "2026-09"
)
CUSTOMERS = tuple(f"CUST-{number:03d}" for number in range(1, 21))

STOCK_ROWS = (
    ("A-100", "STABLE", "SUP-01", 30, 55, 0, 1),
    ("A-200", "SEASONAL", "SUP-01", 45, 45, 20, 1),
    ("A-300", "GROWTH", "SUP-02", 30, 35, 0, 1),
    ("A-400", "STOCKOUT", "SUP-02", 30, 20, 0, 1),
    ("A-500", "OUTLIER", "SUP-03", 21, 10, 0, 1),
)


def _monthly_total(sku: str, month: str, month_index: int, rng: np.random.Generator) -> int:
    """Return a fixture demand total before distributing it across customers."""
    month_number = int(month[-2:])
    if sku == "A-100":
        return int(rng.integers(90, 111))
    if sku == "A-200":
        if month_number in (11, 12, 1):
            return int(rng.integers(130, 161))
        return int(rng.integers(50, 71))
    if sku == "A-300":
        start, end = (40, 65) if month_index < 12 else (65, 100)
        position = month_index if month_index < 12 else month_index - 12
        return round(start + (end - start) * position / 11)
    if sku == "A-400":
        if month in ("2026-04", "2026-05"):
            return int(rng.integers(10, 21))
        return int(rng.integers(85, 96))
    if sku == "A-500":
        return int(rng.integers(40, 56))
    raise ValueError(f"Unsupported SKU: {sku}")


def _sales_rows(rng: np.random.Generator) -> list[tuple[str, str, int, float, str, str]]:
    """Build monthly sales split over several customers for every SKU."""
    rows: list[tuple[str, str, int, float, str, str]] = []
    for sku, *_ in STOCK_ROWS:
        for month_index, month in enumerate(MONTHS):
            total = _monthly_total(sku, month, month_index, rng)
            customer_ids = sorted(rng.choice(CUSTOMERS, size=4, replace=False).tolist())
            weights = rng.multinomial(total - 4, [0.25, 0.25, 0.25, 0.25]) + 1
            for customer_id, quantity in zip(customer_ids, weights, strict=True):
                rows.append((f"{month}-01", sku, int(quantity), 100.0, customer_id, WAREHOUSE))

    rows.append(("2026-03-01", "A-500", 1500, 100.0, "CUST-017", WAREHOUSE))
    return rows


def generate_dataset(output_dir: Path | str = "data") -> None:
    """Write reproducible sales, stock, and stockout fixture CSV files."""
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)

    with (destination / "sales.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(("date", "sku", "qty", "price", "customer_id", "warehouse"))
        writer.writerows(_sales_rows(rng))

    with (destination / "stock.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(("sku", "name", "supplier", "lead_time_days", "stock", "in_transit", "pack_size"))
        writer.writerows(STOCK_ROWS)

    with (destination / "stockout.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(("sku", "month", "is_stockout"))
        writer.writerows(
            (sku, month, str(sku == "A-400" and month in ("2026-04", "2026-05")).lower())
            for sku, *_ in STOCK_ROWS
            for month in MONTHS
        )
