# AGENTS.md — execution contract WarehouseAI

## Назначение

WarehouseAI детерминированно рассчитывает рекомендованный заказ поставщикам для менеджера отдела закупа.
Входы: история продаж, остатки, подтверждённые товары в пути, stockout, сезонность, устойчивый рост и разовые крупные покупки.
Система рекомендует. Человек проверяет, корректирует и утверждает.
Никогда не отправлять заказ поставщику автоматически.

## Перед каждой задачей

1. Прочитать этот файл и относящиеся к задаче source-of-truth документы.
2. Выполнить `git status -sb`, проверить ветку, HEAD и чужие изменения.
3. Зафиксировать TASK, OWNED PATHS, DO NOT TOUCH, ACCEPTANCE и REPORT FORMAT.
4. Не менять файлы вне ownership и не начинать следующую задачу автоматически.
5. Не выдавать UNKNOWN, NOT_RUN или NOT_VERIFIED за PASS.

## P0: пять обязательных результатов

1. Базовая потребность в пополнении.
2. Раздельный учёт сезонности и устойчивого роста.
3. Компенсация упущенного спроса при stockout.
4. Исключение разовой аномалии, включая покупку одного клиента.
5. Рекомендации по поставщикам с фактическим объяснением каждой строки.

P0 не Green, пока любой пункт NOT_RUN или NOT_VERIFIED.
Нельзя вырезать must-have ради сроков.

## Замороженный demo-набор

- 24 месяца, 5 SKU, 1 склад, 2–3 поставщика, обезличенные клиенты.
- `A-100` — STABLE.
- `A-200` — SEASONAL.
- `A-300` — GROWTH.
- `A-400` — STOCKOUT.
- `A-500` — OUTLIER.
- A-500: регулярный спрос около 40–55 единиц/месяц и одна покупка `CUST-017` около 500 единиц.
- Главный WOW: сравнение NAIVE ORDER и CLEAN-DEMAND ORDER для A-500.
- Нельзя hardcode recommendation по SKU ID.

## Архитектура и зависимости

Python 3.12. Числовое ядро детерминировано.
Canonical core command: `python -m procure.run`.
Core обязан работать без Streamlit, live AI и базы данных.
Streamlit — только presentation layer; алгоритмы не размещать в `app.py`.

Замороженный минимальный stack:

- pandas;
- numpy;
- openpyxl;
- openai;
- pytest;
- streamlit;
- по возможности stdlib: csv, json, hashlib, statistics, pathlib, datetime, dataclasses.

Не добавлять package без доказанного blocker.
Для P0 запрещены FastAPI, Django, Flask, PostgreSQL, Redis, Docker, scikit-learn, Prophet, ARIMA, TensorFlow, PyTorch, RAG, vector DB, background jobs, auth и интеграция 1С.

## Неизменяемый порядок расчёта

1. raw data;
2. schema validation;
3. source hash;
4. aggregate demand;
5. detect/exclude one-off anomalies;
6. identify stockout periods;
7. estimate clean/base demand;
8. restore lost demand;
9. derive seasonality;
10. derive sustained growth;
11. forecast replenishment horizon;
12. subtract current stock;
13. subtract confirmed in-transit;
14. recommended quantity;
15. urgency;
16. supplier grouping;
17. explanation;
18. audit;
19. human review.

Не менять порядок молча.

## Числовой source of truth

Все числа вычисляет Python-код.
AI не вычисляет regular demand, outlier, stockout correction, trend, seasonality, `recommended_qty` или urgency.
Никаких скрытых AI adjustments.
Каждая единица измерения должна быть явной.

Planning horizon учитывает lead time и замороженную reorder policy:

```text
recommended_qty = max(
    0,
    expected_demand_over_horizon - current_stock - confirmed_in_transit
)
```

## Безопасность расчёта

Outlier detection: deterministic, explainable, unit-tested.
Не использовать недостижимый на frozen dataset threshold и не применять автоматически `3σ` к короткой истории.
Обязательно учитывать концентрацию у одного клиента.
A-500 доказывает, что разовая покупка 500 единиц не становится regular demand.

Stockout sales не являются истинным низким demand.
Stockout-периоды не должны занижать baseline.
A-400 доказывает: corrected demand > misleading observed demand.

Trend должен быть простым, устойчивым, детерминированным и объяснимым.
Seasonality — простой месячный factor; при недостаточной истории `season_factor = 1.0`.
Сложный ML forecast запрещён.

## Change proof против hardcode

Для A-500 изменить только `in_transit`: 0 → 50.
Если исходная recommendation >= 50, `recommended_qty` должна уменьшиться ровно на 50.
Explanation facts меняются `In transit: 0` → `In transit: 50`.
Другие SKU не должны самопроизвольно менять результат.

