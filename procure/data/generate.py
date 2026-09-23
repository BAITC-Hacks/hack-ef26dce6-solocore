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
    ("A-100", "ВВГнг-LS 3x2.5 бухта 100 м", "SUP-01", 30, 55, 0, 1, "Кабель", "бухта", 145000),
    ("A-200", "Удлинитель садовый 20 м IP44", "SUP-03", 45, 45, 20, 1, "Розетки", "шт", 18500),
    ("A-300", "Светильник LED 36 Вт IP65", "SUP-02", 30, 35, 0, 1, "Светотехника", "шт", 8900),
    ("A-400", "Автомат ВА47-29 3P 25А", "SUP-03", 30, 20, 0, 1, "Автоматика", "шт", 7200),
    ("A-500", "Щит распределительный ЩРН-24", "SUP-03", 21, 10, 0, 1, "Щиты", "шт", 24500),
    ("A-600", "ВВГнг-LS 3x1.5 бухта 100 м", "SUP-01", 30, 40, 0, 1, "Кабель", "бухта", 98000),
    ("A-700", "ПВС 2x1.5 бухта 100 м", "SUP-01", 30, 100, 0, 1, "Кабель", "бухта", 76000),
    ("A-800", "Прожектор LED 50 Вт IP65", "SUP-02", 30, 25, 0, 1, "Светотехника", "шт", 11200),
    ("A-900", "Лампа LED E27 11 Вт", "SUP-02", 21, 160, 0, 1, "Светотехника", "шт", 1150),
    ("A-1000", "Автомат ВА47-29 1P 16А", "SUP-03", 21, 120, 0, 1, "Автоматика", "шт", 1450),
    ("A-1100", "УЗО 2P 40А 30мА", "SUP-03", 30, 25, 0, 1, "Автоматика", "шт", 9800),
    ("A-1200", "Щит ЩРН-12", "SUP-03", 21, 40, 0, 1, "Щиты", "шт", 14800),
)

_ORDINARY_RANGES = {
    "A-600": (65, 81), "A-700": (45, 61), "A-800": (30, 46),
    "A-900": (95, 126), "A-1000": (70, 96), "A-1100": (28, 46), "A-1200": (18, 33),
}


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
    if sku in _ORDINARY_RANGES:
        lower, upper = _ORDINARY_RANGES[sku]
        return int(rng.integers(lower, upper))
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
        writer.writerow(("sku", "name", "supplier", "lead_time_days", "stock", "in_transit", "pack_size", "category", "unit", "price_kzt"))
        writer.writerows(STOCK_ROWS)

    with (destination / "stockout.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(("sku", "month", "is_stockout"))
        writer.writerows(
            (sku, month, str(sku == "A-400" and month in ("2026-04", "2026-05")).lower())
            for sku, *_ in STOCK_ROWS
            for month in MONTHS
        )
