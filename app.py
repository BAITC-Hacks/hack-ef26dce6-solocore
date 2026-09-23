"""UI-01: Streamlit presentation shell backed by static ItemFacts fixtures."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from procure.contracts import ItemFacts

_FIXTURES_DIR = Path(__file__).parent / "tests" / "fixtures"
if str(_FIXTURES_DIR) not in sys.path:
    sys.path.insert(0, str(_FIXTURES_DIR))
from ui_items import fixture_items


SUPPLIERS = {"SUP-01": "«Каз Кабель»", "SUP-02": "«Свет Групп»", "SUP-03": "«ЭлектроПром»"}
URGENCY = {"high": ("▲ Срочно", 0), "unknown": ("? Нет данных", 1), "medium": ("● Скоро", 2), "low": ("○ Запас есть", 3)}


def load_items() -> list[ItemFacts]:
    """Return fixtures now; the real pipeline will replace this adapter later."""
    return fixture_items()


def qty(value: float | None) -> str:
    return "—" if value is None else f"{value:,.0f}".replace(",", " ") + " шт"


def number(value: float | None, suffix: str) -> str:
    return "Не рассчитано" if value is None else f"{value:,.1f}".replace(",", " ").replace(".", ",") + suffix


def manager_key(supplier: str) -> str:
    return f"manager_{supplier}"


def supplier_table(items: list[ItemFacts], supplier: str) -> pd.DataFrame:
    rows = []
    choices = st.session_state.setdefault(manager_key(supplier), {item.sku: int(item.recommended_qty) for item in items})
    for item in sorted(items, key=lambda value: (URGENCY.get(value.urgency, URGENCY["unknown"])[1], value.days_of_cover, value.sku)):
        urgency_text, _ = URGENCY.get(item.urgency, URGENCY["unknown"])
        rows.append({"Срочность": urgency_text, "Товар": f"{item.sku} · {item.name}", "Excel": qty(item.naive_qty), "Рекомендуем": qty(item.recommended_qty), "К заказу": choices.get(item.sku)})
    return pd.DataFrame(rows)


def calculation_steps(item: ItemFacts) -> pd.DataFrame:
    correction = item.restored_demand - item.base_demand
    return pd.DataFrame([
        ("Очистка истории", number(item.base_demand, " шт/мес."), "Разовая продажа исключена" if item.outlier_qty else "Без исключений"),
        ("Восстановление stockout", number(correction, " шт/мес."), f"Периодов: {item.stockout_months}"),
        ("Прогноз на горизонт", qty(item.horizon_need), f"Сезонность {item.season_factor:.2f}".replace(".", ",") + f"; тренд {item.trend_pct:+.1f}%".replace(".", ",")),
        ("Остаток и поступления", f"− {qty(item.stock)} · − {qty(item.in_transit)}", "Вычитаются после прогноза"),
    ], columns=["Шаг", "Значение", "Пояснение"])


st.set_page_config(page_title="Заказы поставщикам", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""<style>
:root { --navy:#122247; --blue:#1769e0; --muted:#64748b; --line:#dce5f0; --surface:#f5f8fc; --amber:#9a5c00; }
.block-container { max-width:1540px; padding-top:2.25rem; padding-bottom:2.5rem; }
h1 { color:var(--navy); font-size:2.25rem!important; letter-spacing:-.04em; margin-bottom:.18rem!important; }
.caption { color:var(--muted); font-size:1rem; margin-bottom:1.45rem; }
.metric { border:1px solid var(--line); border-radius:12px; padding:1rem 1.1rem; min-height:104px; }
.metric-label { color:var(--muted); font-size:.82rem; }.metric-value { color:var(--navy); font-size:1.75rem; font-weight:700; margin-top:.35rem; }
.supplier { color:var(--navy); font-weight:700; font-size:1.05rem; margin:1.4rem 0 .5rem; }.note { color:var(--muted); font-size:.84rem; margin:.45rem 0; }
.detail { border:1px solid var(--line); border-radius:14px; padding:1.25rem; }.old { color:#8593a8; text-decoration:line-through; font-size:1rem; }.recommended { color:var(--blue); font-weight:750; font-size:2rem; margin:.15rem 0 .75rem; }
.bar { height:8px; border-radius:99px; background:#e9eff7; overflow:hidden; margin:.45rem 0 1rem; }.bar span { display:block; height:100%; background:var(--blue); }.fact { display:flex; justify-content:space-between; border-bottom:1px solid #edf1f6; padding:.52rem 0; color:var(--muted); font-size:.88rem; }.fact b { color:var(--navy); }.excluded { background:#fff7e8; border:1px solid #f3dfb1; border-radius:9px; color:#805000; padding:.7rem .8rem; font-size:.85rem; margin:.65rem 0 1rem; }
.stDataFrame, [data-testid="stDataEditor"] { border:1px solid var(--line); border-radius:10px; overflow:hidden; }
</style>""", unsafe_allow_html=True)

