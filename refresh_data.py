from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import requests
from bs4 import BeautifulSoup

try:
    from playwright.sync_api import Browser, Page, sync_playwright
except ImportError:  # Allows request-only sources to be diagnosed locally.
    Browser = Any  # type: ignore[misc,assignment]
    Page = Any  # type: ignore[misc,assignment]
    sync_playwright = None

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DATA_PATH = DATA_DIR / "current.json"
SNAPSHOT_PATH = DATA_DIR / "snapshot.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36 OperboardHTML/2.0"
)
TIMEOUT_SECONDS = 45
START_DATE = date(2021, 1, 1)

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": USER_AGENT,
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.8,*/*;q=0.7",
    }
)

PROFINANCE: dict[str, str] = {
    "brent": "https://www.profinance.ru/charts/brent/lc91h",
    "urals": "https://www.profinance.ru/charts/urals_med/lc91h",
    "ttf": "https://www.profinance.ru/charts/ttfusd1000/lc91h",
    "ara": "https://www.profinance.ru/charts/coaleu/lc91h",
    "lme": "https://www.profinance.ru/charts/aluminum/lc91h",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def log(message: str) -> None:
    print(message, flush=True)


def get(url: str, *, attempts: int = 3, **kwargs: Any) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = SESSION.get(url, timeout=TIMEOUT_SECONDS, **kwargs)
            response.raise_for_status()
            return response
        except Exception as exc:  # noqa: BLE001 - log precise external-source failure
            last_error = exc
            if attempt < attempts:
                time.sleep(attempt * 2)
    assert last_error is not None
    raise last_error


def to_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None

    text = str(value).strip().replace("\xa0", "").replace(" ", "").replace(",", ".")
    text = re.sub(r"[^0-9+\-.]", "", text)
    if not text or text in {"-", ".", "+", "+.", "-."}:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        # Web charts may expose Unix time either in seconds or milliseconds.
        try:
            timestamp = float(value)
            if timestamp > 10_000_000_000:
                timestamp /= 1000
            if timestamp > 100_000_000:
                return datetime.fromtimestamp(timestamp, timezone.utc).date()
        except (OverflowError, OSError, ValueError, TypeError):
            return None

    text = str(value).strip().replace("\xa0", " ")[:80]
    text = re.sub(r"\s+", " ", text)

    # Russian month names are not reliably parsed on systems without a Russian locale.
    russian_months = {
        "янв": 1, "январ": 1,
        "фев": 2, "феврал": 2,
        "мар": 3, "март": 3,
        "апр": 4, "апрел": 4,
        "май": 5, "мая": 5,
        "июн": 6, "июнь": 6, "июня": 6,
        "июл": 7, "июль": 7, "июля": 7,
        "авг": 8, "август": 8,
        "сен": 9, "сент": 9, "сентябр": 9,
        "окт": 10, "октябр": 10,
        "ноя": 11, "нояб": 11, "ноябр": 11,
        "дек": 12, "декабр": 12,
    }
    lowered = text.lower().replace("ё", "е")
    match = re.search(r"(?<!\d)(\d{1,2})[ .-]+([а-я]+)\.?[ ,.-]+(\d{2,4})(?!\d)", lowered)
    if match:
        day_value = int(match.group(1))
        month_word = match.group(2)
        year_value = int(match.group(3))
        if year_value < 100:
            year_value += 2000
        month_value = next(
            (number for word, number in russian_months.items() if month_word.startswith(word)),
            None,
        )
        if month_value:
            try:
                return date(year_value, month_value, day_value)
            except ValueError:
                return None

    formats = (
        "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d",
        "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y",
        "%d.%m.%y", "%d/%m/%y", "%d-%m-%y",
        "%m/%d/%Y", "%m/%d/%y", "%Y%m%d",
    )
    candidates = [text, text[:10], text[:8]]
    for candidate in candidates:
        for fmt in formats:
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                pass
    try:
        parsed = pd.to_datetime(text, dayfirst=True, errors="raise")
        return parsed.date()
    except Exception:  # noqa: BLE001
        return None


def normalise_number(number: float) -> float | int:
    return int(number) if float(number).is_integer() else round(float(number), 8)


def pack_series(rows: list[tuple[date, float]]) -> tuple[list[str], list[float | int]]:
    deduplicated: dict[date, float] = {}
    for row_date, value in rows:
        if row_date and value is not None and math.isfinite(float(value)):
            deduplicated[row_date] = float(value)
    ordered_dates = sorted(deduplicated)
    return (
        [item.isoformat() for item in ordered_dates],
        [normalise_number(deduplicated[item]) for item in ordered_dates],
    )


def validate_numeric_series(dates: list[str], values: list[float | int], source: str) -> None:
    if len(dates) != len(values):
        raise RuntimeError(f"{source}: число дат и значений не совпадает")
    if not dates:
        raise RuntimeError(f"{source}: источник вернул пустой ряд")
    parsed = [parse_date(item) for item in dates]
    if any(item is None for item in parsed):
        raise RuntimeError(f"{source}: обнаружена некорректная дата")
    if dates != sorted(dates):
        raise RuntimeError(f"{source}: даты не отсортированы")


def merge_numeric_series(
    existing: dict[str, Any], fetched_dates: list[str], fetched_values: list[float | int]
) -> dict[str, Any]:
    validate_numeric_series(fetched_dates, fetched_values, "веб-источник")
    merged: dict[str, float | int] = {}
    for item_date, value in zip(existing.get("dates", []), existing.get("values", []), strict=False):
        if parse_date(item_date) is not None and to_number(value) is not None:
            merged[str(item_date)] = normalise_number(float(to_number(value)))
    before = dict(merged)
    for item_date, value in zip(fetched_dates, fetched_values, strict=True):
        number = to_number(value)
        if number is not None:
            merged[item_date] = normalise_number(number)

    ordered = sorted(merged)
    changed = sum(1 for key, value in merged.items() if before.get(key) != value)
    return {
        "dates": ordered,
        "values": [merged[item] for item in ordered],
        "changed_points": changed,
        "new_points": sum(1 for item in fetched_dates if item not in before),
        "fetched_latest": fetched_dates[-1],
        "merged_latest": ordered[-1],
    }


def fetch_key_rate() -> tuple[list[str], list[float | int]]:
    start = START_DATE.strftime("%d.%m.%Y")
    end = (date.today() + timedelta(days=31)).strftime("%d.%m.%Y")
    url = "https://www.cbr.ru/hd_base/keyrate/"
    response = get(
        url,
        params={
            "UniDbQuery.Posted": "True",
            "UniDbQuery.From": start,
            "UniDbQuery.To": end,
        },
    )
    soup = BeautifulSoup(response.text, "lxml")
    table = soup.select_one("table.data")
    if table is None:
        raise RuntimeError("ЦБ РФ: таблица ключевой ставки table.data не найдена")

    rows: list[tuple[date, float]] = []
    for table_row in table.select("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in table_row.select("th,td")]
        if len(cells) >= 2:
            row_date, value = parse_date(cells[0]), to_number(cells[1])
            if row_date and value is not None:
                rows.append((row_date, value))
    dates, values = pack_series(rows)
    validate_numeric_series(dates, values, "ЦБ РФ — ключевая ставка")
    return dates, values


def fetch_rubusd() -> tuple[list[str], list[float | int]]:
    start = START_DATE.strftime("%d/%m/%Y")
    end = (date.today() + timedelta(days=31)).strftime("%d/%m/%Y")
    response = get(
        "https://www.cbr.ru/scripts/XML_dynamic.asp",
        params={"date_req1": start, "date_req2": end, "VAL_NM_RQ": "R01235"},
    )
    root = ET.fromstring(response.content)
    rows: list[tuple[date, float]] = []
    for record in root.findall(".//Record"):
        row_date = parse_date(record.attrib.get("Date"))
        value = to_number(record.findtext("Value"))
        if row_date and value is not None:
            rows.append((row_date, value))
    dates, values = pack_series(rows)
    validate_numeric_series(dates, values, "ЦБ РФ — USD/RUB")
    return dates, values


def fetch_moex(secid: str) -> tuple[list[str], list[float | int]]:
    rows: list[tuple[date, float]] = []
    start = 0
    page_size = 100
    url = f"https://iss.moex.com/iss/history/engines/stock/markets/index/securities/{secid}.json"

    while start <= 20_000:
        obj = get(url, params={"start": start, "limit": page_size, "iss.meta": "off"}).json()
        block = obj.get("history") or {}
        columns = block.get("columns") or []
        data = block.get("data") or []
        if not data:
            break
        column_index = {name: idx for idx, name in enumerate(columns)}
        if "TRADEDATE" not in column_index or "CLOSE" not in column_index:
            raise RuntimeError(f"MOEX {secid}: нет столбцов TRADEDATE/CLOSE")
        for row in data:
            row_date = parse_date(row[column_index["TRADEDATE"]])
            value = to_number(row[column_index["CLOSE"]])
            if row_date and value is not None:
                rows.append((row_date, value))
        start += len(data)
        if len(data) < page_size:
            break

    dates, values = pack_series(rows)
    validate_numeric_series(dates, values, f"MOEX {secid}")
    return dates, values


def recursive_pairs(obj: Any, output: list[tuple[date, float]]) -> None:
    if isinstance(obj, dict):
        lowered = {str(key).lower(): value for key, value in obj.items()}
        for date_key in ("date", "дата", "x"):
            if date_key not in lowered:
                continue
            row_date = parse_date(lowered[date_key])
            for value_key in ("value", "значение", "y"):
                if value_key in lowered:
                    value = to_number(lowered[value_key])
                    if row_date and value is not None:
                        output.append((row_date, value))
        for value in obj.values():
            recursive_pairs(value, output)
    elif isinstance(obj, list):
        if len(obj) >= 2:
            row_date, value = parse_date(obj[0]), to_number(obj[1])
            if row_date and value is not None:
                output.append((row_date, value))
        for value in obj:
            recursive_pairs(value, output)
    elif isinstance(obj, str):
        match = re.match(
            r"\s*(\d{4}-\d{2}-\d{2}|\d{2}\.\d{2}\.\d{4})\D+([-+]?\d+(?:[.,]\d+)?)",
            obj,
        )
        if match:
            row_date, value = parse_date(match.group(1)), to_number(match.group(2))
            if row_date and value is not None:
                output.append((row_date, value))


def fetch_bizon() -> tuple[list[str], list[float | int]]:
    endpoint = "https://m.bizon.ru/graph-ctl/rosstat_ipc_10299"
    obj = get(endpoint, headers={"Accept": "application/json,text/plain,*/*"}).json()
    rows: list[tuple[date, float]] = []
    recursive_pairs(obj, rows)
    dates, values = pack_series(rows)
    if len(dates) < 3:
        raise RuntimeError("Bizon/Росстат: JSON получен, но временной ряд не распознан")
    return dates, values


