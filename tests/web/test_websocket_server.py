from __future__ import annotations

import asyncio

from bot.web.websocket_server import WebSocketBroadcaster


class FakeWebSocket:
    def __init__(self, fail: bool = False) -> None:
        self.accepted = False
        self.sent: list[dict[str, object]] = []
        self.closed = False
        self.fail = fail

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, data: dict[str, object]) -> None:
        if self.fail:
            raise RuntimeError("closed")
        self.sent.append(data)

    async def close(self) -> None:
        self.closed = True


def test_broadcaster_sends_recent_buffer_on_connect() -> None:
    async def run() -> None:
        broadcaster = WebSocketBroadcaster(buffer_size=2)
        await broadcaster.publish("price", {"asset": "BTC", "price": 100})
        ws = FakeWebSocket()

        await broadcaster.connect(ws)
        await broadcaster.publish("status", {"ok": True})

        assert ws.accepted is True
        assert [event["type"] for event in ws.sent] == ["price", "status"]

    asyncio.run(run())


def test_broadcaster_removes_stale_connections() -> None:
    async def run() -> None:
        broadcaster = WebSocketBroadcaster()
        ws = FakeWebSocket(fail=True)
        await broadcaster.connect(ws)

        await broadcaster.publish("event", {})

        assert ws.closed is True
        assert ws not in broadcaster.active

    asyncio.run(run())
