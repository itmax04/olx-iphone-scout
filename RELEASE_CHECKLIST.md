# Чеклист перед релизом

Проходится сверху вниз перед каждым релизом (новая версия локально или деплой
на Render). Отметьте каждый пункт: **PASS** (проверено, работает), **FAIL**
(не работает — релиз останавливается до исправления) или **MANUAL** (пункт
выполняется вручную, отметьте факт выполнения).

Все команды выполняются в папке проекта при запущенном Docker Desktop.

| # | Проверка | Команда / действие | Ожидаемый результат | PASS/FAIL/MANUAL |
|---|---|---|---|---|
| 1 | Чистота репозитория | `git status --short` | Нет незакоммиченных файлов; в списке нет `.env` и `backups/` | ☐ |
| 2 | Сборка образа | `docker compose build` | Сборка завершается без ошибок | ☐ |
| 3 | Миграции применяются | `docker compose up -d` затем `docker compose logs migrate` | `migrate` завершился с кодом 0, в логах `Applying ... OK` и `bootstrap_admin: administrator already exists` | ☐ |
| 4 | Тесты и линтеры | `docker compose run --rm web ./scripts/ci.sh` | Все шаги зеленые, код возврата 0 | ☐ |
| 5 | Secret scan | `git log --all -p \| grep -aiE "OPENAI_API_KEY=sk\|TELEGRAM_BOT_TOKEN=[0-9]" \| head` (плюс ручной просмотр диффа релиза) | Пусто: ни одного реального ключа/токена в истории и в диффе | ☐ |
| 6 | Фикстурная приемка | `docker compose run --rm web python manage.py run_fixture_pipeline` | Строка `FIXTURE_PIPELINE=PASS` | ☐ |
| 7 | Приемка: снижение цены | `docker compose run --rm web python manage.py run_fixture_pipeline --price-drop` | Строка `FIXTURE_PIPELINE=PASS` | ☐ |
| 8 | Health-эндпоинты | `curl -s http://localhost:8000/api/v1/health/live/` и `.../health/ready/` | Оба отвечают HTTP 200 | ☐ |
| 9 | Свежий бэкап | `./scripts/backup_local.sh` | Новые `.dump` + `.sha256` + manifest в `backups/` | ☐ |
| 10 | Пароль администратора сменен с начального | Вход в интерфейс личным паролем (не значением `ADMIN_PASSWORD` из `.env`) | Вход успешен; стартовый пароль не действует | MANUAL ☐ |
| 11 | Telegram работает | /settings/ → «Отправить тест Telegram» | Сообщение пришло в чат | ☐ |
| 12 | Флаги первого деплоя | Проверить переменные окружения релиза | `MONITOR_ENABLED=false` и `AI_ENABLED=false` для первого запуска на новом окружении | MANUAL ☐ |
| 13 | Render blueprint validation (только при деплое на Render) | В панели Render: New → Blueprint → выбрать репозиторий; либо dry-run синхронизации Blueprint | Render распознает `render.yaml` без ошибок валидации: web + worker + PostgreSQL 17, frankfurt, секреты `sync: false` | MANUAL ☐ |
| 14 | Владелец подтверждает платный деплой | Осознанное ручное нажатие Apply/Deploy в Render владельцем | Деплой запущен владельцем, не автоматикой | MANUAL ☐ |

Правило: любой **FAIL** в пунктах 1–9 останавливает релиз. Пункты 13–14
относятся только к публикации на Render (docs/DEPLOY_RENDER.md).

После релиза: пройдите smoke-тест из docs/DEPLOY_RENDER.md (шаг 6) или,
для локального обновления, откройте /system/ и /runs/ и убедитесь, что воркер
`HEALTHY` и запуски идут со статусом `SUCCESS`.