def _normalise_header(value: Any) -> str:
    text = str(value or "").strip().lower().replace("ё", "е")
    return re.sub(r"\s+", " ", text)


def parse_profinance_rows(rows: list[list[str]], source_name: str) -> tuple[list[str], list[float | int]]:
    """Parse a ProFinance history table without relying on fixed visible-cell layout."""
    clean_rows: list[list[str]] = []
    for row in rows:
        if not isinstance(row, list):
            continue
        cells = [str(cell or "").strip() for cell in row]
        if any(cells):
            clean_rows.append(cells)

    if not clean_rows:
        raise RuntimeError(f"{source_name}: DOM-таблица найдена, но все ячейки пусты")

    header_index: int | None = None
    date_index: int | None = None
    close_index: int | None = None
    date_names = ("дата", "время", "date", "time")
    close_names = ("close", "закрытие", "последняя", "последнее", "цена", "last")

    for row_index, cells in enumerate(clean_rows[:8]):
        headers = [_normalise_header(cell) for cell in cells]
        possible_date = next(
            (index for index, header in enumerate(headers) if any(name in header for name in date_names)),
            None,
        )
        possible_close = next(
            (index for index, header in enumerate(headers) if any(name in header for name in close_names)),
            None,
        )
        if possible_date is not None or possible_close is not None:
            header_index = row_index
            date_index = possible_date
            close_index = possible_close
            break

    parsed: list[tuple[date, float]] = []
    data_rows = clean_rows[(header_index + 1) if header_index is not None else 0 :]
    for cells in data_rows:
        row_date: date | None = None
        current_date_index: int | None = date_index
        if current_date_index is not None and current_date_index < len(cells):
            row_date = parse_date(cells[current_date_index])
        if row_date is None:
            for index, cell in enumerate(cells):
                candidate = parse_date(cell)
                if candidate is not None and 1990 <= candidate.year <= date.today().year + 2:
                    row_date = candidate
                    current_date_index = index
                    break
        if row_date is None:
            continue

        value: float | None = None
        if close_index is not None and close_index < len(cells):
            value = to_number(cells[close_index])

        # Historical ProFinance tables traditionally place Close in the fifth column.
        # Prefer that position, then fall back to the last numeric cell after the date.
        if value is None and len(cells) >= 5:
            value = to_number(cells[4])
        if value is None:
            numeric_candidates: list[float] = []
            for index, cell in enumerate(cells):
                if index == current_date_index:
                    continue
                number = to_number(cell)
                if number is not None:
                    numeric_candidates.append(number)
            if numeric_candidates:
                value = numeric_candidates[-1]

        if value is not None:
            parsed.append((row_date, value))

    dates, values = pack_series(parsed)
    if not dates:
        sample = json.dumps(clean_rows[:5], ensure_ascii=False)[:1800]
        raise RuntimeError(
            f"{source_name}: не удалось распознать даты/Close; "
            f"rows={len(clean_rows)}; sample={sample}"
        )
    validate_numeric_series(dates, values, source_name)
    return dates, values


