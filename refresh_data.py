from __future__ import annotations

import json
import math
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / 'data' / 'current.json'
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36 OperboardHTML/1.0'
TIMEOUT = 45
SESSION = requests.Session()
SESSION.headers.update({'User-Agent': USER_AGENT, 'Accept-Language': 'ru,en;q=0.8'})

PROFINANCE = {
    'brent': ('https://www.profinance.ru/charts/brent/lc91h', 'Brent'),
    'urals': ('https://www.profinance.ru/charts/urals_med/lc91h', 'Urals'),
    'ttf': ('https://www.profinance.ru/charts/ttfusd1000/lc91h', 'Газ'),
    'ara': ('https://www.profinance.ru/charts/coaleu/lc91h', 'ARA'),
    'lme': ('https://www.profinance.ru/charts/aluminum/lc91h', 'Алюминий'),
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get(url: str, **kwargs) -> requests.Response:
    r = SESSION.get(url, timeout=TIMEOUT, **kwargs)
    r.raise_for_status()
    return r


def to_number(v: Any) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        x = float(v)
        return x if math.isfinite(x) else None
    s = str(v).strip().replace('\xa0', '').replace(' ', '').replace(',', '.')
    s = re.sub(r'[^0-9+\-.]', '', s)
    if not s or s in {'-', '.', '+', '+.', '-.'}:
        return None
    try:
        x = float(s)
        return x if math.isfinite(x) else None
    except ValueError:
        return None


def parse_date(v: Any) -> date | None:
    if v is None:
        return None
    if isinstance(v, (datetime, date)):
        return v.date() if isinstance(v, datetime) else v
    if isinstance(v, (int, float)) and v > 10_000_000_000:
        try:
            return datetime.fromtimestamp(v / 1000, timezone.utc).date()
        except Exception:
            return None
    s = str(v).strip()[:30]
    for fmt in ('%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y', '%m/%d/%Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            pass
    try:
        return pd.to_datetime(s, dayfirst=True, errors='raise').date()
    except Exception:
        return None


def pack_series(rows: list[tuple[date, float]]) -> tuple[list[str], list[float | int]]:
    dedup: dict[date, float] = {}
    for d, v in rows:
        if d and v is not None and math.isfinite(float(v)):
            dedup[d] = float(v)
    dates = sorted(dedup)
    values = [int(dedup[d]) if dedup[d].is_integer() else dedup[d] for d in dates]
    return [d.isoformat() for d in dates], values


def fetch_profinance(url: str) -> tuple[list[str], list[float | int]]:
    html = get(url).text
    soup = BeautifulSoup(html, 'lxml')
    table = soup.select_one('table#table_history')
    if table is None:
        raise RuntimeError('На странице не найдена таблица #table_history; возможно, сайт изменил разметку или требует браузерный рендеринг')
    rows = []
    for tr in table.select('tr'):
        cells = [c.get_text(' ', strip=True) for c in tr.select('th,td')]
        if len(cells) < 2:
            continue
        d = parse_date(cells[0])
        v = to_number(cells[-1])
        if d and v is not None:
            rows.append((d, v))
    if not rows:
        raise RuntimeError('Таблица ProFinance прочитана, но строки данных не распознаны')
    return pack_series(rows)


def fetch_key_rate() -> tuple[list[str], list[float | int]]:
    start = date.today().replace(year=max(2000, date.today().year - 7)).strftime('%d.%m.%Y')
    end = (date.today() + timedelta(days=31)).strftime('%d.%m.%Y')
    url = f'https://www.cbr.ru/hd_base/keyrate/?UniDbQuery.Posted=True&UniDbQuery.From={start}&UniDbQuery.To={end}'
    soup = BeautifulSoup(get(url).text, 'lxml')
    table = soup.select_one('table.data')
    if table is None:
        raise RuntimeError('На странице ЦБ РФ не найдена таблица ключевой ставки')
    rows = []
    for tr in table.select('tr'):
        c = [x.get_text(' ', strip=True) for x in tr.select('th,td')]
        if len(c) >= 2:
            d, v = parse_date(c[0]), to_number(c[1])
            if d and v is not None:
                rows.append((d, v))
    if not rows:
        raise RuntimeError('Не удалось распознать данные ключевой ставки')
    return pack_series(rows)


def fetch_rubusd() -> tuple[list[str], list[float | int]]:
    d1 = date.today().replace(year=max(2000, date.today().year - 7)).strftime('%d/%m/%Y')
    d2 = (date.today() + timedelta(days=31)).strftime('%d/%m/%Y')
    url = f'https://www.cbr.ru/scripts/XML_dynamic.asp?date_req1={d1}&date_req2={d2}&VAL_NM_RQ=R01235'
    root = ET.fromstring(get(url).content)
    rows = []
    for rec in root.findall('.//Record'):
        d = parse_date(rec.attrib.get('Date'))
        v = to_number(rec.findtext('Value'))
        if d and v is not None:
            rows.append((d, v))
    if not rows:
        raise RuntimeError('XML ЦБ РФ не содержит курсов USD/RUB')
    return pack_series(rows)


def fetch_moex(secid: str) -> tuple[list[str], list[float | int]]:
    rows: list[tuple[date, float]] = []
    start = 0
    while True:
        url = f'https://iss.moex.com/iss/history/engines/stock/markets/index/securities/{secid}.json'
        obj = get(url, params={'start': start, 'iss.meta': 'off'}).json()
        block = obj.get('history') or {}
        cols, data = block.get('columns') or [], block.get('data') or []
        if not data:
            break
        ci = {c: i for i, c in enumerate(cols)}
        for r in data:
            d = parse_date(r[ci['TRADEDATE']]) if 'TRADEDATE' in ci else None
            v = to_number(r[ci['CLOSE']]) if 'CLOSE' in ci else None
            if d and v is not None:
                rows.append((d, v))
        start += len(data)
        if len(data) < 100 or start > 10000:
            break
    if not rows:
        raise RuntimeError(f'MOEX ISS не вернул данные {secid}')
    return pack_series(rows)


def recursive_pairs(obj: Any, out: list[tuple[date, float]]) -> None:
    if isinstance(obj, dict):
        lowered = {str(k).lower(): v for k, v in obj.items()}
        for dk in ('date', 'дата', 'x'):
            if dk in lowered:
                d = parse_date(lowered[dk])
                for vk in ('value', 'значение', 'y'):
                    if vk in lowered:
                        v = to_number(lowered[vk])
                        if d and v is not None:
                            out.append((d, v))
        for v in obj.values():
            recursive_pairs(v, out)
    elif isinstance(obj, list):
        if len(obj) >= 2:
            d = parse_date(obj[0]); v = to_number(obj[1])
            if d and v is not None:
                out.append((d, v))
        for v in obj:
            recursive_pairs(v, out)
    elif isinstance(obj, str):
        m = re.match(r'\s*(\d{4}-\d{2}-\d{2}|\d{2}\.\d{2}\.\d{4})\D+([-+]?\d+(?:[.,]\d+)?)', obj)
        if m:
            d, v = parse_date(m.group(1)), to_number(m.group(2))
            if d and v is not None:
                out.append((d, v))


def fetch_bizon(endpoint: str) -> tuple[list[str], list[float | int]]:
    obj = get(endpoint).json()
    rows: list[tuple[date, float]] = []
    recursive_pairs(obj, rows)
    dates, values = pack_series(rows)
    if len(dates) < 3:
        raise RuntimeError('JSON Bizon получен, но временной ряд не распознан')
    return dates, values


def fetch_hormuz() -> tuple[list[str], dict[str, list[int | float]]]:
    url = 'https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Chokepoints_Data/FeatureServer/0/query'
    params = {'where': "portname = 'STRAIT OF HORMUZ' AND year >= 2025 AND year <= 2035", 'outFields': '*', 'outSR': 4326, 'f': 'json'}
    obj = get(url, params=params).json()
    feats = obj.get('features') or []
    mapping = {'n_container': 'Контейнеровозы', 'n_dry_bulk': 'Балкеры', 'n_general_cargo': 'Сухогрузы', 'n_roro': 'Суда для накатных грузов', 'n_tanker': 'Танкеры'}
    by_date: dict[date, dict[str, float]] = {}
    for f in feats:
        a = f.get('attributes') or {}
        d = parse_date(a.get('date'))
        if not d:
            continue
        by_date[d] = {label: to_number(a.get(field)) or 0 for field, label in mapping.items()}
    if not by_date:
        raise RuntimeError('ArcGIS не вернул данные по Ормузскому проливу')
    ds = sorted(by_date)
    return [d.isoformat() for d in ds], {label: [int(by_date[d][label]) if float(by_date[d][label]).is_integer() else by_date[d][label] for d in ds] for label in mapping.values()}


def refresh_payload(payload: dict) -> dict:
    updated = json.loads(json.dumps(payload, ensure_ascii=False))
    successes = 0
    jobs = {
        'key_rate': fetch_key_rate,
        'rubusd': fetch_rubusd,
        'cpi': lambda: fetch_bizon('https://m.bizon.ru/graph-ctl/rosstat_ipc_10299'),
        'wheat': lambda: fetch_moex('WHFOB'),
        'oil': lambda: fetch_moex('SOEXP'),
    }
    for key, (url, _) in PROFINANCE.items():
        jobs[key] = lambda u=url: fetch_profinance(u)
    for key, fn in jobs.items():
        try:
            dates, values = fn()
            updated['series'][key]['dates'] = dates
            updated['series'][key]['values'] = values
            updated['status'][key] = {'state': 'ok', 'updated_at': now_iso(), 'message': 'Обновлено с веб-источника'}
            successes += 1
        except Exception as e:
            updated['status'][key] = {'state': 'error', 'updated_at': now_iso(), 'message': str(e)[:500]}
    try:
        dates, cats = fetch_hormuz()
        updated['series']['hormuz']['dates'] = dates
        updated['series']['hormuz']['categories'] = cats
        updated['status']['hormuz'] = {'state': 'ok', 'updated_at': now_iso(), 'message': 'Обновлено с ArcGIS / IMF PortWatch'}
        successes += 1
    except Exception as e:
        updated['status']['hormuz'] = {'state': 'error', 'updated_at': now_iso(), 'message': str(e)[:500]}
    updated['generated_at'] = now_iso()
    latest = [s['dates'][-1] for s in updated.get('series', {}).values() if s.get('dates')]
    updated['data_as_of'] = max(latest) if latest else updated.get('data_as_of')
    updated['source_mode'] = 'web_refresh' if successes else 'pbix_snapshot'
    updated['refresh_summary'] = {'successes': successes, 'total': len(jobs) + 1, 'updated_at': now_iso()}
    return updated


def load_current() -> dict:
    return json.loads(DATA_PATH.read_text(encoding='utf-8'))


def save_current(payload: dict) -> None:
    tmp = DATA_PATH.with_suffix('.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(DATA_PATH)


def refresh_file() -> dict:
    payload = refresh_payload(load_current())
    save_current(payload)
    return payload


if __name__ == '__main__':
    p = refresh_file()
    print(json.dumps(p.get('refresh_summary', {}), ensure_ascii=False, indent=2))
