# Обновление Оперборда на GitHub Pages — версия v5

## Какие файлы заменить

Рекомендуется загрузить в корень репозитория всё содержимое архива с заменой существующих файлов.

Минимально необходимо заменить:

- `index.html`;
- `refresh_data.py`;
- `data/current.json`;
- `data/snapshot.json`;
- `.github/workflows/pages.yml`.

`requirements.txt` также следует заменить файлом из комплекта, чтобы версия Playwright оставалась согласованной с Chromium.

## После загрузки

1. Сделайте commit в ветку `main`.
2. Откройте `Settings → Actions → General`.
3. Проверьте `Workflow permissions → Read and write permissions`.
4. Откройте `Settings → Pages` и проверьте `Source → GitHub Actions`.
5. Запустите `Actions → Refresh data and deploy dashboard → Run workflow`.

Первый запуск обязателен: исходный резервный JSON содержит структуру новых EUR и CNY рядов, а их исторические значения будут загружены с сайта ЦБ РФ во время workflow.

## Проверка валютных данных

На шаге `Refresh data` должны появиться строки:

```text
[refresh] rubusd: OK; ...
[refresh] rubeur: OK; ...
[refresh] rubcny: OK; ...
```

На шаге `Validate generated JSON` появятся последние даты и значения трёх рядов:

```text
rubcny: 2026-... = ...
rubeur: 2026-... = ...
rubusd: 2026-... = ...
```

После публикации на главной странице должны отображаться три отдельные карточки, а в навигации — раздел `Курсы валют`.

## Автоматическое обновление

Workflow выполняет проверку трижды в час:

```yaml
- cron: "13,33,53 * * * *"
```

Полный сбор запускается только при возрасте данных 50 минут и более. Это уменьшает последствия задержек scheduled workflows GitHub Actions и не запускает тяжёлую установку Chromium каждые 20 минут.
