"""Static UI-01 fixtures; deliberately independent of calculation modules."""

from procure.contracts import ItemFacts


def fixture_items() -> list[ItemFacts]:
    """Return five deterministic electrical-wholesale rows for the Streamlit screen."""
    return [
        ItemFacts("A-100", "Кабель ВВГнг-LS 3x2.5, бухта 100 м", "SUP-01", 101, 100, 100, 1.0, 0.0, 30, 14, 147, 0, 55, 0, 16.5, 24, 0, None, None, 1, 46, 92, "low", ("stable",)),
        ItemFacts("A-200", "Удлинитель садовый 20 м, IP44", "SUP-01", 112, 78, 78, 1.48, 0.0, 45, 14, 153, 0, 45, 20, 17.3, 24, 0, None, None, 1, 103, 88, "unknown", ("seasonal",)),
        ItemFacts("A-300", "Светильник LED 36 Вт, IP65", "SUP-02", 89, 86, 86, 1.0, 12.5, 30, 14, 126, 0, 35, 0, 11.9, 24, 0, None, None, 1, 54, 91, "medium", ("growth",)),
        ItemFacts("A-400", "Автомат ВА47-29 3P 25А", "SUP-02", 72, 72, 90, 1.0, 0.0, 30, 14, 132, 0, 20, 0, 6.7, 24, 2, None, None, 1, 52, 112, "high", ("stockout_restored",)),
        ItemFacts("A-500", "Щит распределительный ЩРН-24", "SUP-03", 66, 45, 45, 1.0, 0.0, 21, 14, 53, 0, 30, 0, 20.0, 24, 0, 500, "CUST-017", 1, 53, 23, "low", ("one_off_excluded",)),
    ]
