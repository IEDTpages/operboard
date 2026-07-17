"""Prepare the bundled v7 fallback from official sources available at build time."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from refresh_data import SERIES_DEFAULTS, fetch_cbr_trade  # noqa: E402


def prepare(path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["schema_version"] = max(int(payload.get("schema_version", 0)), 4)

    for key in ("production_index", "road_freight"):
        payload["series"][key] = copy.deepcopy(SERIES_DEFAULTS[key])
        payload["status"][key] = {
            "state": "pending",
            "updated_at": None,
            "message": payload["series"][key]["empty_message"],
        }

    trade = fetch_cbr_trade()
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
    print(f"Prepared {path.name}: monthly trade through {trade['exports'][0][-1]}")


def main() -> None:
    for filename in ("current.json", "snapshot.json"):
        prepare(ROOT / "data" / filename)


if __name__ == "__main__":
    main()
