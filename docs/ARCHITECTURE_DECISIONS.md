# Архитектурные решения и отклонения от ТЗ

Исходное ТЗ: `deliverables/OLX_iPhone_Scout_Technical_Specification.md`
(копия требований; папка deliverables исключена из git как артефакт прежней задачи).
Формат записи: **что изменено — почему — чем новое решение надежнее**.

## 1. Проект живет в корне рабочей папки, без HyperAgent

ТЗ описывало разработку через платформу HyperAgent (этапы-Thread'ы, STAGE_REPORT,
HYPERAGENT_CAPABILITIES). Приложение разработано локально автономным агентом в
git-репозитории в корне рабочей папки. Legacy-папки `build/`, `qa/`, `outputs/`,
`work/`, `deliverables/` — артефакты прежней задачи; они сохранены на диске, но
исключены из репозитория (.gitignore). Файлы HYPERAGENT_CAPABILITIES.md и
STAGE_REPORT.md не создавались: платформа не использовалась, отчет один — финальный.
Надежнее: один источник истины (git), никакой зависимости от неподтвержденных
возможностей платформы.

## 2. Версии зависимостей: диапазоны + uv.lock вместо «жестких» пинов

ТЗ пинует точные версии «на 24.07.2026». В `pyproject.toml` заданы безопасные
диапазоны, а точные версии зафиксированы в `uv.lock`. Фактически резолв совпал с
ТЗ почти полностью (Django 5.2.16, DRF 3.17.1, psycopg 3.3.4, Playwright 1.61.0,
django-axes 8.3.1, django-csp 4.0, whitenoise 6.12.0, gunicorn 26.0.0,
ruff 0.15.22, openai 2.48.0 vs 2.46.0 в ТЗ). Отличия: pytest 8.4.2 (ТЗ: 9.1.1),
mypy 1.20.2 (ТЗ: 2.3.0), django-stubs 5.2.9 (ТЗ: 6.0.7), pytest-cov 7.1.0 —
выбраны совместимые стабильные ветки, доступные резолверу. Надежнее: lockfile
гарантирует воспроизводимость, а диапазоны позволяют пересобрать окружение, если
конкретный патч-релиз исчезнет из PyPI.

## 3. BeautifulSoup внутри чистого парсера

Парсер (`apps/monitoring/collectors/olx_parser.py`) — чистые функции над HTML
(`page.content()` из Playwright или файл-фикстура) через BeautifulSoup. ТЗ явно
допускает это («Requests + BeautifulSoup … можно использовать только внутри
чистого parser после page.content()»). Надежнее: один и тот же парсер тестируется
на фикстурах и работает в production.

## 4. HTML-страницы работают через серверные Django-формы, JSON API — параллельно

Кнопки UI отправляют обычные POST-формы в HTML-вьюхи (redirect + flash), а
`/api/v1/` реализует контракт §12 (envelope, allowlists, конфликтные статусы).
HTMX используется точечно (проверка URL поиска). Надежнее: меньше JS-состояния,
UI работает даже без JS, API остается пригодным для автоматизации и тестов.

## 5. AppState расширен полями safety-блока

К таблице §11.3 добавлены `safety_block_until`, `safety_block_reason`,
`safety_ack_required`. §6.13 ссылается на `safety_block_until`, но таблица его не
содержала — противоречие ТЗ разрешено в пользу §6.13. Надежнее: пауза после
CAPTCHA/403/429 переживает рестарт и требует явного подтверждения риска (§12.11).

## 6. Reanalyze: web ставит PENDING-строку, worker выполняет

`POST /listings/{id}/reanalyze/` создает строку AiAnalysis со статусом PENDING и
возвращает 202; воркер подхватывает очередь (`process_pending_analyses`). Это
прямое исполнение требования «web request не делает долгий paid call синхронно»
без Redis/Celery. Cache hit возвращается синхронно без вызова провайдера.

## 7. E2E-тесты — full-stack через Django test client, не браузер

Матрица E-01…E-22 покрыта тестами через test client (полный стек: URL →
middleware → view → сервис → PostgreSQL → шаблон). Живой браузерный Playwright-ран
против self-hosted Django не используется. Почему: детерминизм и отсутствие
flaky-таймингов в CI; адаптивность обеспечена Bootstrap-сеткой и проверена
вручную. Компромисс честно назван в «Известных ограничениях» README.

## 8. Дополнительные reason-codes фильтров

