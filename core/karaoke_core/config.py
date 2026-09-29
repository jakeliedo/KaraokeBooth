"""Cấu hình — đọc từ /etc/karaoke/config.toml, có giá trị mặc định chạy được ngay.

Trên máy phát triển (không có /etc/karaoke) service vẫn khởi động bình thường với
thư mục dữ liệu tạm. Đây là ràng buộc bắt buộc: core phải chạy được cả khi thiếu
thiết bị âm thanh, thiếu mpv và thiếu SSD, nếu không sẽ không test được gì trong VM.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_PATH = Path(os.environ.get("KARAOKE_CONFIG", "/etc/karaoke/config.toml"))


def _default_data_dir() -> Path:
    for candidate in (Path("/data"), Path.home() / ".local/share/karaoke"):
        if candidate.exists() or candidate.parent.exists():
            return candidate
    return Path.cwd() / "data"


@dataclass(slots=True)
class PlayerConfig:
    mpv_binary: str = "mpv"
    ipc_socket: str = "/run/karaoke/mpv.sock"
    screen: int = 1
    """Chỉ số màn hình X11 của TV. 0 = màn cảm ứng, 1 = TV (xem session.sh)."""
    audio_device: str = "pipewire/karaoke_music"
    """Ghim tường minh. Tuyệt đối không để mpv tự chọn — nó sẽ chọn HDMI."""
    volume: int = 100
    volume_max: int = 130
    video_pitch_range: int = 4
    screen_width: int = 1920
    screen_height: int = 1080
    """Độ phân giải màn TV — dùng để render idle image đúng kích thước."""
    """Giới hạn ±4 nửa cung cho bài video. Pitch-shift một bản mix hoàn chỉnh bằng
    phase-vocoder luôn có artifact; quá ±4 là nghe rõ."""


@dataclass(slots=True)
class YouTubeConfig:
    enabled: bool = True
    search_limit: int = 20
    search_suffix: str = "karaoke"
    min_duration: int = 60
    max_duration: int = 900
    cache_ttl_hours: int = 24
    prefetch: bool = True
    """Tải nền bài vừa vào hàng chờ. Bài đang phát đọc từ file đã tải nên mạng
    chập chờn không làm giật."""
    keep_free_percent: int = 15
    """Dọn cache theo LRU khi ổ dữ liệu còn trống ít hơn ngưỡng này."""


@dataclass(slots=True)
class NetworkConfig:
    host: str = "127.0.0.1"
    port: int = 8080
    ap_address: str = "192.168.50.1"
    ap_hostname: str = "karaoke.box"
    ap_ssid: str = "KaraokeBox"
    """SSID WiFi AP phát cho khách. Dùng trong QR WIFI và màn idle."""
    ap_psk: str = ""
    """Mật khẩu WiFi. Để trống = mạng mở (không khuyến nghị trong quán)."""


@dataclass(slots=True)
class AudioConfig:
    music_sink: str = "karaoke_music"
    master_node: str = "karaoke_bus"
    mic_node: str = "karaoke_mic_fx"
    mic_through_pc: bool = False
    """False = Mức A (mic xử lý trên MG10XU). True = Mức B (mic qua audio interface).
    Xem docs/WIRING.md — quyết định sau khi đo ở Giai đoạn 0."""
    preset_dir: str = "config/presets"


@dataclass(slots=True)
class Config:
    data_dir: Path = field(default_factory=_default_data_dir)
    player: PlayerConfig = field(default_factory=PlayerConfig)
    youtube: YouTubeConfig = field(default_factory=YouTubeConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "db" / "karaoke.db"

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir / "db", self.media_dir, self.cache_dir,
                  self.data_dir / "config", self.data_dir / "log"):
            d.mkdir(parents=True, exist_ok=True)


def _merge(section: type, raw: dict) -> object:
    known = {f for f in section.__annotations__}
    return section(**{k: v for k, v in raw.items() if k in known})


def load(path: Path | None = None) -> Config:
    path = path or CONFIG_PATH
    if not path.exists():
        return Config()
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    cfg = Config()
    if "data_dir" in raw:
        cfg.data_dir = Path(raw["data_dir"])
    for key, section in (("player", PlayerConfig), ("youtube", YouTubeConfig),
                         ("network", NetworkConfig), ("audio", AudioConfig)):
        if key in raw:
            setattr(cfg, key, _merge(section, raw[key]))
    return cfg
