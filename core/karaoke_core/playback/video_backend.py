"""Backend phát video MP4/MKV qua mpv — dùng cho cả bài local lẫn bài YouTube.

Lời bài hát đã cháy sẵn trong video nên backend này không render phụ đề gì cả.
Giai đoạn 3 sẽ thêm `MidiBackend` dùng chung cùng một `MpvClient`.
"""

from __future__ import annotations

import logging
import time

from ..models import Capabilities, PlayableMedia, PlayerState, SongRef
from .engine import PlaybackEngine
from .mpv_client import MpvClient

log = logging.getLogger(__name__)

_POSITION_THROTTLE = 0.2
"""Chỉ broadcast vị trí 5 lần/giây. Phát mỗi frame ra WebSocket là cách chắc chắn
nhất để làm đơ app điện thoại."""


class VideoBackend(PlaybackEngine):
    def __init__(self, mpv: MpvClient, cfg, on_event) -> None:
        self._mpv = mpv
        self._cfg = cfg
        self._on_event = on_event
        self._state = PlayerState.IDLE
        self._song: SongRef | None = None
        self._position = 0.0
        self._duration = 0.0
        self._volume = cfg.volume
        self._muted = False
        self._pitch = 0
        self._tempo = 1.0
        self._last_emit = 0.0
        self._pitch_supported: bool | None = None

    # ------------------------------------------------------------------ vòng đời

    async def load(self, song: SongRef, media: PlayableMedia | None = None) -> None:
        self._song = song
        self._state = PlayerState.LOADING
        self._position = 0.0
        self._duration = float(song.duration or 0)
        self._emit("state_changed")

        if media is None or not self._mpv.available:
            # Không có mpv (máy phát triển / VM chưa cài): giữ state hợp lệ để UI
            # vẫn test được, thay vì ném lỗi làm sập core.
            log.info("che do khong co player — bo qua loadfile cho %s", song.title)
            self._state = PlayerState.PLAYING
            self._emit("media_ready")
            return

        await self._mpv.loadfile(media.url)
        await self._apply_pitch()
        await self._mpv.set_property("speed", self._tempo)
        self._state = PlayerState.PLAYING
        self._emit("media_ready")

    async def play(self) -> None:
        if self._mpv.available:
            await self._mpv.set_property("pause", False)
        self._state = PlayerState.PLAYING
        self._emit("state_changed")

    async def pause(self) -> None:
        if self._mpv.available:
            await self._mpv.set_property("pause", True)
        self._state = PlayerState.PAUSED
        self._emit("state_changed")

    async def stop(self) -> None:
        if self._mpv.available:
            await self._mpv.command("stop")
        self._state = PlayerState.IDLE
        self._song = None
        self._position = self._duration = 0.0
        self._emit("state_changed")

    async def seek(self, seconds: float, mode: str = "absolute") -> None:
        if self._mpv.available:
            await self._mpv.command("seek", seconds, mode)
        if mode == "absolute":
            self._position = max(0.0, seconds)

    # ------------------------------------------------------------------ âm thanh

    async def set_volume(self, value: int) -> None:
        self._volume = max(0, min(self._cfg.volume_max, int(value)))
        if self._mpv.available:
            await self._mpv.set_property("volume", self._volume)
        self._emit("volume_changed")

    async def set_mute(self, muted: bool) -> None:
        self._muted = bool(muted)
        if self._mpv.available:
            await self._mpv.set_property("mute", self._muted)
        self._emit("volume_changed")

    async def set_pitch(self, semitones: int) -> None:
        lo, hi = self.capabilities.pitch_range
        self._pitch = max(lo, min(hi, int(semitones)))
        await self._apply_pitch()
        self._emit("pitch_changed")

    async def _apply_pitch(self) -> None:
        """Đổi tông cho video = pitch-shift cả bản mix bằng rubberband.

        Luôn có artifact (nhoè transient, 'phasey' ở cymbal) — đầu karaoke thương
        mại cũng vậy. Vì thế giới hạn ±4 nửa cung. Nếu bản ffmpeg không có
        librubberband thì bỏ qua và UI làm mờ nút đổi tông.
        """
        if not self._mpv.available:
            return
        if self._pitch == 0:
            await self._mpv.set_property("af", "")
            return
        ratio = 2 ** (self._pitch / 12)
        try:
            await self._mpv.set_property("af", f"lavfi=[rubberband=pitch={ratio:.6f}]")
            self._pitch_supported = True
        except RuntimeError as exc:
            self._pitch_supported = False
            self._pitch = 0
            log.warning("khong doi tong duoc (thieu librubberband?): %s", exc)
            self._emit("error", {"code": "PITCH_UNSUPPORTED", "recoverable": True})

    async def set_tempo(self, ratio: float) -> None:
        lo, hi = self.capabilities.tempo_range
        self._tempo = max(lo, min(hi, float(ratio)))
        if self._mpv.available:
            # audio-pitch-correction=yes -> mpv tự chèn scaletempo2, cao độ giữ nguyên
            await self._mpv.set_property("speed", self._tempo)
        self._emit("tempo_changed")

    # ------------------------------------------------------------------ state

    @property
    def position(self) -> float:
        return self._position

    @property
    def duration(self) -> float:
        return self._duration

    @property
    def state(self) -> PlayerState:
        return self._state

    @property
    def capabilities(self) -> Capabilities:
        r = self._cfg.video_pitch_range
        can_pitch = self._pitch_supported is not False
        return Capabilities(
            can_pitch=can_pitch,
            pitch_range=(-r, r) if can_pitch else (0, 0),
            pitch_quality="dsp" if can_pitch else "none",
            can_tempo=True,
            tempo_range=(0.85, 1.15),
            can_vocal_guide=False,
            has_lyrics=False,  # lời cháy sẵn trong video
        )

    def snapshot(self) -> dict:
        return {
            "state": self._state.value,
            "song": self._song.to_dict() if self._song else None,
            "position": round(self._position, 2),
            "duration": round(self._duration, 2),
            "volume": self._volume,
            "muted": self._muted,
            "pitch": self._pitch,
            "tempo": self._tempo,
            "capabilities": self.capabilities.to_dict(),
        }

    # ------------------------------------------------------------------ mpv events

    def on_mpv_property(self, name: str, value) -> None:
        if name == "time-pos" and isinstance(value, (int, float)):
            self._position = float(value)
            now = time.monotonic()
            if now - self._last_emit >= _POSITION_THROTTLE:
                self._last_emit = now
                self._emit("position_changed")
        elif name == "duration" and isinstance(value, (int, float)):
            self._duration = float(value)
            self._emit("duration_changed")
        elif name == "eof-reached" and value:
            self._state = PlayerState.ENDED
            self._emit("ended")
        elif name == "pause" and isinstance(value, bool):
            if self._state in (PlayerState.PLAYING, PlayerState.PAUSED):
                self._state = PlayerState.PAUSED if value else PlayerState.PLAYING
                self._emit("state_changed")

    def _emit(self, event: str, extra: dict | None = None) -> None:
        payload = self.snapshot()
        if extra:
            payload.update(extra)
        self._on_event(event, payload)
