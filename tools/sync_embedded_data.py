"""Synchronize index.html's offline fallback with data/snapshot.json."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "index.html"
SNAPSHOT_PATH = ROOT / "data" / "snapshot.json"


def main() -> None:
    payload = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    compact = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    html = INDEX_PATH.read_text(encoding="utf-8")
    replacement = f"const EMBEDDED_DATA={compact};\nconst LOGO_DATA="
    updated, count = re.subn(
        r"const EMBEDDED_DATA=.*?;\nconst LOGO_DATA=",
        replacement,
        html,
        count=1,
        flags=re.DOTALL,
    )
    if count != 1:
        raise RuntimeError("EMBEDDED_DATA block was not found exactly once")
    INDEX_PATH.write_text(updated, encoding="utf-8")
    print(f"Embedded {len(payload.get('series', {}))} series into {INDEX_PATH.name}")


if __name__ == "__main__":
    main()
