"""Deterministic substitution for recommendation explanations."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping


PLACEHOLDERS = frozenset(
    {
        "regular_demand",
        "naive_demand",
        "excluded_outlier",
        "outlier_client",
        "stockout_correction",
        "stockout_months",
        "season_factor",
        "trend_factor",
        "stock",
        "in_transit",
        "lead_time",
        "days_of_cover",
        "recommended_qty",
    }
)

_QUANTITIES = frozenset(
    {
        "regular_demand",
        "naive_demand",
        "excluded_outlier",
        "stockout_correction",
        "stock",
        "in_transit",
        "recommended_qty",
    }
)
_DAYS = frozenset({"lead_time", "days_of_cover"})
_FACTORS = frozenset({"season_factor", "trend_factor"})
_PLACEHOLDER = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}")
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
_THIN_SPACE = "\u2009"


def _number(value: object, placeholder: str) -> float:
    if isinstance(value, bool):
        raise TypeError(f"{placeholder} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{placeholder} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{placeholder} must be finite")
    return number


def _integer(value: object, placeholder: str) -> str:
    rounded = round(_number(value, placeholder))
    return f"{rounded:,}".replace(",", _THIN_SPACE)


def _format_value(placeholder: str, value: object) -> str:
    if placeholder in _QUANTITIES:
        return f"{_integer(value, placeholder)} шт"
    if placeholder in _DAYS:
        return f"{_integer(value, placeholder)} дн"
    if placeholder in _FACTORS:
        return f"{_number(value, placeholder):.2f}"
    if placeholder == "stockout_months":
        return f"{_integer(value, placeholder)} мес"
    return str(value)


def render_template(template: str, values: Mapping[str, object | None]) -> str:
    """Substitute the closed placeholder set and omit sentences with ``None``."""

    names = set(_PLACEHOLDER.findall(template))
    unknown = names - PLACEHOLDERS
    if unknown:
        raise ValueError(f"unknown placeholder: {sorted(unknown)[0]}")

    missing = names - values.keys()
    if missing:
        raise KeyError(f"missing value for placeholder: {sorted(missing)[0]}")

    rendered: list[str] = []
    for sentence in _SENTENCE_BOUNDARY.split(template.strip()):
        sentence_names = set(_PLACEHOLDER.findall(sentence))
        if any(values[name] is None for name in sentence_names):
            continue

        def substitute(match: re.Match[str]) -> str:
            name = match.group(1)
            return _format_value(name, values[name])

        rendered_sentence = _PLACEHOLDER.sub(substitute, sentence).strip()
        if rendered_sentence:
            rendered.append(rendered_sentence)
    return " ".join(rendered)


render = render_template
