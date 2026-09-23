"""Tests for deterministic recommendation explanations."""

from dataclasses import replace

import pytest

from procure.ai.render import render_template
from procure.ai.template import build_template_explanation
from procure.contracts import ItemFacts


def _facts(**changes: object) -> ItemFacts:
    facts = ItemFacts(
        sku="A-100",
        name="STABLE",
        supplier="SUP-01",
        raw_demand=100.0,
        base_demand=100.0,
        restored_demand=100.0,
        season_factor=1.0,
        trend_pct=0.0,
        lead_time_days=30,
        review_days=14,
        horizon_need=146.67,
        safety_stock=0.0,
        stock=55.0,
        in_transit=0.0,
        days_of_cover=16.5,
        history_months=24,
        stockout_months=0,
        outlier_qty=None,
        outlier_client=None,
        pack_size=1,
        naive_qty=45.0,
        recommended_qty=92.0,
        urgency="high",
        flags=(),
    )
    return replace(facts, **changes)


def test_outlier_explanation_contains_quantity_and_client() -> None:
    explanation = build_template_explanation(
        _facts(
            sku="A-500",
            raw_demand=68.0,
            base_demand=47.0,
            outlier_qty=500.0,
            outlier_client="CUST-017",
        )
    )

    assert "500 шт" in explanation.text
    assert "CUST-017" in explanation.text
    assert explanation.source == "template"


def test_stockout_explanation_mentions_restored_period() -> None:
    explanation = build_template_explanation(
        _facts(
            sku="A-400",
            base_demand=84.46,
            restored_demand=90.29,
            stockout_months=2,
        )
    )

    assert "2 мес отсутствия" in explanation.text
    assert "6 шт" in explanation.text


def test_all_adjustments_fit_and_keep_high_value_sentences() -> None:
    explanation = build_template_explanation(
        _facts(
            sku="A-500",
            raw_demand=1234.0,
            base_demand=734.0,
            restored_demand=760.0,
            outlier_qty=500.0,
            outlier_client="CUST-017",
            stockout_months=2,
            season_factor=1.45,
            trend_pct=30.0,
            stock=1200.0,
            in_transit=300.0,
            days_of_cover=48.0,
            lead_time_days=45,
            recommended_qty=2500.0,
        )
    )

    assert len(explanation.text) <= 300
    assert "500 шт" in explanation.text
    assert "CUST-017" in explanation.text
    assert "2 мес отсутствия" in explanation.text


def test_no_adjustments_still_has_meaningful_advice() -> None:
    text = build_template_explanation(_facts(stock=0.0)).text

    assert "Регулярный спрос" in text
    assert "Рекомендуем 92 шт" in text
    assert "Закажите" not in text


def test_zero_recommendation_explains_that_no_order_is_needed() -> None:
    text = build_template_explanation(_facts(recommended_qty=0.0)).text

    assert "Рекомендуем 0 шт" in text
    assert "заказ не требуется" in text


def test_none_value_removes_whole_sentence() -> None:
    text = render_template(
        "Спрос {{regular_demand}}. Клиент {{outlier_client}}. "
        "Рекомендуем {{recommended_qty}}.",
        {
            "regular_demand": 100,
            "outlier_client": None,
            "recommended_qty": 50,
        },
    )

    assert text == "Спрос 100 шт. Рекомендуем 50 шт."
    assert "Клиент" not in text


def test_render_formats_units_and_rejects_unknown_placeholder() -> None:
    text = render_template(
        "Склад {{stock}}. Срок {{lead_time}}. Сезон {{season_factor}}.",
        {"stock": 1250, "lead_time": 30, "season_factor": 1.2},
    )

    assert text == "Склад 1\u2009250 шт. Срок 30 дн. Сезон 1.20."
    with pytest.raises(ValueError, match="unknown placeholder"):
        render_template("Неизвестно {{price}}.", {"price": 1})
