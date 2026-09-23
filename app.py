"""Streamlit presentation of the deterministic supplier-order pipeline."""

from __future__ import annotations

import shutil
import tempfile
import re
from html import escape
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from procure.contracts import ItemFacts
from procure.calc.order import group_by_supplier
from procure.run import build_item_facts
from procure.ai.template import build_template_explanation


SUPPLIERS = {"SUP-01": "«Каз Кабель»", "SUP-02": "«Свет Групп»", "SUP-03": "«ЭлектроПром»"}
URGENCY = {"high": ("▲ Срочно", 0), "unknown": ("? Нет данных", 1), "medium": ("● Скоро", 2), "low": ("○ Запас есть", 3)}


def load_items(in_transit_overrides: dict[str, int] | None = None) -> list[ItemFacts]:
    """Run the deterministic pipeline with optional temporary transit edits."""
    data_dir = Path(__file__).parent / "data"
    if not in_transit_overrides:
        return build_item_facts(data_dir)
    with tempfile.TemporaryDirectory() as temporary_directory:
        temporary_data = Path(temporary_directory)
        for filename in ("sales.csv", "stock.csv", "stockout.csv"):
            shutil.copy2(data_dir / filename, temporary_data / filename)
        stock = pd.read_csv(temporary_data / "stock.csv")
        for sku, in_transit in in_transit_overrides.items():
            stock.loc[stock["sku"] == sku, "in_transit"] = in_transit
        stock.to_csv(temporary_data / "stock.csv", index=False)
        return build_item_facts(temporary_data)


def qty(value: float | None) -> str:
    return "—" if value is None else f"{value:,.0f}".replace(",", " ") + " шт"


def number(value: float | None, suffix: str) -> str:
    if value is None:
        return "Не рассчитано"
    formatted = f"{value:,.0f}" if round(float(value), 1).is_integer() else f"{value:,.1f}"
    return formatted.replace(",", " ").replace(".", ",") + suffix


def order_qty(item: ItemFacts) -> int | None:
    manual = st.session_state.manual_overrides.get(item.sku)
    if manual is not None:
        return int(manual)
    return None if item.urgency == "unknown" else int(item.recommended_qty)


def sorted_supplier_items(items: list[ItemFacts]) -> list[ItemFacts]:
    return sorted(items, key=lambda item: (URGENCY.get(item.urgency, URGENCY["unknown"])[1], item.days_of_cover, item.sku))


def select_supplier_item(supplier: str, skus: tuple[str, ...]) -> None:
    click = st.session_state.get(f"select_{supplier}")
    if click is not None and 0 <= click.row < len(skus):
        st.session_state.selected_sku = skus[click.row]


def approve_supplier(supplier: str) -> None:
    st.session_state.approval_flags[supplier] = True
    st.session_state.approved[supplier] = datetime.now().strftime("%H:%M")


def record_order_edits(supplier: str, skus: tuple[str, ...]) -> None:
    if st.session_state.approval_flags.get(supplier, False):
        return
    edited_rows = st.session_state[f"table_{supplier}"].get("edited_rows", {})
    for row, changes in edited_rows.items():
        if "К заказу" not in changes:
            continue
        sku = skus[int(row)]
        value = int(changes["К заказу"])
        if st.session_state.manual_overrides.get(sku) != value:
            st.session_state.manual_overrides[sku] = value
            st.session_state.recommendation_at_manual_edit[sku] = st.session_state.current_recommendations[sku]


def save_in_transit(sku: str) -> None:
    st.session_state.in_transit_by_sku[sku] = int(st.session_state[f"_in_transit_widget_{sku}"])


def supplier_table(items: list[ItemFacts], supplier: str) -> pd.DataFrame:
    rows = []
    for item in sorted_supplier_items(items):
        urgency_text, _ = URGENCY.get(item.urgency, URGENCY["unknown"])
        selection = "▸ " if item.sku == st.session_state.selected_sku else ""
        recommendation = None if item.urgency == "unknown" else item.recommended_qty
        rows.append({"Срочность": urgency_text, "Товар": f"{selection}{item.sku} · {item.name}", "Excel": qty(item.naive_qty), "Рекомендуем": qty(recommendation), "К заказу": order_qty(item)})
    return pd.DataFrame(rows)


