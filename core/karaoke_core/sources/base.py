"""Giao diện chung cho mọi nguồn bài hát.

Tầng trên (queue, playback, API) không bao giờ biết bài đến từ YouTube hay từ ổ
đĩa. Thêm nguồn mới (USB, NAS, dịch vụ khác) chỉ là thêm một lớp ở đây.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import PlayableMedia, SongRef, SourceKind


class SourceError(RuntimeError):
    """Nguồn không dùng được lúc này — mất mạng, yt-dlp hỏng, file biến mất."""


class SongSource(ABC):
    kind: SourceKind

    @abstractmethod
    async def search(self, query: str, limit: int) -> list[SongRef]:
        ...

    @abstractmethod
    async def resolve(self, ref: SongRef) -> PlayableMedia:
        """Trả về thứ mpv mở được. Có thể tốn thời gian (tải file) nên luôn await."""

    async def prefetch(self, ref: SongRef) -> None:
        """Tải sẵn ở nền. Mặc định không làm gì."""
        return None

    async def close(self) -> None:
        return None
