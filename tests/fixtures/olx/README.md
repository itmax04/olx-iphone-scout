# OLX HTML fixtures

Санитизированная разметка страниц OLX для parser/pipeline-тестов и локальной
приемки (`run_fixture_pipeline`). CI никогда не обращается к живому OLX.

Правила:

- никаких реальных телефонов, имен, адресов, токенов и переписки;
- OLX ID в диапазоне `8000000xx` — синтетические;
- image URL указывают на несуществующие sanitized-пути CDN;
- структура повторяет ключевые `data-testid`/`data-cy` атрибуты OLX,
  используемые в `apps/monitoring/collectors/selectors.py`.

| Файл | Сценарий |
|---|---|
| `search_normal.html` | обычная выдача: телефон, Pro-модель, чехол (аксессуар), запчасти |
| `search_promoted.html` | выдача с промо-карточкой |
| `search_missing_price.html` | карточка без цены («Договірна») |
| `search_price_drop.html` | та же карточка `800000001` с ценой ниже |
| `detail_normal.html` | детальная страница живого объявления |
| `detail_price_drop.html` | та же детальная страница со сниженной ценой |
| `detail_inactive.html` | удаленное/неактивное объявление |
| `captcha.html` | страница с CAPTCHA-маркером |