def calculation_steps(item: ItemFacts) -> pd.DataFrame:
    correction = item.restored_demand - item.base_demand
    return pd.DataFrame([
        ("Очистка истории", number(item.base_demand, " шт/мес."), "Разовая продажа исключена" if item.outlier_qty else "Без исключений"),
        ("Восстановление stockout", number(correction, " шт/мес."), f"Периодов: {item.stockout_months}"),
        ("× Сезон", f"×{display_factor(item.season_factor)}", "Месячный коэффициент"),
        ("× Устойчивый рост", f"×{display_factor(1 + item.trend_pct / 100)}", f"{item.trend_pct:+.0f}% год к году"),
        ("Прогноз на горизонт", qty(item.horizon_need), f"Срок поставки {item.lead_time_days} дн + запас {item.review_days} дн"),
        ("Остаток и поступления", f"− {qty(item.stock)} · − {qty(item.in_transit)}", "Вычитаются после прогноза"),
    ], columns=["Шаг", "Значение", "Пояснение"])


def display_factor(value: float) -> str:
    return f"{value:.2f}".replace(".", ",")


def signed_qty(value: float) -> str:
    sign = "−" if value < 0 else "+"
    return f"{sign}{qty(abs(value))}"


def difference_copy(item: ItemFacts) -> str:
    difference = int(item.recommended_qty - item.naive_qty)
    if abs(difference) <= 2:
        return "Совпадает с Excel"
    if difference < 0:
        return f"На {qty(-difference)} меньше Excel"
    return f"На {qty(difference)} больше Excel: без этого риск дефицита"


def position_count(value: int) -> str:
    word = "позиция" if value % 10 == 1 and value % 100 != 11 else "позиции" if value % 10 in (2, 3, 4) and value % 100 not in (12, 13, 14) else "позиций"
    return f"{value} {word}"


def reason_for_item(item: ItemFacts) -> str:
    if abs(item.naive_qty - item.recommended_qty) <= 2:
        return "Совпадает с Excel"
    if item.outlier_qty and item.outlier_qty > 0:
        return f"Главная причина: Excel учёл разовую продажу {qty(item.outlier_qty)} как обычный спрос."
    if item.stockout_months > 0:
        correction = item.restored_demand - item.base_demand
        return f"Excel не учёл {item.stockout_months} месяца без товара на складе: восстановлено около +{qty(correction).replace(' шт', ' шт/мес.')}"
    if item.trend_pct > 5:
        return f"Excel не учёл рост продаж {item.trend_pct:+.0f}%."
    if item.season_factor > 1.2:
        return f"Excel не учёл сезон: сейчас спрос в {display_factor(item.season_factor)} раза выше обычного."
    return f"Сезонный коэффициент {display_factor(item.season_factor)} скорректировал спрос."


def outlier_calculation_steps(item: ItemFacts) -> pd.DataFrame:
    horizon_days = item.lead_time_days + item.review_days
    return pd.DataFrame([
        (f"Средние продажи за {item.history_months} мес", qty(item.raw_demand).replace(" шт", " шт/мес")),
        (f"− Разовая продажа {qty(item.outlier_qty)} ({item.outlier_client})", signed_qty(item.base_demand - item.raw_demand).replace(" шт", " шт/мес")),
        (f"× Сезон {display_factor(item.season_factor)}", f"= {number(item.base_demand * item.season_factor, ' шт/мес')}"),
        (f"Нужно на {horizon_days} дней", qty(item.horizon_need)),
        ("− Остаток", f"−{qty(item.stock)}"),
        ("− В пути", f"−{qty(item.in_transit)}"),
        ("= Рекомендуем", qty(item.recommended_qty)),
    ], columns=["Шаг", "Значение"])


