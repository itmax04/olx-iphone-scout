# Правила для агентов и разработчиков

Проект: OLX iPhone Scout — приватный однопользовательский Django-монолит
(web + worker, PostgreSQL 17, Playwright, HTMX/Bootstrap).

## Перед изменениями

1. `git status --short` — не перезаписывай чужие незакоммиченные изменения.
2. Прочитай `README.md`, `docs/ARCHITECTURE_DECISIONS.md` и код затрагиваемого модуля.
3. Требования лежат в `deliverables/OLX_iPhone_Scout_Technical_Specification.md`
   (вне git); отклонения фиксируются в `docs/ARCHITECTURE_DECISIONS.md`.

## Жесткие правила

- Никаких TODO/FIXME/pass/NotImplementedError в production-коде.
- Никаких реальных секретов в git, логах и промптах; `.env` не коммитится.
- CSRF, permissions и тесты не отключаются ради зеленого результата.
- Скрытый мобильный API OLX, обход CAPTCHA/403/429 — запрещены навсегда.
- Автоматические тесты не ходят в OLX, OpenAI и Telegram (fixtures/mocks).
- Деньги — только Decimal; AI не участвует в расчете прибыли.
- Направление зависимостей модулей — §7.2 ТЗ; core не импортирует feature-apps.
- Миграции: примененные не редактируются; destructive — только с backup и
  отдельным одобрением. `git reset --hard` и force push запрещены.

## Проверки перед коммитом

```bash
docker compose run --rm web ./scripts/ci.sh
./scripts/secret_scan.sh
git diff --check
```

Локально без Docker: `.venv/bin/python -m pytest`, `ruff format --check .`,
`ruff check .`, `mypy apps` (нужен PostgreSQL и `DATABASE_URL`).
