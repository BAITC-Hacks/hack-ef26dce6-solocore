"""Deterministic Russian explanations built from frozen item facts."""

from __future__ import annotations

import math
from dataclasses import dataclass

from procure.ai.render import render_template
from procure.contracts import Explanation, ItemFacts


MAX_EXPLANATION_LENGTH = 300


@dataclass(frozen=True)
class _Sentence:
    template: str
    protected: bool = False


def _sentence_specs(facts: ItemFacts) -> list[_Sentence]:
    if facts.recommended_qty == 0:
        recommendation = (
            "Рекомендуем {{recommended_qty}}: заказ не требуется."
        )
    else:
        recommendation = "Рекомендуем {{recommended_qty}}."

    sentences = [
        _Sentence("Регулярный спрос — {{regular_demand}}.", protected=True),
        _Sentence(recommendation, protected=True),
    ]
    if facts.outlier_qty is not None and facts.outlier_client is not None:
        sentences.append(
            _Sentence(
                "Без очистки спрос — {{naive_demand}}; исключена разовая продажа "
                "{{excluded_outlier}} клиенту {{outlier_client}}.",
                protected=True,
            )
        )
    if facts.stockout_months > 0:
        sentences.append(
            _Sentence(
                "Поправка к месячному спросу за {{stockout_months}} отсутствия — "
                "{{stockout_correction}}.",
                protected=True,
            )
        )
    if facts.season_factor > 1.2:
        sentences.append(
            _Sentence(
                "Поставка придёт в высокий сезон (коэффициент {{season_factor}}), "
                "поэтому объём выше среднегодового.",
            )
        )
    elif not math.isclose(facts.season_factor, 1.0):
        sentences.append(_Sentence("Сезонный коэффициент — {{season_factor}}."))

    trend_factor = 1.0 + facts.trend_pct / 100.0
    if trend_factor > 1.05:
        sentences.append(
            _Sentence(
                f"Спрос растёт на {facts.trend_pct:.1f}% год к году.".replace(".", ","),
            )
        )
    elif not math.isclose(trend_factor, 1.0):
        sentences.append(_Sentence("Коэффициент тренда — {{trend_factor}}."))

    if facts.stock != 0 and facts.in_transit != 0:
        sentences.append(
            _Sentence("В наличии {{stock}}, в пути {{in_transit}}.")
        )
    elif facts.stock != 0:
        sentences.append(_Sentence("В наличии {{stock}}."))
    elif facts.in_transit != 0:
        sentences.append(_Sentence("В пути {{in_transit}}."))

    sentences.append(
        _Sentence(
            "Покрытие — {{days_of_cover}}, срок поставки — {{lead_time}}."
        )
    )
    return sentences


def build_sentences(facts: ItemFacts) -> list[str]:
    """Return the ordered, unsubstituted sentence templates for ``facts``."""

    return [sentence.template for sentence in _sentence_specs(facts)]


def _values(facts: ItemFacts) -> dict[str, object | None]:
    return {
        "regular_demand": facts.base_demand,
        "naive_demand": facts.raw_demand,
        "excluded_outlier": facts.outlier_qty,
        "outlier_client": facts.outlier_client,
        "stockout_correction": facts.restored_demand - facts.base_demand,
        "stockout_months": facts.stockout_months,
        "season_factor": facts.season_factor,
        "trend_factor": 1.0 + facts.trend_pct / 100.0,
        "stock": facts.stock,
        "in_transit": facts.in_transit,
        "lead_time": facts.lead_time_days,
        "days_of_cover": facts.days_of_cover,
        "recommended_qty": facts.recommended_qty,
    }


def build_template_explanation(facts: ItemFacts) -> Explanation:
    """Build a concise template explanation without changing numeric facts."""

    values = _values(facts)
    sentences = [
        (render_template(spec.template, values), spec.protected)
        for spec in _sentence_specs(facts)
    ]
    sentences = [item for item in sentences if item[0]]

    def joined() -> str:
        return " ".join(text for text, _ in sentences)

    while len(joined()) > MAX_EXPLANATION_LENGTH:
        removable = next(
            (
                index
                for index in range(len(sentences) - 1, -1, -1)
                if not sentences[index][1]
            ),
            None,
        )
        if removable is None:
            raise ValueError("protected explanation sentences exceed 300 characters")
        del sentences[removable]

    return Explanation(sku=facts.sku, text=joined(), source="template")


build_explanation = build_template_explanation
