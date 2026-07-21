"""Prepare the bundled v7.5 fallback from official sources available at build time."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from refresh_data import (  # noqa: E402
    SERIES_DEFAULTS,
    fetch_cbr_trade,
    fetch_rosstat_production_history,
    fetch_rosstat_road_freight,
    merge_production_series,
    now_iso,
)


def prepare(
    path: Path,
    trade: dict,
    production: dict,
    road: tuple[list[str], list[float | int]],
) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["schema_version"] = max(int(payload.get("schema_version", 0)), 6)

    payload["series"]["production_index"] = copy.deepcopy(
        SERIES_DEFAULTS["production_index"]
    )
    production_result = merge_production_series(
        payload["series"]["production_index"], production
    )
    for field in (
        "default_mode", "mode_labels", "series_labels", "modes", "dates", "values"
    ):
        payload["series"]["production_index"][field] = production_result[field]
    payload["status"]["production_index"] = {
        "state": "ok",
        "updated_at": now_iso(),
        "message": "Официальная таблица Росстата",
        "fetched_latest": production_result["fetched_latest"],
        "merged_latest": production_result["merged_latest"],
        "new_points": production_result["new_points"],
        "changed_points": production_result["changed_points"],
    }

    payload["series"]["road_freight"] = copy.deepcopy(SERIES_DEFAULTS["road_freight"])
    road_dates, road_values = road
    payload["series"]["road_freight"]["dates"] = road_dates
    payload["series"]["road_freight"]["values"] = road_values
    payload["status"]["road_freight"] = {
        "state": "ok",
        "updated_at": now_iso(),
        "message": "Официальная таблица Росстата",
        "fetched_latest": road_dates[-1],
        "merged_latest": road_dates[-1],
        "new_points": len(road_dates),
        "changed_points": len(road_dates),
    }

    for key in ("exports", "imports"):
        payload["series"][key] = copy.deepcopy(SERIES_DEFAULTS[key])
        dates, values = trade[key]
        payload["series"][key]["dates"] = dates
        payload["series"][key]["values"] = values
        payload["status"][key] = {
            "state": "ok",
            "updated_at": payload.get("generated_at"),
            "message": "Официальный ежемесячный ряд ЦБ РФ",
            "fetched_latest": dates[-1],
            "merged_latest": dates[-1],
            "new_points": len(dates),
            "changed_points": len(dates),
        }

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Prepared {path.name}: production through "
        f"{production_result['fetched_latest']}; monthly trade through "
        f"{trade['exports'][0][-1]}"
    )


def main() -> None:
    trade = fetch_cbr_trade()
    production = fetch_rosstat_production_history()
    road = fetch_rosstat_road_freight()
    for filename in ("current.json", "snapshot.json"):
        prepare(ROOT / "data" / filename, trade, production, road)


if __name__ == "__main__":
    main()