К allowlist §6.7.2 добавлены `KEYWORD_EXCLUDED`, `KEYWORD_MISSING`,
`SELLER_TYPE_MISMATCH`, `DELIVERY_MISSING`, `DELIVERY_UNKNOWN`,
`PRICE_BELOW_MINIMUM`, `STORAGE_MISMATCH` (see `apps/pricing/constants.py`).
ТЗ описывает сами фильтры (9.7), но не дает им кодов. Надежнее: каждая причина
отклонения объяснима в UI, а не сливается в «прочее».

## 9. PRICE_DROP-уведомление и из обычного скана

§6.3 описывает price-drop при refresh; дополнительно, если обычный скан выдачи
видит снижение цены уже известного кандидата, создается PRICE_DROP-событие
(fingerprint включает новую цену — дублей нет). Надежнее: владелец узнает о
снижении на первой странице выдачи без ожидания 6-часового refresh.

## 10. PRICE_BORDERLINE: формальное определение

ТЗ требует `MANUAL_REVIEW + PRICE_BORDERLINE` «между порогами», не определяя
границу. Реализовано: цена ≤ профильного потолка и каждый экономический порог
(прибыль, ROI) промахнут не более чем на 10% (`BORDERLINE_FACTOR = 0.90`).
Константа лежит в `apps/pricing/services.py` и покрыта boundary-тестами.

## 11. Rate limits через окна AuditEvent

Отдельного limiter-хранилища нет: количество одинаковых AuditEvent за окно
считается перед действием (`apps/core/services.enforce_rate_limit`). Это ровно
рекомендация §13.9 (PostgreSQL, фиксированные action codes, один пользователь).

## 12. Fixture pipeline: `--no-send` всегда истинен

`run_fixture_pipeline` создает outbox-строки, но никогда не отправляет их:
отправкой занимается только outbox-цикл воркера, а Telegram в local/test не
сконфигурирован. Флаг `--no-send` оставлен для совместимости с ТЗ и всегда
включен. Плюс защиты: APP_ENV local|test, MONITOR_ENABLED=false, отказ от
production-похожей БД.

## 13. Покрытие: исключения задокументированы

Из coverage исключены `collectors/playwright_source.py`, `collectors/base.py`
(Protocol) и тонкие CLI-обертки `run_monitor`/`run_search_once`/`refresh_listing`:
их исполнение требует живого OLX/Chromium, что запрещено в автоматических тестах.
Итог: 81% общий (порог 80%), pricing 94–95%, парсер 91%, outbox/статусы >90%.
`apps/monitoring/services.py` (dedup/оркестрация) — 84%: ниже цели ТЗ в 90% для
«dedup», непокрытые ветки — обработка редких ошибок коллектора.

## 14. `ci.sh` использует `mypy apps` (без config)

Обязательные проверки пользователя фиксируют `mypy apps`; настройки Django
(`config/settings/*`) не проходят строгую типизацию из-за динамического
django-environ. Строгая типизация действует для всего кода приложения (108 файлов,
0 ошибок).

## 15. Тестовый прогон использует MD5-хешер, боевой — Argon2

`config/settings/test.py` подменяет PASSWORD_HASHERS ради скорости; тест
`tests/security/test_headers.py` отдельно проверяет, что боевая конфигурация
начинается с Argon2 и что hash в БД имеет префикс `argon2`.

## 16. GitHub Actions: официальные actions по мажорным тегам

ТЗ просит пиновать по commit SHA «по возможности». Использованы официальные
`actions/checkout@v4`, `actions/setup-python@v5`, `gitleaks/gitleaks-action@v2`
по мажорным тегам: репозиторий приватный, а обновление SHA вручную новичком —
источник ошибок. Dependabot следит за actions ежемесячно.

## 17. Ограничение «удаление данных»

Hard delete Listing/Deal отсутствует и в UI, и в API (§12.12). Единственные
разрушающие операции — retention cleanup (`cleanup_old_data --confirm`, не
трогает бизнес-данные) и `run_fixture_pipeline --cleanup-fixture-namespace`
(только fixture-namespace, объявления со сделками не удаляет).

## 18. Локальный web-процесс — runserver, production — gunicorn

Compose запускает web как `manage.py runserver` (DEBUG, автостатика), образ по
умолчанию (CMD) и Render используют gunicorn + WhiteNoise manifest. Надежнее:
локальная простота без потери production-контракта (P-06/P-07 проверяются образом).
