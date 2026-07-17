from __future__ import annotations

import argparse
import calendar
import io
import json
import math
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin

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

CBR_TRADE_URL = (
    "https://www.cbr.ru/vfs/statistics/credit_statistics/bop/"
    "bal_of_payments_standart.xlsx"
)
ROSSTAT_INDUSTRIAL_URL = "https://rosstat.gov.ru/enterprise_industrial"
ROSSTAT_TRANSPORT_URL = "https://rosstat.gov.ru/statistics/transport"
ATI_HISTORY_URL = "https://api.ati.su/index/license/v1/general_index_dynamic"

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


def post_json(
    url: str,
    *,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
    attempts: int = 3,
) -> requests.Response:
    """POST JSON without ever putting authorization values into logs."""
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = SESSION.post(
                url,
                json=payload,
                headers=headers,
                timeout=TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response
        except Exception as exc:  # noqa: BLE001 - caller records source status
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
        "май": 5, "мая": 5, "мае": 5,
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


def fetch_cbr_currency(
    currency_code: str,
    series_name: str,
) -> tuple[list[str], list[float | int]]:
    """Load an official CBR exchange-rate series and normalize it per 1 unit.

    CBR may publish some currencies with a nominal greater than one. Dividing
    Value by Nominal keeps USD, EUR and CNY directly comparable as rubles per
    one unit of the foreign currency.
    """
    start = START_DATE.strftime("%d/%m/%Y")
    end = (date.today() + timedelta(days=31)).strftime("%d/%m/%Y")
    response = get(
        "https://www.cbr.ru/scripts/XML_dynamic.asp",
        params={
            "date_req1": start,
            "date_req2": end,
            "VAL_NM_RQ": currency_code,
        },
    )
    root = ET.fromstring(response.content)
    rows: list[tuple[date, float]] = []
    for record in root.findall(".//Record"):
        row_date = parse_date(record.attrib.get("Date"))
        value = to_number(record.findtext("Value"))
        nominal = to_number(record.findtext("Nominal")) or 1.0
        if row_date and value is not None and nominal > 0:
            rows.append((row_date, value / nominal))
    dates, values = pack_series(rows)
    validate_numeric_series(dates, values, f"ЦБ РФ — {series_name}")
    return dates, values


def fetch_rubusd() -> tuple[list[str], list[float | int]]:
    return fetch_cbr_currency("R01235", "USD/RUB")


def fetch_rubeur() -> tuple[list[str], list[float | int]]:
    return fetch_cbr_currency("R01239", "EUR/RUB")


def fetch_rubcny() -> tuple[list[str], list[float | int]]:
    return fetch_cbr_currency("R01375", "CNY/RUB")


def fetch_cbr_trade() -> dict[str, tuple[list[str], list[float | int]]]:
    """Load quarterly exports/imports of goods from the official CBR workbook."""
    response = get(CBR_TRADE_URL)
    frame = pd.read_excel(
        io.BytesIO(response.content),
        sheet_name="Кварталы",
        header=None,
    )

    quarter_pattern = re.compile(r"([1-4])\s*квартал\s*(\d{4})", re.IGNORECASE)
    header_row: int | None = None
    quarter_columns: list[tuple[int, int, int]] = []
    for row_index in range(min(15, len(frame))):
        found: list[tuple[int, int, int]] = []
        for column_index, value in enumerate(frame.iloc[row_index]):
            match = quarter_pattern.search(str(value or ""))
            if match:
                found.append((column_index, int(match.group(1)), int(match.group(2))))
        if len(found) > len(quarter_columns):
            header_row, quarter_columns = row_index, found
    if header_row is None or len(quarter_columns) < 4:
        raise RuntimeError("ЦБ РФ: в книге платежного баланса не найдены кварталы")

    goods_row: int | None = None
    for row_index in range(header_row + 1, min(len(frame), header_row + 80)):
        label = _normalise_header(frame.iat[row_index, 0])
        if label == "товары":
            goods_row = row_index
            break
    if goods_row is None:
        raise RuntimeError("ЦБ РФ: в книге платежного баланса не найден раздел «Товары»")

    value_rows: dict[str, int] = {}
    for row_index in range(goods_row + 1, min(len(frame), goods_row + 7)):
        label = _normalise_header(frame.iat[row_index, 0])
        if label == "экспорт":
            value_rows["exports"] = row_index
        elif label == "импорт":
            value_rows["imports"] = row_index
    if set(value_rows) != {"exports", "imports"}:
        raise RuntimeError("ЦБ РФ: не найдены строки экспорта и импорта товаров")

    output: dict[str, tuple[list[str], list[float | int]]] = {}
    for key, row_index in value_rows.items():
        rows: list[tuple[date, float]] = []
        for column_index, quarter, year in quarter_columns:
            if year < START_DATE.year:
                continue
            value = to_number(frame.iat[row_index, column_index])
            if value is None:
                continue
            month = quarter * 3
            period_end = date(year, month, calendar.monthrange(year, month)[1])
            rows.append((period_end, value / 1000.0))  # workbook is in USD millions
        dates, values = pack_series(rows)
        validate_numeric_series(dates, values, f"ЦБ РФ — {key}")
        output[key] = dates, values
    return output


def _extract_production_point(text: str) -> tuple[date, float] | None:
    clean = re.sub(r"\s+", " ", text.replace("\xa0", " ")).lower().replace("ё", "е")
    patterns = (
        r"индекс промышленного производства в ([а-я]+) (\d{4}) года "
        r"по сравнению с[^.]{0,220}?составил\s+([\d.,]+)\s*%",
        r"индекс промышленного производства в ([а-я]+) (\d{4}) года[^.]{0,260}?"
        r"составил\s+([\d.,]+)\s*%",
    )
    for pattern in patterns:
        match = re.search(pattern, clean, re.IGNORECASE)
        if not match:
            continue
        parsed = parse_date(f"1 {match.group(1)} {match.group(2)}")
        value = to_number(match.group(3))
        if parsed and value is not None:
            return (
                date(parsed.year, parsed.month, calendar.monthrange(parsed.year, parsed.month)[1]),
                value,
            )
    return None


def fetch_rosstat_production() -> tuple[list[str], list[float | int]]:
    """Read the latest monthly industrial-production headline from Rosstat."""
    response = get(ROSSTAT_INDUSTRIAL_URL)
    soup = BeautifulSoup(response.text, "lxml")
    candidates: list[str] = []
    for anchor in soup.select("a[href]"):
        container = anchor.parent.parent if anchor.parent and anchor.parent.parent else anchor
        text = _normalise_header(container.get_text(" ", strip=True))
        href = anchor.get("href", "")
        if "промышлен" not in text or not href:
            continue
        url = urljoin(ROSSTAT_INDUSTRIAL_URL, href)
        if url not in candidates and ("/document/" in url or url.endswith((".html", ".htm"))):
            candidates.append(url)

    pages = [(ROSSTAT_INDUSTRIAL_URL, response.text)]
    for url in candidates[:10]:
        try:
            pages.append((url, get(url, attempts=1).text))
        except Exception:  # noqa: BLE001 - try the next official release
            continue

    points: list[tuple[date, float]] = []
    for _, html in pages:
        text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
        point = _extract_production_point(text)
        if point:
            points.append(point)
    if not points:
        raise RuntimeError("Росстат: актуальный месячный индекс производства не распознан")
    dates, values = pack_series(points)
    validate_numeric_series(dates, values, "Росстат — промышленное производство")
    return dates, values


def _parse_period_cell(value: Any) -> date | None:
    """Recognise a year, quarter, month or explicit date in a Rosstat workbook."""
    if (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    ):
        year = int(value)
        if 1990 <= year <= date.today().year + 1 and float(value).is_integer():
            return date(year, 12, 31)
    text = _normalise_header(value)
    year_match = re.fullmatch(r"(19\d{2}|20\d{2})(?:\s*г\.?)?", text)
    if year_match:
        return date(int(year_match.group(1)), 12, 31)
    quarter_match = re.search(r"([1-4])\s*квартал\s*(20\d{2})", text)
    if quarter_match:
        quarter, year = int(quarter_match.group(1)), int(quarter_match.group(2))
        month = quarter * 3
        return date(year, month, calendar.monthrange(year, month)[1])
    month_match = re.search(r"([а-я]+)[\s-]+(20\d{2})", text)
    if month_match:
        parsed = parse_date(f"1 {month_match.group(1)} {month_match.group(2)}")
        if parsed:
            return date(parsed.year, parsed.month, calendar.monthrange(parsed.year, parsed.month)[1])
    parsed = parse_date(value)
    return parsed if parsed and parsed.year >= 1990 else None


def parse_rosstat_road_workbook(content: bytes) -> tuple[list[str], list[float | int]]:
    """Extract the national road-freight time series from a Rosstat workbook.

    Rosstat periodically changes the workbook layout, so the parser supports
    both wide tables (periods in columns) and long two-column tables.
    """
    workbook = pd.ExcelFile(io.BytesIO(content))
    best_rows: list[tuple[date, float]] = []
    best_score = -1

    for sheet_name in workbook.sheet_names:
        frame = pd.read_excel(workbook, sheet_name=sheet_name, header=None)
        text_blob = " ".join(_normalise_header(value) for value in frame.to_numpy().ravel())
        sheet_bonus = 20 if "автомоб" in text_blob and "груз" in text_blob else 0

        # Wide table: one row contains periods and a nearby row contains values.
        for header_index in range(len(frame)):
            periods = [
                (column_index, _parse_period_cell(value))
                for column_index, value in enumerate(frame.iloc[header_index])
            ]
            periods = [(column, period) for column, period in periods if period]
            if len(periods) < 3:
                continue
            for value_index in range(max(0, header_index - 8), min(len(frame), header_index + 9)):
                if value_index == header_index:
                    continue
                rows: list[tuple[date, float]] = []
                for column_index, period in periods:
                    number = to_number(frame.iat[value_index, column_index])
                    if number is not None:
                        rows.append((period, number))
                if len(rows) < 3:
                    continue
                context = " ".join(
                    _normalise_header(value)
                    for value in frame.iloc[value_index, : min(5, frame.shape[1])]
                )
                score = len(rows) + sheet_bonus
                if "автомоб" in context:
                    score += 30
                if "груз" in context:
                    score += 15
                if score > best_score:
                    best_rows, best_score = rows, score

        # Long table: each row has a period and a numeric value.
        long_rows: list[tuple[date, float]] = []
        for row_index in range(len(frame)):
            period: date | None = None
            period_column: int | None = None
            for column_index, value in enumerate(frame.iloc[row_index]):
                period = _parse_period_cell(value)
                if period:
                    period_column = column_index
                    break
            if period is None:
                continue
            numbers = [
                to_number(value)
                for column_index, value in enumerate(frame.iloc[row_index])
                if column_index != period_column
            ]
            number = next((value for value in numbers if value is not None), None)
            if number is not None:
                long_rows.append((period, number))
        if len(long_rows) >= 3 and len(long_rows) + sheet_bonus > best_score:
            best_rows, best_score = long_rows, len(long_rows) + sheet_bonus

    best_rows = [(period, value) for period, value in best_rows if period >= START_DATE]
    if not best_rows:
        raise RuntimeError("Росстат: ряд автоперевозок в XLSX не распознан")
    median = sorted(abs(value) for _, value in best_rows)[len(best_rows) // 2]
    if median > 100_000:  # some releases use thousand tonnes; dashboard uses million tonnes
        best_rows = [(period, value / 1000.0) for period, value in best_rows]
    dates, values = pack_series(best_rows)
    validate_numeric_series(dates, values, "Росстат — автоперевозки")
    return dates, values


def fetch_rosstat_road_freight() -> tuple[list[str], list[float | int]]:
    response = get(ROSSTAT_TRANSPORT_URL)
    soup = BeautifulSoup(response.text, "lxml")
    ranked_candidates: list[tuple[int, str]] = []
    for anchor in soup.select("a[href]"):
        container = anchor.parent.parent if anchor.parent and anchor.parent.parent else anchor
        text = _normalise_header(container.get_text(" ", strip=True))
        href = anchor.get("href", "")
        href_lower = href.lower()
        relevant_text = "автомоб" in text and "груз" in text
        if href_lower.endswith(".xlsx") and ("perevgruz" in href_lower or relevant_text):
            ranked_candidates.append(
                (0 if "perevgruz" in href_lower else 1, urljoin(ROSSTAT_TRANSPORT_URL, href))
            )
    candidates = [url for _, url in sorted(ranked_candidates, key=lambda item: item[0])]
    if not candidates:
        raise RuntimeError("Росстат: ссылка на XLSX по автоперевозкам не найдена")
    last_error: Exception | None = None
    for url in candidates[:5]:
        try:
            return parse_rosstat_road_workbook(get(url, attempts=1).content)
        except Exception as exc:  # noqa: BLE001 - try alternate current/historical workbook
            last_error = exc
    raise RuntimeError(f"Росстат: файл автоперевозок не обработан: {last_error}")


def fetch_ati_ftl() -> tuple[list[str], list[float | int]]:
    """Load ATI.SU's general FTL index using only the server-side GitHub secret."""
    token = os.environ.get("ATI_API_TOKEN", "").strip()
    if not token:
        raise RuntimeError("ATI_API_TOKEN не настроен в GitHub Secrets")
    response = post_json(
        ATI_HISTORY_URL,
        payload={
            "CarType": "all",
            "DateFrom": START_DATE.isoformat(),
            "DateTo": date.today().isoformat(),
        },
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    obj = response.json()
    records = obj.get("Data") or obj.get("data") or []
    rows: list[tuple[date, float]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        row_date = parse_date(record.get("Date") or record.get("date"))
        value = to_number(record.get("Index") if "Index" in record else record.get("index"))
        if row_date and value is not None:
            rows.append((row_date, value))
    dates, values = pack_series(rows)
    validate_numeric_series(dates, values, "ATI.SU — общий индекс FTL")
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


SERIES_DEFAULTS: dict[str, dict[str, Any]] = {
    "production_index": {
        "title": "Индекс промышленного производства",
        "subtitle": "к тому же месяцу прошлого года",
        "chart_label": "Промышленное производство, % г/г",
        "unit": "%",
        "source": "Росстат",
        "source_url": ROSSTAT_INDUSTRIAL_URL,
        "value_decimals": 1,
        "change_decimals": 1,
        "change_type": "pp",
        "change_labels": ["к пред. точке", "3 мес.", "г/г"],
        "change_days": ["previous", 93, 365],
        "frequency": "monthly",
        "page": "production",
        "dates": [
            "2025-02-28", "2025-03-31", "2025-05-31", "2025-09-30",
            "2025-11-30", "2025-12-31", "2026-01-31", "2026-02-28",
            "2026-04-30", "2026-05-31",
        ],
        "values": [100.2, 100.8, 101.8, 100.3, 99.3, 103.7, 99.2, 99.1, 101.9, 99.3],
    },
    "exports": {
        "title": "Экспорт товаров",
        "subtitle": "методология платежного баланса, квартал",
        "chart_label": "Экспорт товаров, млрд $",
        "unit": "млрд $",
        "source": "ЦБ РФ",
        "source_url": CBR_TRADE_URL,
        "value_decimals": 1,
        "change_decimals": 1,
        "change_type": "raw",
        "change_labels": ["кв/кв", "г/г", "3 года"],
        "change_days": ["previous", 365, 1095],
        "frequency": "quarterly",
        "page": "foreign_trade",
        "dates": [],
        "values": [],
    },
    "imports": {
        "title": "Импорт товаров",
        "subtitle": "методология платежного баланса, квартал",
        "chart_label": "Импорт товаров, млрд $",
        "unit": "млрд $",
        "source": "ЦБ РФ",
        "source_url": CBR_TRADE_URL,
        "value_decimals": 1,
        "change_decimals": 1,
        "change_type": "raw",
        "change_labels": ["кв/кв", "г/г", "3 года"],
        "change_days": ["previous", 365, 1095],
        "frequency": "quarterly",
        "page": "foreign_trade",
        "dates": [],
        "values": [],
    },
    "road_freight": {
        "title": "Грузы автотранспортом",
        "subtitle": "объём перевозок",
        "chart_label": "Перевезено грузов автотранспортом, млн т",
        "unit": "млн т",
        "source": "Росстат",
        "source_url": ROSSTAT_TRANSPORT_URL,
        "value_decimals": 1,
        "change_decimals": 1,
        "change_type": "raw",
        "change_labels": ["к пред. периоду", "3 года", "5 лет"],
        "change_days": ["previous", 1095, 1825],
        "frequency": "annual",
        "page": "road_freight",
        "empty_message": "Ряд появится после первого успешного обновления файла Росстата.",
        "dates": [],
        "values": [],
    },
    "ati_ftl": {
        "title": "Индекс ставок ATI.SU FTL",
        "subtitle": "Россия, полная загрузка 20 т / 82 м³",
        "chart_label": "Общий индекс ATI.SU FTL, пунктов",
        "unit": "пунктов",
        "source": "ATI.SU",
        "source_url": "https://help.ati.su/price-index",
        "value_decimals": 1,
        "change_decimals": 1,
        "change_type": "raw",
        "change_labels": ["к пред. дню", "м/м", "г/г"],
        "change_days": ["previous", 31, 365],
        "frequency": "daily",
        "page": "ati_ftl",
        "empty_message": "Добавьте GitHub Secret ATI_API_TOKEN и запустите workflow обновления.",
        "dates": [],
        "values": [],
    },
}


def ensure_series_defaults(payload: dict[str, Any]) -> dict[str, Any]:
    payload.setdefault("series", {})
    payload.setdefault("status", {})
    for key, default in SERIES_DEFAULTS.items():
        if key not in payload["series"]:
            payload["series"][key] = json.loads(json.dumps(default, ensure_ascii=False))
        else:
            for field, value in default.items():
                payload["series"][key].setdefault(field, value)
        payload["status"].setdefault(
            key,
            {
                "state": "pending",
                "updated_at": None,
                "message": payload["series"][key].get("empty_message", "Ожидает обновления"),
            },
        )
    payload["schema_version"] = max(int(payload.get("schema_version", 1)), 3)
    return payload


def load_base_payload() -> dict[str, Any]:
    for path in (DATA_PATH, SNAPSHOT_PATH):
        if path.exists():
            return ensure_series_defaults(json.loads(path.read_text(encoding="utf-8")))
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
    updated = ensure_series_defaults(json.loads(json.dumps(base_payload, ensure_ascii=False)))
    updated.setdefault("status", {})
    updated.setdefault("series", {})

    successes = 0
    failures: dict[str, str] = {}
    actual_changes = 0

    request_jobs: dict[str, Callable[[], tuple[list[str], list[float | int]]]] = {
        "key_rate": fetch_key_rate,
        "rubusd": fetch_rubusd,
        "rubeur": fetch_rubeur,
        "rubcny": fetch_rubcny,
        "cpi": fetch_bizon,
        "production_index": fetch_rosstat_production,
        "road_freight": fetch_rosstat_road_freight,
        "ati_ftl": fetch_ati_ftl,
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

    log("[refresh] CBR foreign trade: loading quarterly workbook…")
    try:
        trade_results = fetch_cbr_trade()
        for key in ("exports", "imports"):
            dates, values = trade_results[key]
            result = merge_numeric_series(updated["series"][key], dates, values)
            updated["series"][key]["dates"] = result["dates"]
            updated["series"][key]["values"] = result["values"]
            updated["status"][key] = status_ok(
                result, "Обновлено из квартальной книги платежного баланса ЦБ РФ"
            )
            successes += 1
            actual_changes += int(result["changed_points"])
            log(
                f"[refresh] {key}: OK; fetched_latest={result['fetched_latest']}; "
                f"new={result['new_points']}; changed={result['changed_points']}"
            )
    except Exception as exc:  # noqa: BLE001
        message = str(exc)[:1000]
        for key in ("exports", "imports"):
            failures[key] = message
            updated["status"][key] = {
                "state": "error",
                "updated_at": now_iso(),
                "message": message,
            }
        log(f"[refresh] CBR foreign trade: ERROR: {message}")

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

    total = len(request_jobs) + 2 + len(PROFINANCE) + 1
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



def validate_required_currency_series(payload: dict[str, Any]) -> None:
    """Ensure essential public series exist before publishing."""
    required = (
        "rubusd", "rubeur", "rubcny", "production_index", "exports", "imports"
    )
    for key in required:
        series = payload.get("series", {}).get(key, {})
        dates = series.get("dates") or []
        values = series.get("values") or []
        if not dates or len(dates) != len(values):
            raise RuntimeError(
                f"Обязательный ряд {key} не загружен или повреждён: "
                f"{len(dates)} дат / {len(values)} значений"
            )
    if os.environ.get("ATI_API_TOKEN", "").strip():
        ati = payload.get("series", {}).get("ati_ftl", {})
        dates, values = ati.get("dates") or [], ati.get("values") or []
        if not dates or len(dates) != len(values):
            raise RuntimeError(
                "ATI_API_TOKEN задан, но ряд ati_ftl не загружен: "
                f"{len(dates)} дат / {len(values)} значений"
            )


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
    validate_required_currency_series(payload)
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
        validate_required_currency_series(payload)
        save_payload(payload)
    except Exception as exc:  # noqa: BLE001
        log(f"[fatal] {exc}")
        return 2

    log(f"[done] Saved {DATA_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
