# Оперборд — версия для GitHub Pages

Статическая HTML-версия отчёта с интерактивными графиками и автоматическим обновлением данных через GitHub Actions.

## Архитектура

1. Workflow `.github/workflows/pages.yml` запускается каждый час.
2. `refresh_data.py` получает данные с веб-источников. Для ProFinance используется Chromium через Playwright.
3. Свежие данные сохраняются в `data/current.json` и публикуются в GitHub Pages.
4. `index.html` загружает `data/current.json` без кэширования. Кнопка «Обновить» перечитывает последнюю опубликованную версию.

## Основные файлы

- `index.html` — статический интерактивный дашборд;
- `refresh_data.py` — загрузка, проверка и слияние данных;
- `requirements.txt` — Python-зависимости;
- `.github/workflows/pages.yml` — расписание, Chromium, обновление и публикация;
- `data/current.json` — последний опубликованный набор данных;
- `data/snapshot.json` — исходный резервный снимок из PBIX.

Подробная инструкция находится в `GITHUB_PAGES_SETUP.md`.