def fetch_profinance_requests(url: str, source_name: str) -> tuple[list[str], list[float | int]]:
    """Fast path for cases where the HTML table is already present server-side."""
    soup = BeautifulSoup(get(url).text, "lxml")
    table = soup.select_one("table#table_history")
    if table is None:
        raise RuntimeError("table#table_history отсутствует в HTTP-ответе")
    rows = [
        [
            cell.get_text(" ", strip=True)
            or cell.get("data-value", "")
            or cell.get("value", "")
            or cell.get("title", "")
            for cell in table_row.select("th,td")
        ]
        for table_row in table.select("tr")
    ]
    return parse_profinance_rows(rows, source_name)


def _browser_table_rows(page: Page) -> list[list[str]]:
    rows = page.locator("table#table_history tr").evaluate_all(
        r"""
        rows => rows.map(row =>
          Array.from(row.querySelectorAll('th,td')).map(cell => {
            const candidates = [
              cell.textContent,
              cell.innerText,
              cell.getAttribute('data-value'),
              cell.getAttribute('data-val'),
              cell.getAttribute('value'),
              cell.getAttribute('title'),
              cell.getAttribute('aria-label')
            ];
            return (candidates.find(value => value && value.trim()) || '')
              .replace(/\u00a0/g, ' ')
              .replace(/\s+/g, ' ')
              .trim();
          })
        )
        """
    )
    return rows if isinstance(rows, list) else []