st.set_page_config(page_title="Заказы поставщикам", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""<style>
:root { --navy:#122247; --blue:#1769e0; --muted:#64748b; --line:#dce5f0; --surface:#f5f8fc; --amber:#9a5c00; }
.block-container { max-width:1600px; padding:32px clamp(48px,5.5vw,80px) 64px; }
h1 { color:var(--navy); font-size:2.25rem!important; letter-spacing:-.04em; margin-bottom:0!important; }
.metric { box-sizing:border-box; display:flex; flex-direction:column; justify-content:space-between; height:128px; border:1px solid var(--line); border-radius:12px; padding:16px; }
.metric-label { color:var(--muted); font-size:.82rem; line-height:1.3; }
.metric-value { color:var(--navy); font-size:1.7rem; line-height:1.1; font-weight:700; }
.metric-note { color:var(--muted); font-size:.72rem; line-height:1.3; }
.kpi-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:16px; }
.st-key-supplier-layout [data-testid="stHorizontalBlock"] { gap:24px!important; }
.st-key-supplier-layout h3 { color:var(--navy); font-size:1.05rem!important; margin:24px 0 12px!important; }
.st-key-detail-card [data-testid="stVerticalBlock"] { gap:8px!important; }
.detail-title { color:var(--navy); font-size:1rem; font-weight:700; line-height:1.35; margin:0; }
.comparison { display:flex; flex-wrap:wrap; align-items:baseline; gap:8px; }
.cmp-old { color:#8593a8; text-decoration:line-through; font-size:1rem; }
.cmp-arrow { color:var(--muted); font-size:1.2rem; }
.cmp-new { color:var(--blue); font-weight:750; font-size:1.8rem; line-height:1.15; }
.cmp-label { color:var(--muted); font-size:.85rem; margin:0; }
.reason-main { color:var(--navy); font-size:.9rem; font-weight:600; line-height:1.35; margin:4px 0 8px; }
.fair-copy { color:var(--muted); font-size:.75rem; line-height:1.35; margin:0; }
.order-choice { color:var(--navy); font-weight:650; font-size:1rem; margin-bottom:8px; }
.bar { height:8px; border-radius:99px; background:#e9eff7; overflow:hidden; margin:4px 0 8px; }
.bar span { display:block; height:100%; background:var(--blue); }
.fact { display:flex; justify-content:space-between; border-bottom:1px solid #edf1f6; padding:8px 0; color:var(--muted); font-size:.88rem; }
.fact b { color:var(--navy); }
.excluded { background:#fff7e8; border:1px solid #f3dfb1; border-radius:9px; color:#805000; padding:12px 16px; font-size:.85rem; margin:16px 0; }
.stDataFrame, [data-testid="stDataEditor"] { border:1px solid var(--line); border-radius:10px; overflow:hidden; }
.st-key-supplier-layout button { min-height:40px; padding-inline:16px; }
@media (max-width:1100px) {
  .kpi-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .st-key-supplier-layout [data-testid="stHorizontalBlock"] { flex-wrap:wrap!important; }
  .st-key-supplier-layout [data-testid="stColumn"] { min-width:100%!important; width:100%!important; flex:1 1 100%!important; }
}
</style>""", unsafe_allow_html=True)

data_dir = Path(__file__).parent / "data"
source_version = tuple((data_dir / name).stat().st_mtime_ns for name in ("sales.csv", "stock.csv", "stockout.csv"))
if st.session_state.get("source_version") != source_version:
    st.session_state.base_items = load_items()
    st.session_state.source_version = source_version
base_items = st.session_state.base_items
in_transit_by_sku = st.session_state.setdefault("in_transit_by_sku", {})
for item in base_items:
    in_transit_by_sku.setdefault(item.sku, int(item.in_transit))
st.session_state.setdefault("manual_overrides", {})
st.session_state.setdefault("recommendation_at_manual_edit", {})
st.session_state.setdefault("approved", {})
st.session_state.setdefault("approval_flags", {supplier: True for supplier in st.session_state.approved})
default_item = next((item for item in base_items if item.outlier_qty and item.outlier_qty > 0), base_items[0])
if "selected_sku" not in st.session_state:
    st.session_state.selected_sku = default_item.sku
transit_overrides = {
    item.sku: int(in_transit_by_sku[item.sku])
    for item in base_items
    if int(in_transit_by_sku[item.sku]) != int(item.in_transit)
}
items = load_items(transit_overrides) if transit_overrides else base_items
st.session_state.current_recommendations = {item.sku: int(item.recommended_qty) for item in items}

st.title("Заказы поставщикам")
st.caption("Рекомендация системы. Решение и отправку делает менеджер.")
recommended_items = [item for item in items if item.recommended_qty > 0]
excess_items = [item for item in items if item.naive_qty > item.recommended_qty]
shortage_items = [item for item in items if item.recommended_qty > item.naive_qty]
metric_values = [
    ("К заказу", position_count(len(recommended_items)), "по всем поставщикам"),
    ("Срочных", f"{sum(item.urgency == 'high' for item in items)}", "требуют внимания"),
    ("Excel заказал бы лишнего", qty(sum(item.naive_qty - item.recommended_qty for item in excess_items)), f"{position_count(len(excess_items))} · замороженные деньги"),
    ("Excel недозаказал бы", qty(sum(item.recommended_qty - item.naive_qty for item in shortage_items)), f"{position_count(len(shortage_items))} · риск дефицита"),
]
st.markdown(
    '<div class="kpi-grid">' + ''.join(
        f'<div class="metric"><div class="metric-label">{label}</div><div class="metric-value">{value}</div><div class="metric-note">{note}</div></div>'
        for label, value, note in metric_values
    ) + '</div>',
    unsafe_allow_html=True,
)

left, right = st.container(key="supplier-layout").columns([3, 2])
with left:
    for supplier, supplier_items in group_by_supplier(items).items():
        lead_times = sorted({item.lead_time_days for item in supplier_items})
        lead_label = str(lead_times[0]) if len(lead_times) == 1 else f"{lead_times[0]}–{lead_times[-1]}"
        st.subheader(f"{SUPPLIERS[supplier]} · {position_count(len(supplier_items))} · срок {lead_label} дн")
        locked = st.session_state.approval_flags.get(supplier, False)
        ordered_items = sorted_supplier_items(supplier_items)
        table_data = supplier_table(supplier_items, supplier)
        st.data_editor(
            table_data,
            hide_index=True,
            disabled=True if locked else ["Срочность", "Excel", "Рекомендуем"],
            column_config={
                "Срочность": st.column_config.TextColumn(width=100),
                "Товар": st.column_config.ButtonColumn(
                    "Товар", width=240, alignment="left", type="tertiary",
                    help="Выберите товар для просмотра справа",
                    on_click=select_supplier_item,
                    args=(supplier, tuple(item.sku for item in ordered_items)),
                    key=f"select_{supplier}",
                ),
                "Excel": st.column_config.TextColumn(width=70, alignment="right"),
                "Рекомендуем": st.column_config.TextColumn(width=95, alignment="right"),
                "К заказу": st.column_config.NumberColumn("К заказу", min_value=0, step=1, format="%d шт", width=85, alignment="right", help="Измените количество перед утверждением"),
            },
            key=f"table_{supplier}",
            on_change=record_order_edits,
            args=(supplier, tuple(item.sku for item in ordered_items)),
            width="stretch",
        )
        changes = []
        for item in ordered_items:
            if item.sku in st.session_state.manual_overrides:
                original_recommendation = st.session_state.recommendation_at_manual_edit[item.sku]
                changes.append(f"Изменено вручную: {item.name} — {qty(st.session_state.manual_overrides[item.sku])} вместо {qty(original_recommendation)}")
                if int(item.recommended_qty) != original_recommendation:
                    changes.append(f"Рекомендация изменилась: {qty(item.recommended_qty)}")
        for change in changes:
            st.caption(change)
        if locked:
            st.success(f"Утверждено вами, {st.session_state.approved[supplier]}. Отправка поставщику — вручную.")
        else:
            st.button(f"Утвердить заказ: {SUPPLIERS[supplier]}", key=f"approve_{supplier}", type="primary", on_click=approve_supplier, args=(supplier,))

with right:
    st.subheader("Выбранная позиция")
    with st.container(border=True, key="detail-card"):
        selected_sku = st.selectbox("Позиция", [item.sku for item in items], key="selected_sku", label_visibility="collapsed", format_func=lambda sku: next(item.name for item in items if item.sku == sku))
        selected = next(item for item in items if item.sku == selected_sku)
        selected_base = next(item for item in base_items if item.sku == selected_sku)
        st.markdown(f'<div class="detail-title">{escape(selected.sku)} · {escape(selected.name)}</div>', unsafe_allow_html=True)
        if selected.urgency == "unknown":
            st.caption("Рекомендуем: —")
            st.caption("Не рассчитано: недостаточно данных для рекомендации.")
            st.stop()
        st.markdown(
            f'<div class="comparison"><span class="cmp-old">Excel: {qty(selected.naive_qty)}</span>'
            f'<span class="cmp-arrow">→</span><span class="cmp-new">{qty(selected.recommended_qty)}</span></div>'
            f'<div class="cmp-label">{difference_copy(selected)}</div>',
            unsafe_allow_html=True,
        )
        naive_width = min(100, selected.naive_qty / max(selected.naive_qty, selected.recommended_qty, 1) * 100)
        recommended_width = min(100, selected.recommended_qty / max(selected.naive_qty, selected.recommended_qty, 1) * 100)
        st.markdown(f'<div class="bar"><span style="width:{naive_width:.0f}%"></span></div><div class="bar"><span style="width:{recommended_width:.0f}%"></span></div>', unsafe_allow_html=True)
        st.markdown('<div class="fair-copy">Excel: среднее за 24 месяца на тот же срок, минус остаток и товары в пути.</div>', unsafe_allow_html=True)
        if abs(selected.recommended_qty - selected.naive_qty) > 2:
            st.markdown(f'<div class="reason-main">{reason_for_item(selected)}</div>', unsafe_allow_html=True)
        if selected.outlier_qty:
            st.dataframe(outlier_calculation_steps(selected), hide_index=True, width="stretch")
            st.caption(f"Срок поставки {selected.lead_time_days} дн + запас {selected.review_days} дн. Промежуточные значения округлены только для показа; итог рассчитан из точных значений.")
            st.markdown(f'<div class="excluded">Исключена разовая продажа {qty(selected.outlier_qty)} ({selected.outlier_client})</div>', unsafe_allow_html=True)
        else:
            st.dataframe(calculation_steps(selected), hide_index=True, width="stretch")
        st.markdown(f'<div class="order-choice">К заказу: {qty(order_qty(selected))}</div>', unsafe_allow_html=True)
        for label, value in [("Остаток", qty(selected.stock)), ("Хватит на", qty(selected.days_of_cover).replace(" шт", " дн")), ("Срок поставки", f"{selected.lead_time_days} дн")]:
            st.markdown(f'<div class="fact"><span>{label}</span><b>{value}</b></div>', unsafe_allow_html=True)
        selected_transit_key = f"_in_transit_widget_{selected.sku}"
        if selected_transit_key not in st.session_state:
            st.session_state[selected_transit_key] = int(in_transit_by_sku[selected.sku])
        st.number_input("В пути, шт", min_value=0, step=1, key=selected_transit_key, on_change=save_in_transit, args=(selected.sku,))
        if int(in_transit_by_sku[selected.sku]) != int(selected_base.in_transit):
            st.metric("Рекомендуем", qty(selected.recommended_qty), delta=f"{signed_qty(selected.recommended_qty - selected_base.recommended_qty)}: учтены товары в пути", delta_color="inverse")
        with st.container(border=True):
            st.subheader("Объяснение системы")
            st.caption("Числа рассчитаны системой. Генеративный ИИ не подключён.")
            st.markdown("**Системные данные**")
            st.markdown(
                f"Текущий SKU: {selected.sku}  \n"
                f"Excel: {qty(selected.naive_qty)}  \n"
                f"Рекомендуем: {qty(selected.recommended_qty)}  \n"
                f"К заказу: {qty(order_qty(selected))}  \n"
                f"В пути: {qty(selected.in_transit)}"
            )
            st.markdown(reason_for_item(selected))
            explanation = build_template_explanation(selected)
            st.caption(re.sub(r"(?<=\d)\.(?=\d)", ",", explanation.text))
            st.caption("ИИ-помощник: не подключён")
            st.caption("Расчёт и объяснение работают без внешней модели.")
