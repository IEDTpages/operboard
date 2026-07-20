"""Seed Operboard history from user-provided EMISS XLS exports.

The resulting dashboard does not query EMISS. Subsequent observations and
official revisions are merged from the public Rosstat workbooks.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from refresh_data import (  # noqa: E402
    DATA_PATH,
    SNAPSHOT_PATH,
    SERIES_DEFAULTS,
    ensure_series_defaults,
    merge_production_series,
    now_iso,
    parse_rosstat_production_workbook,
    parse_rosstat_road_workbook,
)


def _latest_dashboard_date(payload: dict) -> str | None:
    dates = [
        series["dates"][-1]
        for series in payload.get("series", {}).values()
        if isinstance(series, dict) and series.get("dates")
    ]
    return max(dates) if dates else None


def seed_payload(
    path: Path,
    production: dict,
    road_dates: list[str],
    road_values: list[float | int],
) -> None:
    payload = ensure_series_defaults(json.loads(path.read_text(encoding="utf-8")))
    stamp = now_iso()

    payload["series"]["production_index"] = copy.deepcopy(
        SERIES_DEFAULTS["production_index"]
    )
    production_result = merge_production_series(
        payload["series"]["production_index"], production
    )
    for field in (
        "default_mode",
        "mode_labels",
        "series_labels",
        "modes",
        "dates",
        "values",
    ):
        payload["series"]["production_index"][field] = production_result[field]
    payload["status"]["production_index"] = {
        "state": "seed",
        "updated_at": stamp,
        "message": (
            "Ретроспектива импортирована из выгрузки ЕМИСС; "
            "регулярное обновление настроено из таблиц Росстата"
        ),
        "fetched_latest": production_result["fetched_latest"],
        "merged_latest": production_result["merged_latest"],
        "new_points": production_result["new_points"],
        "changed_points": production_result["changed_points"],
    }

    payload["series"]["road_freight"] = copy.deepcopy(
        SERIES_DEFAULTS["road_freight"]
    )
    payload["series"]["road_freight"]["dates"] = road_dates
    payload["series"]["road_freight"]["values"] = road_values
    payload["status"]["road_freight"] = {
        "state": "seed",
        "updated_at": stamp,
        "message": (
            "Ретроспектива импортирована из выгрузки ЕМИСС; "
            "регулярное обновление настроено из таблиц Росстата"
        ),
        "fetched_latest": road_dates[-1],
        "merged_latest": road_dates[-1],
        "new_points": len(road_dates),
        "changed_points": len(road_dates),
    }

    payload["schema_version"] = max(int(payload.get("schema_version", 1)), 6)
    payload["generated_at"] = stamp
    payload["data_as_of"] = _latest_dashboard_date(payload)
    payload["source_mode"] = "emiss_history_seed_rosstat_refresh"
    # A previous web-refresh summary may mention sources that were intentionally
    # replaced by this seed. The next workflow run will write a fresh summary.
    payload.pop("refresh_summary", None)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("production_xls", type=Path)
    parser.add_argument("road_xls", type=Path)
    args = parser.parse_args()

    production = parse_rosstat_production_workbook(args.production_xls.read_bytes())
    road_dates, road_values = parse_rosstat_road_workbook(args.road_xls.read_bytes())

    for mode, block in production["modes"].items():
        if len(block["dates"]) != 36:
            raise RuntimeError(f"ИПП {mode}: ожидалось 36 месяцев, получено {len(block['dates'])}")
        if block["dates"][0] != "2023-01-31" or block["dates"][-1] != "2025-12-31":
            raise RuntimeError(f"ИПП {mode}: неверные границы ретроспективы")
    if len(road_dates) != 60:
        raise RuntimeError(
            f"Автоперевозки: ожидалось 60 месяцев, получено {len(road_dates)}"
        )
    if road_dates[0] != "2021-01-31" or road_dates[-1] != "2025-12-31":
        raise RuntimeError("Автоперевозки: неверные границы ретроспективы")

    for path in (DATA_PATH, SNAPSHOT_PATH):
        seed_payload(path, production, road_dates, road_values)
        print(f"Seeded {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