def fetch_profinance_browser(page: Page, url: str, source_name: str) -> tuple[list[str], list[float | int]]:
    page.goto(url, wait_until="domcontentloaded", timeout=90_000)
    try:
        page.wait_for_load_state("networkidle", timeout=25_000)
    except Exception:  # noqa: BLE001 - analytics may keep connections open
        pass

    page.wait_for_selector("table#table_history", state="attached", timeout=60_000)
    try:
        page.locator("table#table_history").scroll_into_view_if_needed(timeout=10_000)
    except Exception:  # noqa: BLE001
        pass

    # The table shell can appear before AJAX fills its cells. Poll until the
    # table contains recognisable values instead of reading the empty shell.
    last_rows: list[list[str]] = []
    last_error: Exception | None = None
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        last_rows = _browser_table_rows(page)
        try:
            return parse_profinance_rows(last_rows, source_name)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        page.wait_for_timeout(2000)

    title = page.title()
    sample = json.dumps(last_rows[:5], ensure_ascii=False)[:1800]
    raise RuntimeError(
        f"таблица не заполнилась за 90 с; title={title!r}; url={page.url!r}; "
        f"rows={len(last_rows)}; sample={sample}; last={last_error}"
    )


def fetch_all_profinance() -> tuple[
    dict[str, tuple[list[str], list[float | int]]], dict[str, str]
]:
    results: dict[str, tuple[list[str], list[float | int]]] = {}
    errors: dict[str, str] = {}

    browser_needed: list[tuple[str, str]] = []
    for key, url in PROFINANCE.items():
        try:
            results[key] = fetch_profinance_requests(url, f"ProFinance {key}")
        except Exception as exc:  # noqa: BLE001
            browser_needed.append((key, url))
            errors[key] = f"HTTP parser: {exc}"

    if not browser_needed:
        return results, errors
    if sync_playwright is None:
        for key, _ in browser_needed:
            errors[key] += "; Playwright не установлен"
        return results, errors

    with sync_playwright() as playwright:
        browser: Browser = playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = browser.new_context(
            user_agent=USER_AGENT,
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            viewport={"width": 1440, "height": 1200},
            java_script_enabled=True,
        )
        context.set_extra_http_headers(
            {
                "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
                "Referer": "https://www.profinance.ru/",
            }
        )
        page = context.new_page()
        page.set_default_timeout(60_000)
        # Reduce the most obvious automation marker used by some page scripts.
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        for key, url in browser_needed:
            try:
                results[key] = fetch_profinance_browser(page, url, f"ProFinance {key}")
                errors.pop(key, None)
            except Exception as exc:  # noqa: BLE001
                errors[key] = f"Browser parser: {exc}"
            finally:
                try:
                    page.goto("about:blank", wait_until="commit", timeout=10_000)
                except Exception:  # noqa: BLE001
                    pass
        context.close()
        browser.close()
    return results, errors


