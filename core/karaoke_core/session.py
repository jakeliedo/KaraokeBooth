"""Session — nơi ghép hàng chờ, nguồn bài hát và bộ phát lại với nhau.

Đây là "nguồn sự thật duy nhất" mà README nói tới. Mọi client (màn cảm ứng, điện
thoại) đều thao tác lên đối tượng này qua API, rồi nhận state mới qua WebSocket.
Không client nào được giữ state riêng.
"""

from __future__ import annotations

import asyncio
import logging

from .bus import EventBus
from .models import PlayerState, QueueItem, SongRef, SourceKind
from .playback.mpv_client import MpvClient
from .playback.video_backend import VideoBackend
from .qr_util import write_idle_image
from .sources import LocalSource, SourceError, YouTubeSource

log = logging.getLogger(__name__)


class Session:
    def __init__(self, cfg, conn, bus: EventBus) -> None:
        self._cfg = cfg
        self._conn = conn
        self._bus = bus
        self._queue: list[QueueItem] = []
        self._current: QueueItem | None = None
        self._advancing = False
        self._mpv_retry: asyncio.Task | None = None

        # Ảnh hiển thị trên TV khi không có bài phát.
        # Thử /run/karaoke/ (tmpfs trên máy thật); nếu không ghi được thì dùng data_dir.
        from pathlib import Path
        self._idle_image = Path("/run/karaoke/idle.png")
        if not write_idle_image(cfg, self._idle_image):
            self._idle_image = cfg.data_dir / "idle.png"
            write_idle_image(cfg, self._idle_image)

        self.local = LocalSource(conn)
        self.youtube = YouTubeSource(conn, cfg.cache_dir, cfg.youtube)
        self.mpv = MpvClient(cfg.player, on_property=self._on_mpv_property)
        self.player = VideoBackend(self.mpv, cfg.player, self._on_player_event)

    # ------------------------------------------------------------------ vòng đời

    async def start(self) -> None:
        if not await self.mpv.start():
            # Thường là X chưa lên (core chạy trước phiên đồ họa) hoặc chưa cài mpv.
            # Không được coi đây là lỗi chết người: core vẫn phục vụ API và app điện
            # thoại, rồi tự bắt được mpv khi màn hình sẵn sàng.
            self._mpv_retry = asyncio.create_task(self._retry_mpv())

    async def _retry_mpv(self, interval: float = 5.0) -> None:
        while not self.mpv.available:
            await asyncio.sleep(interval)
            if await self.mpv.start():
                log.info("mpv da san sang sau %ss cho", interval)
                self._bus.emit("player_ready", self.snapshot())
                return

    async def close(self) -> None:
        if self._mpv_retry:
            self._mpv_retry.cancel()
        await self.youtube.close()
        await self.mpv.stop()

    # ------------------------------------------------------------------ tìm kiếm

    async def search(self, query: str, source: str, limit: int) -> dict:
        results: list[SongRef] = []
        error: str | None = None

        if source in ("local", "all"):
            results += await self.local.search(query, limit)
        if source in ("youtube", "all") and self._cfg.youtube.enabled:
            try:
                results += await self.youtube.search(query, limit)
            except SourceError as exc:
                # YouTube hỏng không được làm hỏng cả ô tìm kiếm — vẫn trả kết quả
                # local kèm thông báo để UI hiện banner.
                error = str(exc)

        return {"results": [r.to_dict() for r in results], "error": error}

    # ------------------------------------------------------------------ hàng chờ

    async def enqueue(self, song: SongRef, singer: str = "", added_by: str = "") -> QueueItem:
        item = QueueItem(song=song, singer=singer, added_by=added_by)
        self._queue.append(item)
        self._bus.emit("queue_changed", self.queue_snapshot())
        self._log_event("enqueue", f"{song.title} | {singer}")

        if song.source is SourceKind.YOUTUBE:
            asyncio.create_task(self._prefetch(item))

        if self._current is None:
            await self.play_next()
        return item

    async def _prefetch(self, item: QueueItem) -> None:
        try:
            await self.youtube.prefetch(item.song)
            item.ready = True
            self._bus.emit("queue_changed", self.queue_snapshot())
        except SourceError as exc:
            log.warning("prefetch that bai: %s", exc)

    def remove(self, item_id: str, requester: str | None = None) -> bool:
        for i, item in enumerate(self._queue):
            if item.id != item_id:
                continue
            # Khách chỉ xóa được bài của chính mình; màn cảm ứng (requester=None)
            # là quyền quản trị, xóa được tất cả.
            if requester is not None and item.added_by and item.added_by != requester:
                return False
            self._queue.pop(i)
            self._bus.emit("queue_changed", self.queue_snapshot())
            return True
        return False

    def reorder(self, item_id: str, new_index: int) -> bool:
        for i, item in enumerate(self._queue):
            if item.id == item_id:
                self._queue.pop(i)
                self._queue.insert(max(0, min(len(self._queue), new_index)), item)
                self._bus.emit("queue_changed", self.queue_snapshot())
                return True
        return False

    # ------------------------------------------------------------------ phát

    async def play_next(self) -> bool:
        """Lấy bài kế trong hàng chờ và phát.

        Bài nào không mở được (file biến mất, YouTube tải hỏng) thì **bỏ qua và đi
        tiếp**, không được để cả buổi hát dừng lại vì một bài lỗi. Dùng vòng lặp
        chứ không đệ quy để hàng chờ dài toàn bài hỏng cũng không làm tràn stack.
        """
        if self._advancing:
            return False
        self._advancing = True
        try:
            while self._queue:
                item = self._queue.pop(0)
                self._current = item
                self._bus.emit("queue_changed", self.queue_snapshot())

                source = self.youtube if item.song.source is SourceKind.YOUTUBE else self.local
                try:
                    media = await source.resolve(item.song)
                except SourceError as exc:
                    log.warning("bo qua bai khong mo duoc: %s", exc)
                    self._bus.emit("error", {"code": "RESOLVE_FAILED", "message": str(exc),
                                             "song": item.song.to_dict()})
                    self._log_event("error", f"resolve: {item.song.title}")
                    self._current = None
                    continue

                await self.player.load(item.song, media)
                self._mark_played(item.song)
                self._log_event("play", item.song.title)

                # Tải sẵn bài kế ngay khi bài này bắt đầu -> chuyển bài tức thì.
                if self._queue and self._queue[0].song.source is SourceKind.YOUTUBE:
                    asyncio.create_task(self._prefetch(self._queue[0]))
                return True

            self._current = None
            await self.player.stop()
            # Hàng chờ hết: hiện ảnh QR trên TV thay vì màn đen.
            if self.mpv.available and self._idle_image.exists():
                try:
                    await self.mpv.loadfile(str(self._idle_image))
                except Exception as exc:
                    log.debug("khong load duoc idle image: %s", exc)
            return False
        finally:
            self._advancing = False

    # ------------------------------------------------------------------ state

    def queue_snapshot(self) -> dict:
        return {
            "current": self._current.to_dict() if self._current else None,
            "items": [i.to_dict() for i in self._queue],
        }

    def snapshot(self) -> dict:
        return {"player": self.player.snapshot(), "queue": self.queue_snapshot(),
                "mpv_available": self.mpv.available}

    # ------------------------------------------------------------------ nội bộ

    def _on_mpv_property(self, name: str, value) -> None:
        self.player.on_mpv_property(name, value)

    def _on_player_event(self, event: str, payload: dict) -> None:
        self._bus.emit(event, payload)
        if event == "ended" and payload.get("state") == PlayerState.ENDED.value:
            asyncio.create_task(self.play_next())

    def _mark_played(self, song: SongRef) -> None:
        self._conn.execute(
            """UPDATE songs SET play_count = play_count + 1, last_played = unixepoch()
               WHERE uid = ?""",
            (song.uid,),
        )
        self._conn.commit()

    def _log_event(self, kind: str, detail: str) -> None:
        self._conn.execute("INSERT INTO events (kind, detail) VALUES (?,?)", (kind, detail))
        self._conn.commit()
