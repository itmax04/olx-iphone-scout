# Частые ошибки и их решения

Первый шаг при любой проблеме — посмотреть логи:

```bash
docker compose logs --tail=200 web worker migrate
```

Где выполнять: в папке проекта.
Что делает: показывает последние 200 строк логов трех сервисов.
Ожидаемый результат: текст логов; ищите строки с `ERROR` или `Traceback`.

## Таблица частых ошибок

| Симптом / текст ошибки | Причина | Решение |
|---|---|---|
| `Bind for 0.0.0.0:8000 failed: port is already allocated` (при `docker compose up`) | Порт 8000 занят другим приложением | Найдите, кто занял: `lsof -i :8000`. Закройте ту программу, либо в `compose.yaml` замените `"8000:8000"` на `"8001:8000"` и открывайте http://localhost:8001 (тогда же поправьте `DJANGO_CSRF_TRUSTED_ORIGINS` и `APP_BASE_URL` в `.env`) |
| `the database system is starting up` | PostgreSQL еще не успел стартовать | Подождите 10–20 секунд и повторите команду. Compose обычно ждет сам (healthcheck); ошибка чаще бывает при ручных `docker compose run` сразу после старта |
| `password authentication failed for user "iphone_scout"` | Пароль в `DATABASE_URL` не совпадает с паролем, с которым база была создана впервые (`POSTGRES_PASSWORD` действует только при первом создании тома) | Верните прежний пароль в обе переменные `.env` (`DATABASE_URL` и `POSTGRES_PASSWORD`) и `docker compose up -d --force-recreate`. Менять пароль БД надо внутри PostgreSQL (`ALTER USER`), а не только в `.env` |
| `DisallowedHost at /` / `Invalid HTTP_HOST header` | Открываете сайт по адресу, которого нет в `DJANGO_ALLOWED_HOSTS` | Добавьте адрес (без http://) в `DJANGO_ALLOWED_HOSTS` через запятую в `.env`, затем `docker compose up -d --force-recreate web` |
| `CSRF verification failed. Request aborted.` (403 при отправке формы) | Адрес, с которого отправлена форма, не указан в `DJANGO_CSRF_TRUSTED_ORIGINS` (или страница «протухла» за ночь) | Сначала просто обновите страницу и повторите. Если не помогло — добавьте точный адрес с протоколом (например, `http://localhost:8001`) в `DJANGO_CSRF_TRUSTED_ORIGINS`, перезапустите `web` |
| `Executable doesn't exist at .../chromium...` / `playwright ... executable doesn't exist` | Образ собран без браузера Playwright (устаревший/битый кэш сборки) | Пересоберите образ без кэша: `docker compose build --no-cache` затем `docker compose up -d`. Браузер ставится в образ на этапе сборки; ничего внутри работающего контейнера доустанавливать не нужно |
| OLX возвращает 429 / CAPTCHA, запуски в статусе `BLOCKED`, мониторинг сам встал на паузу | OLX ограничивает частоту запросов; сработала штатная защита приложения (safety-блок) | Это нормальное поведение. Подождите минимум 30 минут, затем /settings/ → «Возобновить» с галочкой подтверждения риска. Увеличьте интервалы сканирования, сократите число активных поисков. **Не пытайтесь обходить**: прокси, смена IP, решение CAPTCHA — прямой путь к блокировке на OLX |
| OpenAI 401 (`invalid_api_key`) | Неверный/отозванный `OPENAI_API_KEY` | Создайте новый project-ключ на platform.openai.com, обновите `.env`, `docker compose up -d --force-recreate web worker`. Мониторинг при этом работает — страдает только AI-анализ |
| OpenAI 429 (`rate limit` / `insufficient_quota`) | Кончился баланс/квота OpenAI или слишком частые запросы | Проверьте Billing на platform.openai.com. Если это лимит приложения («Дневной/Месячный лимит расходов AI исчерпан») — это штатный предохранитель, он сбросится сам в начале суток/месяца |
| Telegram 401 (`Unauthorized`) при тесте | Неверный `TELEGRAM_BOT_TOKEN` | Проверьте токен у @BotFather (или сделайте `/revoke` и получите новый), обновите `.env`, пересоздайте контейнеры |
| Telegram 400 `chat not found` | Неверный `TELEGRAM_CHAT_ID`, или вы не отправили боту `/start` | Отправьте боту `/start`, затем `docker compose run --rm web python manage.py discover_telegram_chat_id` и впишите правильный ID |
| На /system/ статус воркера `NEVER_RUN` («воркер не запускался») | Контейнер `worker` не стартовал или падает при старте | `docker compose ps` — если `worker` не `running`, смотрите `docker compose logs worker`. Частые причины: ошибка в `.env`, недоступная база. После исправления: `docker compose up -d --force-recreate worker` |
| На /system/ статус воркера `STALE` или `UNAVAILABLE` | Воркер завис или остановился после старта | `docker compose restart worker`, затем логи. Если повторяется — ищите в логах последнюю ошибку перед остановкой heartbeat |
| Вход заблокирован, HTTP 429 на странице логина | Защита от перебора: 5 неудачных попыток | Подождите 15 минут. Пароль забыт — см. ниже «Сброс пароля» |
| `bootstrap_admin: ... required` в логах `migrate` | Не заполнены `ADMIN_USERNAME`/`ADMIN_EMAIL`/`ADMIN_PASSWORD` при первом запуске | Заполните `.env` и выполните `docker compose up -d` еще раз |
| `FIXTURE_PIPELINE=FAIL` или отказ команды | Запуск с `MONITOR_ENABLED=true` или не в локальном окружении | Поставьте `MONITOR_ENABLED=false`, повторите. Если статус запуска не SUCCESS — смотрите строки вывода выше итога |

## Сброс пароля администратора

Пароль в `.env` на существующий аккаунт не влияет. Если пароль утерян:

```bash
docker compose run --rm web python manage.py changepassword owner
```

Что делает: интерактивно задает новый пароль пользователю `owner`.
Ожидаемый результат: `Password changed successfully for user 'owner'`.

## Если ничего не помогло

1. Полный перезапуск без потери данных:

```bash
docker compose down
```

```bash
docker compose up --build -d
```

2. Проверьте health:

```bash
curl -s http://localhost:8000/api/v1/health/ready/
```

3. Сохраните логи (`docker compose logs > логи.txt`) — с ними проще искать
   причину. Помните: `docker compose down -v` не является способом «починить»
   что-либо — он удаляет базу данных.