def fetch_hormuz() -> tuple[list[str], dict[str, list[int | float]]]:
    url = (
        "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/"
        "Daily_Chokepoints_Data/FeatureServer/0/query"
    )
    params = {
        "where": "portname = 'STRAIT OF HORMUZ' AND year >= 2025",
        "outFields": "date,n_container,n_dry_bulk,n_general_cargo,n_roro,n_tanker",
        "orderByFields": "date ASC",
        "returnGeometry": "false",
        "resultRecordCount": 5000,
        "f": "json",
    }
    obj = get(url, params=params).json()
    if obj.get("error"):
        raise RuntimeError(f"ArcGIS: {obj['error']}")

    mapping = {
        "n_container": "Контейнеровозы",
        "n_dry_bulk": "Балкеры",
        "n_general_cargo": "Сухогрузы",
        "n_roro": "Суда для накатных грузов",
        "n_tanker": "Танкеры",
    }
    by_date: dict[date, dict[str, float]] = {}
    for feature in obj.get("features") or []:
        attributes = feature.get("attributes") or {}
        row_date = parse_date(attributes.get("date"))
        if not row_date:
            continue
        by_date[row_date] = {
            label: float(to_number(attributes.get(field)) or 0)
            for field, label in mapping.items()
        }
    if not by_date:
        raise RuntimeError("ArcGIS/IMF PortWatch: данные по Ормузскому проливу не получены")

    ordered_dates = sorted(by_date)
    dates = [item.isoformat() for item in ordered_dates]
    categories = {
        label: [normalise_number(by_date[item][label]) for item in ordered_dates]
        for label in mapping.values()
    }
    return dates, categories


