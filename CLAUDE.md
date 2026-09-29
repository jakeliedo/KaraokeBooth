# CLAUDE.md — KaraokeBooth

Dự án karaoke một máy cố định: AEWIN MB-8390 chạy Debian 13, hai màn (ELO cảm ứng + TV),
tiếng ra Yamaha MG10XU. Khách chọn bài bằng điện thoại qua WiFi nội bộ.

Xem chi tiết kiến trúc và lộ trình ở [docs/PLAN.md](docs/PLAN.md).

---

## Máy thật (MB-8390)

| | |
|---|---|
| IP | `192.168.1.127` |
| SSH | `ssh bo@192.168.1.127` (pass: `bo`) |
| User karaoke | `sudo -u karaoke` hoặc `sudo -i -u karaoke` |
| XDG_RUNTIME_DIR | `/run/user/1001` |
| DBUS_SESSION_BUS_ADDRESS | `unix:path=/run/user/1001/bus` |
| Config | `/etc/karaoke/config.toml` |
| App | `/opt/karaoke/` (deploy từ repo) |
| Data/cache | `/data/` (SSD riêng) |
| mpv IPC socket | `/run/karaoke/mpv.sock` |

Restart service: `sudo -u karaoke XDG_RUNTIME_DIR=/run/user/1001 systemctl --user restart karaoke-core`

Deploy code mới (từ Windows):
```python
import paramiko, io
client = paramiko.SSHClient(); client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('192.168.1.127', username='bo', password='bo')
sftp = client.open_sftp()
sftp.putfo(open('path/to/file', 'rb'), '/tmp/file.py')
client.exec_command('echo bo | sudo -S cp /tmp/file.py /opt/karaoke/path/to/file.py')
```

---

## Phần cứng MB-8390 — những điểm quan trọng

| Thành phần | Chi tiết | Ghi chú |
|---|---|---|
| GPU | AMD Trinity 2 Radeon HD 7520G | Driver: `radeon` (VLIW4, không phải GCN) |
| Audio codec | Realtek ALC886 | Card index 1; chỉ có 2 port: `analog-output-lineout` (rear) + `analog-output-headphones` (front) |
| Màn hình | ELO cảm ứng (DP-3, 1920×1080) + TV (HDMI, 1920×1080) | Dual monitor hoặc single tùy cắm |
| Hai màn hình | Dải 2560×1080 (dual) hoặc 1920×1080 (single) | session.sh detect tự động |

**Audio routing (ALC886):**
- WirePlumber giữ state ở `/home/karaoke/.local/state/wireplumber/default-routes`
- Port đang dùng: `analog-output-headphones` (jack xanh phía trước case hoặc rear IO)
- Đổi port: `pactl set-sink-port <sink_id> analog-output-headphones`
- `pactl` đến từ `pulseaudio-utils` (cần cài, đã vào provision.sh)

**Video decode:**
- H264 High profile decode qua VAAPI: `mesa-va-drivers` + `r600_drv_video.so` → **hoạt động** (`VAProfileH264High: VAEntrypointVLD`)
- VDPAU backend: `mesa-vdpau-drivers` → `libvdpau_r600.so` (đã cài)
- mpv dùng `--hwdec=auto-safe` — tự chọn VAAPI nếu được
- **Không dùng `display-resample`**: CPU 91.7%. Dùng `--video-sync=audio` (CPU ~43%)

---

## Trạng thái triển khai

### Giai đoạn 0 — Kiểm chứng phần cứng ✅
Đã làm xong trên MB-8390 thật. Kết quả: GPU/audio/hai màn đều hoạt động.

### Giai đoạn 1 — YouTube + 2 màn + app điện thoại 🔄 Đang làm

**Đã hoàn thành:**
- [x] `karaoke-core` service chạy ổn định (FastAPI + uvicorn)
- [x] mpv phát video lên TV (screen=1), audio qua PipeWire → ALC886 → jack 3.5mm
- [x] WirePlumber port `analog-output-headphones` persistent qua reboot
- [x] Web UI (kiosk.html) chạy trên ELO — tìm bài, hàng chờ, điều khiển
- [x] YouTube search + download + cache → `/data/cache/`
- [x] Service restart nhanh ~8s (fix `_restart_task` cancellation)
- [x] Video không lag (`video-sync=audio` + `scale=bilinear`)
- [x] session.sh detect single/dual monitor tự động

