"""Kiểu dữ liệu dùng chung giữa các tầng.

Giữ ở một chỗ để API, UI và playback engine nói cùng một ngôn ngữ.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum


class PlayerState(str, Enum):
    IDLE = "idle"
    LOADING = "loading"
    PLAYING = "playing"
    PAUSED = "paused"
    ENDED = "ended"
    ERROR = "error"


class SourceKind(str, Enum):
    LOCAL = "local"
    YOUTUBE = "youtube"


@dataclass(slots=True)
class SongRef:
    """Một bài hát ở dạng tham chiếu — chưa chắc đã có file trên đĩa."""

    source: SourceKind
    source_id: str
    title: str
    artist: str = ""
    duration: int = 0
    thumbnail: str = ""
    channel: str = ""
    song_code: str = ""
    """Mã số 6 chữ số kiểu đầu karaoke thương mại, chỉ có ở bài local."""

    @property
    def uid(self) -> str:
        return f"{self.source.value}:{self.source_id}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["source"] = self.source.value
        d["uid"] = self.uid
        return d


@dataclass(slots=True)
class PlayableMedia:
    """Kết quả của SongSource.resolve() — thứ mpv thực sự mở được."""

    url: str
    is_local: bool
    headers: dict[str, str] = field(default_factory=dict)
    subtitle_path: str | None = None
    """Chỉ dùng cho bài MIDI ở Giai đoạn 3 (file .ass sinh động)."""


@dataclass(slots=True)
class QueueItem:
    song: SongRef
    singer: str = ""
    added_by: str = ""
    """Định danh client đã đặt bài — để khách chỉ xóa được bài của chính mình."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    added_at: float = field(default_factory=time.time)
    ready: bool = False
    """True khi đã tải xong về cache (bài YouTube) hoặc file có sẵn (bài local)."""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "song": self.song.to_dict(),
            "singer": self.singer,
            "added_by": self.added_by,
            "added_at": self.added_at,
            "ready": self.ready,
        }


@dataclass(slots=True)
class Capabilities:
    """UI đọc cái này để bật/tắt/giới hạn nút mà không cần biết backend nào đang chạy."""

    can_pitch: bool = False
    pitch_range: tuple[int, int] = (0, 0)
    pitch_quality: str = "none"
    """'lossless' (MIDI transpose) | 'dsp' (pitch-shift video) | 'none'"""
    can_tempo: bool = False
    tempo_range: tuple[float, float] = (1.0, 1.0)
    can_vocal_guide: bool = False
    has_lyrics: bool = False

    def to_dict(self) -> dict:
        return asdict(self)