def merge_hormuz_series(
    existing: dict[str, Any], fetched_dates: list[str], fetched_categories: dict[str, list[int | float]]
) -> dict[str, Any]:
    categories = set(existing.get("categories", {})) | set(fetched_categories)
    merged: dict[str, dict[str, float | int]] = {}

    existing_dates = existing.get("dates", [])
    for category in categories:
        values = existing.get("categories", {}).get(category, [])
        for item_date, value in zip(existing_dates, values, strict=False):
            number = to_number(value)
            if parse_date(item_date) and number is not None:
                merged.setdefault(item_date, {})[category] = normalise_number(number)
    before = json.loads(json.dumps(merged, ensure_ascii=False))

    for category, values in fetched_categories.items():
        if len(values) != len(fetched_dates):
            raise RuntimeError(f"Hormuz: размер категории {category} не совпадает с датами")
        for item_date, value in zip(fetched_dates, values, strict=True):
            number = to_number(value)
            if number is not None:
                merged.setdefault(item_date, {})[category] = normalise_number(number)

    ordered_dates = sorted(merged)
    ordered_categories = sorted(categories)
    output_categories = {
        category: [merged[item_date].get(category, 0) for item_date in ordered_dates]
        for category in ordered_categories
    }
    changed = sum(1 for key, value in merged.items() if before.get(key) != value)
    return {
        "dates": ordered_dates,
        "categories": output_categories,
        "changed_points": changed,
        "new_points": sum(1 for item in fetched_dates if item not in before),
        "fetched_latest": fetched_dates[-1],
        "merged_latest": ordered_dates[-1],
    }


def load_base_payload() -> dict[str, Any]:
    for path in (DATA_PATH, SNAPSHOT_PATH):
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    raise FileNotFoundError("Не найдены data/current.json и data/snapshot.json")


