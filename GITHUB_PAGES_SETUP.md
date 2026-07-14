# Установка обновлённой версии в существующий репозиторий GitHub

## 1. Замените файлы

Загрузите содержимое этого комплекта в корень репозитория с заменой существующих файлов. Особенно важно заменить:

```text
.github/workflows/pages.yml
refresh_data.py
requirements.txt
index.html
```

Папки `data` и `.github` должны сохраниться именно с такими именами.

## 2. Проверьте разрешения Actions

Откройте:

```text
Settings → Actions → General → Workflow permissions
```

Выберите `Read and write permissions` и сохраните настройку.

## 3. Проверьте источник GitHub Pages

Откройте:

```text
Settings → Pages → Build and deployment
```

Установите `Source: GitHub Actions`.

## 4. Запустите обновление вручную

Откройте:

```text
Actions → Refresh data and deploy dashboard → Run workflow
```

В успешном запуске должны пройти шаги:

```text
Install Chromium and operating-system dependencies
Verify Chromium launch
Refresh dashboard data
Validate generated JSON
Save refreshed data in repository
Deploy to GitHub Pages
```

В логе `Validate generated JSON` отдельно выводятся статусы `brent`, `urals`, `ttf`, `ara` и `lme`.

## 5. Проверьте опубликованные данные

Откройте в репозитории `data/current.json`. После успешного запуска должны присутствовать:

```json
"source_mode": "web_refresh"
```

и объект:

```json
"refresh_summary": {
  "successes": 11,
  "total": 11
}
```

Число успешных источников может быть меньше 11 при временной недоступности отдельных сайтов. Необновившиеся ряды сохраняют последние корректные значения, а причина записывается в `status`.

## Особенность кнопки «Обновить»

GitHub Pages не запускает Python по нажатию кнопки. Кнопка в дашборде перечитывает уже опубликованный `data/current.json`. Для немедленного сбора данных запустите workflow вручную во вкладке Actions.

## Расписание

По умолчанию workflow запускается каждый час на 17-й минуте UTC:

```yaml
- cron: "17 * * * *"
```