**Còn lại trong Giai đoạn 1:**
- [ ] **Chromium kiosk trên ELO** — mở kiosk.html fullscreen trên màn cảm ứng (DP-3)
- [ ] **ELO touch input mapping** — `xinput map-to-output` trong session.sh
- [ ] **Test sau reboot** — xác nhận toàn bộ audio/video/screen survive reboot

### Giai đoạn 2, 3, 4 — Chưa làm

---

## Kiến trúc code

```
core/karaoke_core/
├── main.py          FastAPI app entry point
├── config.py        Đọc /etc/karaoke/config.toml
├── session.py       PlaybackSession — nguồn sự thật trạng thái
├── bus.py           EventBus WebSocket broadcast
├── models.py        Pydantic models
├── api/             REST routes
├── playback/
│   ├── mpv_client.py   MpvClient — quản lý tiến trình mpv, IPC socket
│   └── engine.py       PlaybackEngine
├── sources/
│   └── youtube.py      YouTubeSource — yt-dlp search + download
├── library/         SQLite WAL, FTS5 search
└── audio/           PipeWire control
```

**mpv_client.py — điểm quan trọng:**
- mpv chạy tiến trình riêng, điều khiển qua Unix socket JSON IPC
- `_restart_task` phải được cancel trong `stop()` — nếu không service treo 90s+ khi restart
- Tham số khởi động quan trọng: xem hàm `_argv()` tại [core/karaoke_core/playback/mpv_client.py](core/karaoke_core/playback/mpv_client.py)

---

## Deploy

```bash
# Trên server (từ repo đã clone)
sudo rsync -a core/ /opt/karaoke/core/
sudo rsync -a web/  /opt/karaoke/web/
sudo -u karaoke XDG_RUNTIME_DIR=/run/user/1001 systemctl --user restart karaoke-core
```

```bash
# Cài mới hoàn toàn (Debian 13 trắng)
sudo ./deploy/provision.sh
# Sau đó: sửa /etc/karaoke/config.toml (audio_device, screen)
# Cài fix_alsa.sh đã có trong provision.sh
```

**Gói bắt buộc phải có trên server** (đã vào provision.sh):
- `pulseaudio-utils` — cần cho `pactl` (đổi WirePlumber port)
- `mesa-va-drivers` — VAAPI backend cho AMD (H264 hardware decode)
- `mesa-vdpau-drivers` — VDPAU backend cho AMD (libvdpau_r600.so)

---

## Systemd services (user `karaoke`)

| Service | Mô tả | Restart |
|---|---|---|
| `karaoke-core` | FastAPI + mpv | always, TimeoutStopSec=10 |
| `karaoke-dsp` | PipeWire DSP filter-chain | always |
| `karaoke-ui` | PySide6 kiosk UI (chưa dùng) | always |

`ExecStartPost=/bin/bash -c "/etc/karaoke/fix_alsa.sh &"` — unmute ALSA sau boot (background, không block stop).

Kiểm tra: `sudo -u karaoke XDG_RUNTIME_DIR=/run/user/1001 systemctl --user status karaoke-core`

---

## Gotchas hay gặp

1. **mpv IPC socket** — chỉ có thể read nếu không có process nào khác đang hold connection.
   Dùng `socat -t 3 - UNIX-CONNECT:/run/karaoke/mpv.sock` với timeout đủ.

2. **WirePlumber state** — không ghi tay vào file JSON. Dùng `pactl set-sink-port` để đổi,
   WirePlumber tự lưu đúng format.

3. **ALC886 sink index** — có thể thay đổi sau reboot. Dùng `pactl list sinks` để tìm index
   đúng trước khi gọi `set-sink-port`.

4. **`video-sync=display-resample`** — ngốn CPU 91.7% trên AMD Trinity. Phải dùng `audio`.

5. **VAAPI H264High** — hoạt động qua `r600_drv_video.so`. Cần `DISPLAY=:0` và
   `XDG_RUNTIME_DIR=/run/user/1001` được set khi kiểm tra `vainfo`.

6. **`StartLimitIntervalSec=0`** trên mọi service — không đặt thì systemd bỏ cuộc sau 5 lần
   crash trong 10s và máy chết hẳn giữa buổi hát.

7. **fix_alsa.sh** phải chạy background trong ExecStartPost, không thì block stop phase.
