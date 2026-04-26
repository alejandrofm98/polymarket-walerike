"""In-process WebSocket broadcaster for dashboard events."""

from __future__ import annotations

import contextlib
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Deque


@dataclass(slots=True)
class DashboardEvent:
    type: str
    payload: dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class WebSocketBroadcaster:
    def __init__(self, buffer_size: int = 10) -> None:
        self.active: set[Any] = set()
        self.recent: Deque[dict[str, Any]] = deque(maxlen=buffer_size)
        self._market_tick_recent: Deque[dict[str, Any]] = deque(maxlen=3)

    async def connect(self, websocket: Any) -> None:
        await websocket.accept()
        self.active.add(websocket)
        for event in self.recent:
            if event.get("type") == "market_tick":
                continue
            await websocket.send_json(event)

    def disconnect(self, websocket: Any) -> None:
        self.active.discard(websocket)

    async def publish(self, event_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        event = DashboardEvent(event_type, payload or {})
        data = {"type": event.type, "payload": event.payload, "timestamp": event.timestamp}
        self.recent.append(data)
        if event_type == "market_tick":
            self._market_tick_recent.append(data)
        stale: list[Any] = []
        for websocket in list(self.active):
            try:
                await websocket.send_json(data)
            except Exception:  # noqa: BLE001 - stale sockets are expected
                stale.append(websocket)
        for websocket in stale:
            with contextlib.suppress(Exception):
                await websocket.close()
            self.disconnect(websocket)
        return data
