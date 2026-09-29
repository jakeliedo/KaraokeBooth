"""Event bus — mọi thay đổi state được broadcast tới tất cả client đang mở.

Mỗi message mang một `seq` tăng dần. Client phát hiện mất gói (seq nhảy cóc) thì
gọi GET /api/state để lấy lại toàn bộ, thay vì cố ghép state từ các delta.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

log = logging.getLogger(__name__)

_MAX_PENDING = 64
"""Client chậm hơn ngần này message sẽ bị ngắt — thà ngắt rồi nó tự kết nối lại
còn hơn để hàng đợi phình ra vô hạn."""


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._seq = 0

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=_MAX_PENDING)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def emit(self, event: str, payload: Any = None) -> None:
        """Gửi không chặn. Gọi được từ bất kỳ coroutine nào trong event loop."""
        self._seq += 1
        message = {"seq": self._seq, "event": event, "data": payload}
        dead = []
        for q in self._subscribers:
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                log.warning("client quá chậm, ngắt kết nối (event=%s)", event)
                dead.append(q)
        for q in dead:
            self._subscribers.discard(q)