## AI contract

AI подключается только после Green всех must-have.
Сначала реализовать template explanation.
`AI_MODE=off` — обязательный рабочий режим.
Numeric result при `AI_MODE=off` и `AI_MODE=on` полностью идентичен.
AI только формулирует explanation из рассчитанных facts и не меняет recommendation.

Разрешённые placeholders:

- `{{regular_demand}}`;
- `{{season_factor}}`;
- `{{trend_factor}}`;
- `{{stockout_correction}}`;
- `{{excluded_outlier}}`;
- `{{stock}}`;
- `{{in_transit}}`;
- `{{lead_time}}`;
- `{{recommended_qty}}`.

Production prompt не содержит реальные числа.
Validation model output: любая цифра — FAIL; неизвестный placeholder — FAIL; длина > 300 chars — FAIL.
При FAIL: один retry, затем deterministic template fallback.
Timeout 15 секунд: template fallback.
Python подставляет actual values только после validation модели или шаблона.

## UI contract

Один экран Streamlit: `layout="wide"`, без sidebar, tabs и charts.
Слева 60% — supplier tables; справа 40% — detail выбранной позиции.
По умолчанию выбрана позиция с `excluded_outlier > 0`.

Header: `Заказы поставщикам`.
Subtitle: `Рекомендация системы. Решение и отправку делает менеджер.`
Metrics: `К заказу`, `Срочных`, `Excel заказал бы лишнего`.

Supplier table содержит ровно пять колонок:

1. Срочность;
2. Товар;
3. Excel;
4. Рекомендуем;
5. К заказу.

Редактируется только `К заказу`.

## Граница человека и аудит

Менеджер может проверить, изменить предложенное количество и approve/reject.
Система не отправляет заказ, не создаёт обязательство перед поставщиком, не auto-approve и не меняет складские данные.
Approval невозможен без непустого audit evidence.

Каждая recommendation хранит trace: input hash, sku, base demand, excluded anomaly, stockout correction, trend, seasonality, lead time, horizon, stock, in_transit, final arithmetic и `recommended_qty`.

## Scenario gates

Обязательны `SCN-HAPPY`, `SCN-OUTLIER`, `SCN-STOCKOUT`, `SCN-SEASON`, `SCN-GROWTH`, `SCN-CHANGE`, `SCN-FALLBACK`, `SCN-DEMO`.
Каждый gate содержит Given, When, Then и Evidence.
UNKNOWN != PASS. NOT_RUN != PASS. NOT_VERIFIED != PASS.

## Failure policy

Первый реальный FAIL: сохранить evidence → установить root cause → применить минимальный обоснованный fix → повторить релевантный gate.
Второй FAIL с той же root cause: STOP. Третья спекулятивная правка запрещена.
Coordination BLOCKED не равен implementation FAIL.

## Ownership и Git

Каждая задача задаёт TASK, OWNED PATHS, DO NOT TOUCH, ACCEPTANCE и REPORT FORMAT.
Не изменять ничего вне ownership без явного согласования.
Terminal — execution truth. Commit не означает Push.

Запрещены `git add .`, `git add -A`, force push, destructive reset и history rewrite.
Только явный staging конкретных путей.
Перед commit проверить `git status -sb`, `git diff` и `git diff --cached`.
Push VERIFIED только при точном равенстве local SHA и remote SHA.

## Source of truth и delivery freeze

- `README.md` — объяснение проекта человеку; только подтверждённые репозиторием факты.
- `AGENTS.md` — execution contract.
- `docs/STATUS.md` — текущая operational truth.
- `git log` — delivery history.
- Не создавать `.codex/` или PROMPT_REGISTRY.

Freeze: STOP_WRITES → regression → scenario gates → demo → explicit staging → commit → committed-tree regression → push → local SHA → remote SHA → exact equality → clean worktree.

## Приоритет при нехватке времени

Сокращать: live AI → audit polish → detail card → Excel export → trend polish.
Не сокращать: outlier, stockout, supplier grouping, factual explanation, README и demo proof.

README обязан отражать project name, problem/user, implemented features, main scenario, technologies, architecture, install/run, verification example, data/external services, limitations и deployed link при наличии.
Не описывать незавершённое как готовое.

## Порядок задач

T002 generator + naive baseline → T003 outliers → T004 stockout → T005 trend + seasonality → T006 order + urgency + supplier grouping → T007 template explanation + export.
Только после must-have Green: T008 live AI → T009 audit enhancement → T010 Streamlit → T011 regression/scenarios → T012 video/delivery.

## Обязательный отчёт execution writer

Сообщать: status, owned_paths, files_created, files_modified, tests_run, test_result, unexpected_files, not_verified, blocker и next.
Не заявлять PASS без наблюдаемого evidence.