def save_payload(payload: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary = DATA_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(DATA_PATH)


def status_ok(result: dict[str, Any], message: str) -> dict[str, Any]:
    return {
        "state": "ok",
        "updated_at": now_iso(),
        "message": message,
        "fetched_latest": result.get("fetched_latest"),
        "merged_latest": result.get("merged_latest"),
        "new_points": result.get("new_points", 0),
        "changed_points": result.get("changed_points", 0),
    }


def refresh_payload(base_payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    updated = json.loads(json.dumps(base_payload, ensure_ascii=False))
    updated.setdefault("status", {})
    updated.setdefault("series", {})

    successes = 0
    failures: dict[str, str] = {}
    actual_changes = 0

    request_jobs: dict[str, Callable[[], tuple[list[str], list[float | int]]]] = {
        "key_rate": fetch_key_rate,
        "rubusd": fetch_rubusd,
        "cpi": fetch_bizon,
        "wheat": lambda: fetch_moex("WHFOB"),
        "oil": lambda: fetch_moex("SOEXP"),
    }

    for key, job in request_jobs.items():
        log(f"[refresh] {key}: loading…")
        try:
            dates, values = job()
            result = merge_numeric_series(updated["series"][key], dates, values)
            updated["series"][key]["dates"] = result["dates"]
            updated["series"][key]["values"] = result["values"]
            updated["status"][key] = status_ok(result, "Обновлено с веб-источника")
            successes += 1
            actual_changes += int(result["changed_points"])
            log(
                f"[refresh] {key}: OK; fetched_latest={result['fetched_latest']}; "
                f"new={result['new_points']}; changed={result['changed_points']}"
            )
        except Exception as exc:  # noqa: BLE001
            message = str(exc)[:1000]
            failures[key] = message
            updated["status"][key] = {
                "state": "error",
                "updated_at": now_iso(),
                "message": message,
            }
            log(f"[refresh] {key}: ERROR: {message}")

    log("[refresh] ProFinance: loading rendered tables…")
    profinance_results, profinance_errors = fetch_all_profinance()
    for key in PROFINANCE:
        if key in profinance_results:
            try:
                dates, values = profinance_results[key]
                result = merge_numeric_series(updated["series"][key], dates, values)
                updated["series"][key]["dates"] = result["dates"]
                updated["series"][key]["values"] = result["values"]
                updated["status"][key] = status_ok(
                    result, "Обновлено из таблицы ProFinance через Chromium"
                )
                successes += 1
                actual_changes += int(result["changed_points"])
                log(
                    f"[refresh] {key}: OK; fetched_latest={result['fetched_latest']}; "
                    f"new={result['new_points']}; changed={result['changed_points']}"
                )
            except Exception as exc:  # noqa: BLE001
                message = str(exc)[:1000]
                failures[key] = message
                updated["status"][key] = {
                    "state": "error",
                    "updated_at": now_iso(),
                    "message": message,
                }
                log(f"[refresh] {key}: ERROR: {message}")
        else:
            message = profinance_errors.get(key, "неизвестная ошибка ProFinance")[:1000]
            failures[key] = message
            updated["status"][key] = {
                "state": "error",
                "updated_at": now_iso(),
                "message": message,
            }
            log(f"[refresh] {key}: ERROR: {message}")

    log("[refresh] hormuz: loading…")
    try:
        dates, categories = fetch_hormuz()
        result = merge_hormuz_series(updated["series"]["hormuz"], dates, categories)
        updated["series"]["hormuz"]["dates"] = result["dates"]
        updated["series"]["hormuz"]["categories"] = result["categories"]
        updated["status"]["hormuz"] = status_ok(
            result, "Обновлено с ArcGIS / IMF PortWatch"
        )
        successes += 1
        actual_changes += int(result["changed_points"])
        log(
            f"[refresh] hormuz: OK; fetched_latest={result['fetched_latest']}; "
            f"new={result['new_points']}; changed_dates={result['changed_points']}"
        )
    except Exception as exc:  # noqa: BLE001
        message = str(exc)[:1000]
        failures["hormuz"] = message
        updated["status"]["hormuz"] = {
            "state": "error",
            "updated_at": now_iso(),
            "message": message,
        }
        log(f"[refresh] hormuz: ERROR: {message}")

    total = len(request_jobs) + len(PROFINANCE) + 1
    latest_dates = [
        series["dates"][-1]
        for series in updated.get("series", {}).values()
        if isinstance(series, dict) and series.get("dates")
    ]
    updated["generated_at"] = now_iso()
    updated["data_as_of"] = max(latest_dates) if latest_dates else updated.get("data_as_of")
    updated["source_mode"] = "web_refresh" if successes else "pbix_snapshot"
    summary = {
        "successes": successes,
        "failures": total - successes,
        "total": total,
        "actual_changed_points": actual_changes,
        "updated_at": now_iso(),
        "failed_sources": failures,
    }
    updated["refresh_summary"] = summary
    return updated, summary



def load_current() -> dict[str, Any]:
    """Return the last successfully saved dashboard payload."""
    return load_base_payload()


def refresh_file(min_success: int = 4) -> dict[str, Any]:
    """Refresh web sources and atomically save current.json.

    The existing file is preserved when too few sources can be read. This
    function is used by the local HTTP server as well as by command-line runs.
    """
    payload, summary = refresh_payload(load_base_payload())
    if int(summary.get("successes", 0)) < min_success:
        failed = summary.get("failed_sources", {})
        details = "; ".join(f"{key}: {value}" for key, value in list(failed.items())[:4])
        raise RuntimeError(
            f"Обновлено только {summary.get('successes', 0)} из {summary.get('total', 0)} "
            f"источников; требуется минимум {min_success}. {details}"
        )
    save_payload(payload)
    return payload

def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh Operboard web data")
    parser.add_argument(
        "--min-success",
        type=int,
        default=1,
        help="Do not write current.json when fewer sources were read successfully",
    )
    args = parser.parse_args()

    try:
        payload, summary = refresh_payload(load_base_payload())
        log(json.dumps(summary, ensure_ascii=False, indent=2))
        if summary["successes"] < args.min_success:
            log(
                f"[fatal] Successfully read only {summary['successes']} of {summary['total']} sources; "
                f"required at least {args.min_success}. data/current.json was NOT overwritten."
            )
            return 3
        save_payload(payload)
    except Exception as exc:  # noqa: BLE001
        log(f"[fatal] {exc}")
        return 2

    log(f"[done] Saved {DATA_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
