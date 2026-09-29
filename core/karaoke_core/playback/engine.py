"""Giao diện trừu tượng của bộ phát nhạc.

Định nghĩa ngay từ Giai đoạn 1 dù mới có một backend (video), để Giai đoạn 3 cắm
`MidiBackend` vào mà không phải sửa tầng trên. Tầng UI **không bao giờ** biết mình
đang điều khiển backend nào — nó gọi `set_pitch(+3)` rồi đọc `capabilities` để
bật/tắt/giới hạn nút.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Capabilities, PlayerState, SongRef


class PlaybackEngine(ABC):
    # --- vòng đời ---------------------------------------------------------

    @abstractmethod
    async def load(self, song: SongRef) -> None:
        """Chuẩn bị bài (tải file, parse lời, sinh .ass) nhưng CHƯA phát."""

    @abstractmethod
    async def play(self) -> None: ...

    @abstractmethod
    async def pause(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    async def toggle_pause(self) -> None:
        if self.state is PlayerState.PLAYING:
            await self.pause()
        else:
            await self.play()

    # --- vị trí -----------------------------------------------------------

    @abstractmethod
    async def seek(self, seconds: float, mode: str = "absolute") -> None: ...

    async def restart(self) -> None:
        """Hát lại từ đầu."""
        await self.seek(0)
        await self.play()

    @property
    @abstractmethod
    def position(self) -> float: ...

    @property
    @abstractmethod
    def duration(self) -> float: ...

    @property
    @abstractmethod
    def state(self) -> PlayerState: ...

    # --- âm thanh ---------------------------------------------------------

    @abstractmethod
    async def set_volume(self, value: int) -> None: ...

    @abstractmethod
    async def set_mute(self, muted: bool) -> None: ...

    @abstractmethod
    async def set_pitch(self, semitones: int) -> None:
        """Đổi tông. Giá trị bị kẹp theo `capabilities.pitch_range`."""

    @abstractmethod
    async def set_tempo(self, ratio: float) -> None: ...

    async def set_vocal_guide(self, enabled: bool) -> None:
        """Bật/tắt giọng hát mẫu — chỉ bài MIDI làm được. Mặc định bỏ qua."""
        return None

    # --- dữ liệu ----------------------------------------------------------

    @property
    @abstractmethod
    def capabilities(self) -> Capabilities: ...

    @abstractmethod
    def snapshot(self) -> dict:
        """State hiện tại để trả về API và broadcast qua WebSocket."""
