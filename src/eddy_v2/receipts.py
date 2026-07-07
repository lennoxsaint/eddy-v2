from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class Receipts:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, event: str, **fields: Any) -> dict[str, Any]:
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **fields,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")
        return row

    def read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows
