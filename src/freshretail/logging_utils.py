"""运行日志：JSONL 事件流 + 运行摘要。"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from pathlib import Path

from . import config


class RunLogger:
    def __init__(self, name: str):
        config.LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.run_id = f"{datetime.now():%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"
        self.name = name
        self.path = config.LOG_DIR / f"{name}_{self.run_id}.jsonl"
        self.records: list[dict] = []
        self._t0 = time.time()

    def log(self, event: str, **fields) -> None:
        rec = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "run_id": self.run_id,
            "event": event,
            **fields,
        }
        self.records.append(rec)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        print(f"[{rec['ts']}] {event} {fields if fields else ''}")

    def summary(self) -> dict:
        return {
            "run_id": self.run_id,
            "name": self.name,
            "elapsed_seconds": round(time.time() - self._t0, 2),
            "events": len(self.records),
        }
