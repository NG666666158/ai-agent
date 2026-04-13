from __future__ import annotations

import json
import logging
from time import perf_counter
from typing import Any


logger = logging.getLogger("orion_agent")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


def log_event(event: str, **payload: Any) -> None:
    logger.info(json.dumps({"event": event, **payload}, ensure_ascii=False, default=str))


class Timer:
    def __init__(self, name: str, **payload: Any) -> None:
        self.name = name
        self.payload = payload
        self.start = 0.0

    def __enter__(self):
        self.start = perf_counter()
        log_event(f"{self.name}.start", **self.payload)
        return self

    def __exit__(self, exc_type, exc, tb):
        elapsed_ms = round((perf_counter() - self.start) * 1000, 2)
        if exc:
            log_event(f"{self.name}.error", elapsed_ms=elapsed_ms, error=str(exc), **self.payload)
        else:
            log_event(f"{self.name}.success", elapsed_ms=elapsed_ms, **self.payload)
        return False
