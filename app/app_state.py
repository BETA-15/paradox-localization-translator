from __future__ import annotations

import time
import uuid
from collections.abc import Iterable, MutableMapping
from dataclasses import dataclass, field

QUEUE_ITEM_ID_KEY = "queue_item_id"


def ensure_queue_item_id(item: MutableMapping) -> str:
    """Return a stable identifier for a persisted queue item."""
    raw = str(item.get(QUEUE_ITEM_ID_KEY, "")).strip()
    if not raw:
        raw = uuid.uuid4().hex
        item[QUEUE_ITEM_ID_KEY] = raw
    return raw


def ensure_queue_item_ids(items: Iterable[MutableMapping]) -> None:
    for item in items:
        if isinstance(item, MutableMapping):
            ensure_queue_item_id(item)


def queue_item_by_id(items: Iterable[MutableMapping], item_id: str) -> MutableMapping | None:
    wanted = str(item_id or "")
    for item in items:
        if isinstance(item, MutableMapping) and ensure_queue_item_id(item) == wanted:
            return item
    return None


def queue_index_by_id(items: Iterable[MutableMapping], item_id: str) -> int:
    wanted = str(item_id or "")
    for index, item in enumerate(items):
        if isinstance(item, MutableMapping) and ensure_queue_item_id(item) == wanted:
            return index
    return -1


@dataclass
class EventBudget:
    """Bound one GUI event-poll turn by both item count and wall time."""

    max_items: int = 200
    max_seconds: float = 0.012
    clock: object = time.perf_counter
    processed: int = 0
    started: float = field(init=False)

    def __post_init__(self) -> None:
        self.max_items = max(1, int(self.max_items))
        self.max_seconds = max(0.001, float(self.max_seconds))
        self.started = self.clock()

    def allow_next(self) -> bool:
        return self.processed < self.max_items and (self.clock() - self.started) < self.max_seconds

    def record(self) -> None:
        self.processed += 1
