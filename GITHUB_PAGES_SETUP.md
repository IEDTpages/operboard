# Обновление Оперборда на GitHub Pages — версия v7.2

## Какие файлы заменить

Рекомендуется загрузить в корень репозитория всё содержимое архива с заменой существующих файлов.

Минимально необходимо заменить:

- `index.html`;
- `refresh_data.py`;
- `data/current.json`;
- `data/snapshot.json`;
- `.github/workflows/pages.yml`.

`requirements.txt` также следует заменить файлом из комплекта, чтобы версия Playwright оставалась согласованной с Chromium.

Workflow сам устанавливает R и CRAN-пакет `fedstatAPIr`; вручную добавлять R в
репозиторий или создавать для него secret не требуется.

## Добавление токена ATI.SU

1. Откройте `Settings → Secrets and variables → Actions`.
2. Нажмите `New repository secret`.
3. В поле имени укажите строго `ATI_API_TOKEN`.
4. Вставьте токен ATI.SU в поле значения и сохраните secret.

Не добавляйте токен в `index.html`, JSON-файлы, `refresh_data.py`, переменные GitHub Pages или URL. Workflow передаёт secret только процессу серверного обновления. Браузер посетителя никогда не обращается к API ATI.SU напрямую.

## После загрузки

1. Сделайте commit в ветку `main`.
2. Откройте `Settings → Actions → General`.
3. Проверьте `Workflow permissions → Read and write permissions`.
4. Откройте `Settings → Pages` и проверьте `Source → GitHub Actions`.
5. Добавьте `ATI_API_TOKEN` по инструкции выше.
6. Запустите `Actions → Refresh data and deploy dashboard → Run workflow`.

Первый запуск обязателен: он загрузит актуальные ряды ЕМИСС 57806 и 31314 и историю общего индекса ATI.SU FTL. Если ATI secret ещё не добавлен, остальные показатели всё равно обновятся.

Если ЕМИСС вернёт HTTP 403, workflow не завершится ошибкой: актуальные данные
остальных источников будут опубликованы, а существующие значения 57806 и 31314
останутся без изменений. В логе это отражается как `ERROR` конкретного
источника и итоговая успешная публикация `data/current.json`.

## Проверка новых данных

На шаге `Refresh data` должны появиться строки:

```text
[refresh] rubusd: OK; ...
[refresh] rubeur: OK; ...
[refresh] rubcny: OK; ...
[refresh] production_index: OK; ...
[refresh] road_freight: OK; ...
[refresh] exports: OK; ...
[refresh] imports: OK; ...
[refresh] ati_ftl: OK; ...
```

На шаге `Validate generated JSON` появятся последние даты и значения обязательных рядов:

```text
rubcny: 2026-... = ...
rubeur: 2026-... = ...
rubusd: 2026-... = ...
production_index/mom/total: 2026-... = ...
production_index/yoy/mining: 2026-... = ...
production_index/ytd/manufacturing: 2026-... = ...
exports: 2026-... = ...
imports: 2026-... = ...
```

После публикации на главной странице должны отображаться две группы карточек, а в навигации — отдельные разделы `Промпроизводство`, `Внешняя торговля`, `Автоперевозки` и `ATI.SU FTL`.

## Автоматическое обновление

Workflow выполняет проверку трижды в час:

```yaml
- cron: "13,33,53 * * * *"
```

Полный сбор запускается только при возрасте данных 50 минут и более. Это уменьшает последствия задержек scheduled workflows GitHub Actions и не запускает тяжёлую установку Chromium каждые 20 минут.