items = load_items()
if "approved" not in st.session_state:
    st.session_state.approved = {}
outlier_index = next((index for index, item in enumerate(items) if item.outlier_qty and item.outlier_qty > 0), 0)

st.title("Заказы поставщикам")
st.markdown('<div class="caption">Рекомендация системы. Решение и отправку делает менеджер.</div>', unsafe_allow_html=True)
recommended_items = [item for item in items if item.recommended_qty > 0]
metric_values = [("К заказу", f"{len(recommended_items)} позиций"), ("Срочных", f"{sum(item.urgency == 'high' for item in items)}"), ("Наивный расчёт выше рекомендации на", qty(sum(max(0, item.naive_qty - item.recommended_qty) for item in items)))]
for column, (label, value) in zip(st.columns(3), metric_values, strict=True):
    column.markdown(f'<div class="metric"><div class="metric-label">{label}</div><div class="metric-value">{value}</div></div>', unsafe_allow_html=True)

left, right = st.columns((60, 40), gap="large")
with left:
    for supplier in SUPPLIERS:
        supplier_items = [item for item in items if item.supplier == supplier]
        st.markdown(f'<div class="supplier">{SUPPLIERS[supplier]} <span style="color:#7f8da3;font-weight:500">· {supplier}</span></div>', unsafe_allow_html=True)
        locked = supplier in st.session_state.approved
        edited = st.data_editor(supplier_table(supplier_items, supplier), hide_index=True, disabled=["Срочность", "Товар", "Excel", "Рекомендуем"] if not locked else True, column_config={"К заказу": st.column_config.NumberColumn("К заказу", min_value=0, step=1, format="%d шт")}, key=f"table_{supplier}", use_container_width=True)
        proposed = st.session_state[manager_key(supplier)]
        changes = []
        for item, value in zip(sorted(supplier_items, key=lambda item: (URGENCY.get(item.urgency, URGENCY["unknown"])[1], item.days_of_cover, item.sku)), edited["К заказу"], strict=True):
            if pd.notna(value):
                proposed[item.sku] = int(value)
                if int(value) != int(item.recommended_qty): changes.append(f"{item.sku}: {qty(item.recommended_qty)} → {qty(int(value))}")
        reasons = [f"{item.sku}: Excel {qty(item.naive_qty)}; рекомендуем {qty(item.recommended_qty)}" for item in supplier_items if item.naive_qty != item.recommended_qty]
        if reasons: st.markdown('<div class="note">Причина отличия: ' + " · ".join(reasons) + "</div>", unsafe_allow_html=True)
        st.markdown('<div class="note">Ручные изменения: ' + ("; ".join(changes) if changes else "нет") + "</div>", unsafe_allow_html=True)
        if locked:
            st.caption(f"Утверждено: {st.session_state.approved[supplier]}. Отправка поставщику — вручную")
        elif st.button(f"Утвердить заказ: {SUPPLIERS[supplier]}", key=f"approve_{supplier}"):
            st.session_state.approved[supplier] = datetime.now().strftime("%d.%m.%Y %H:%M")
            st.rerun()

with right:
    with st.container(border=True):
        selected_sku = st.selectbox("Позиция", [item.sku for item in items], index=outlier_index, format_func=lambda sku: next(item.name for item in items if item.sku == sku))
        selected = next(item for item in items if item.sku == selected_sku)
        st.subheader(f"{selected.sku} · {selected.name}")
        st.markdown(f'<div class="old">Excel: {qty(selected.naive_qty)}</div><div class="recommended">Рекомендуем: {qty(selected.recommended_qty)}</div>', unsafe_allow_html=True)
        naive_width = min(100, selected.naive_qty / max(selected.naive_qty, selected.recommended_qty, 1) * 100)
        recommended_width = min(100, selected.recommended_qty / max(selected.naive_qty, selected.recommended_qty, 1) * 100)
        st.markdown(f'<div class="bar"><span style="width:{naive_width:.0f}%"></span></div><div class="bar"><span style="width:{recommended_width:.0f}%"></span></div>', unsafe_allow_html=True)
        if selected.outlier_qty:
            st.markdown(f'<div class="excluded">Исключённая разовая продажа: {qty(selected.outlier_qty)} · {selected.outlier_client}</div>', unsafe_allow_html=True)
        st.dataframe(calculation_steps(selected), hide_index=True, use_container_width=True)
        for label, value in [("Остаток", qty(selected.stock)), ("Дни покрытия", number(selected.days_of_cover, " дн")), ("Срок поставки", f"{selected.lead_time_days} дн")]:
            st.markdown(f'<div class="fact"><span>{label}</span><b>{value}</b></div>', unsafe_allow_html=True)
        st.number_input("В пути, шт", min_value=0, value=int(selected.in_transit), disabled=True, help="Интеграция с реальным расчётным потоком будет добавлена после T006.")
        st.markdown("### Обоснование")
        st.write("Рекомендация сформирована из fixture-данных для проверки интерфейса. Окончательное решение и отправку поставщику делает менеджер.")
