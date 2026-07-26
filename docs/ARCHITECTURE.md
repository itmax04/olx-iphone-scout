# Архитектура (кратко)

Полное ТЗ: [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md).
Отклонения: [ARCHITECTURE_DECISIONS.md](ARCHITECTURE_DECISIONS.md).

## Компоненты

```text
Пользователь ──HTTPS/session──▶ Django Web (Templates + HTMX + DRF /api/v1/)
                                   │
                                   ▼
                              PostgreSQL 17
                                   ▲
Django Worker (run_monitor) ───────┘
  ├─ pg_try_advisory_lock (ровно один активный worker)
  ├─ due-scheduler: SearchProfile.next_scan_at + jitter
  ├─ Playwright Chromium ──▶ публичные страницы olx.ua (concurrency 1)
  ├─ детерминированный prefilter + формула profit-v1 (Decimal)
  ├─ AI-очередь: OpenAI Responses API (fast → deep), жесткие USD-лимиты
  └─ outbox-цикл ──▶ Telegram Bot API (sendMessage, retry ladder)
```

## Приложения Django

| App | Ответственность |
|---|---|
| `apps/core` | AppState(singleton), AuditEvent, auth backend, health, middleware, redaction, настройки/система |
| `apps/dashboard` | Агрегаты обзора |
| `apps/monitoring` | SearchProfile, Listing, Discovery, Snapshot, ScanRun; collectors; scheduler; worker; status machine |
| `apps/pricing` | Реестр моделей iPhone 11–15, извлечение фактов, MarketPriceRule, DefectReserveRule, Evaluation-формула, выбор current evaluation (§6.7.3) |
| `apps/analysis` | AiAnalysis-кеш (revision/attempt), Pydantic-схема, prompts, routing, бюджеты |
| `apps/alerts` | NotificationOutbox, форматирование, Telegram-клиент, retry |
| `apps/deals` | Deal (OneToOne к Listing), immutable purchase_snapshot, фактическая прибыль |

Направление зависимостей — по §7.2 ТЗ: все apps → core; monitoring → pricing/analysis/alerts;
core не импортирует feature-apps.

## Ключевые инварианты

- Дедупликация: `Listing.olx_id` UNIQUE; повторный скан не создает дублей и уведомлений.
- История: `ListingSnapshot` только при значимом изменении (unique fingerprint).
- Оценка: append-only `Evaluation` c `input_hash`; AI не влияет на цифры.
- Outbox: запись в БД до внешней отправки; fingerprint UNIQUE; 5 попыток, retry_after.
- Runtime-переключатели: env (`MONITOR_ENABLED`, `AI_ENABLED`) доминируют над AppState.
- CAPTCHA/403/429: safety-пауза 30 минут + подтверждение риска; обход запрещен.
