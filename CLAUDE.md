# CLAUDE.md — KaraokeBooth

Dự án karaoke một máy cố định: AEWIN MB-8390 chạy Debian 13, hai màn (ELO cảm ứng + TV),
tiếng ra Yamaha MG10XU. Khách chọn bài bằng điện thoại qua WiFi nội bộ.

Xem chi tiết kiến trúc và lộ trình ở [docs/PLAN.md](docs/PLAN.md).

---

## Máy thật (MB-8390)

| | |
|---|---|
| IP | `192.168.1.126` |
| SSH | `ssh bo@192.168.1.126` (pass: `bo`) |
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
| Audio codec | Realtek ALC886 | Card index 1; chỉ có 2 port: `analog-output-lineout` (rear, **đang dùng**) + `analog-output-headphones` (front, không dùng) |
| Màn hình | ELO cảm ứng (DP-3, 1920×1080) + TV (HDMI, 1920×1080) | Dual monitor hoặc single tùy cắm |
| Hai màn hình | Dải 2560×1080 (dual) hoặc 1920×1080 (single) | session.sh detect tự động |

**Audio routing (ALC886):**
- Jack xanh lá **rear IO** (mặt sau máy, nối Yamaha MG10XU) = NID `0x14` = ALSA control
  "Front" = PipeWire port `analog-output-lineout`. Đây là port **đang dùng thật**.
- Jack xanh lá **mặt trước case** = NID `0x1b` = ALSA control "Headphone" = PipeWire port
  `analog-output-headphones`. Không dùng — không có gì cắm vào đó trong lắp đặt thật.
- Đổi port: `pactl set-sink-port alsa_output.pci-0000_00_14.2.analog-stereo analog-output-lineout`
- `pactl` đến từ `pulseaudio-utils` (cần cài, đã vào provision.sh)
- WirePlumber **không lưu state** qua reboot trên máy này (`~/.local/state/wireplumber/`
  luôn rỗng) — mọi thứ set bằng `wpctl`/`pactl` chỉ có hiệu lực tới lần khởi động sau.
  Volume mặc định và port default đã được ép cứng qua config, xem gotcha #2 và #8.

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
- [x] mpv phát video lên TV (screen=1), audio qua PipeWire → ALC886 → jack 3.5mm rear IO (lineout)
- [x] Audio 3.5mm hoạt động thật sự và ổn định qua restart — xem gotcha #8–11
      (pin widget, Auto-Mute Mode, suspend-khi-idle, thứ tự lệnh fix_alsa.sh)
- [x] WirePlumber volume mặc định ép 100% + port `analog-output-lineout` — xem gotcha #2
- [x] QR app tự phát hiện IP thật (DHCP) thay vì hardcode `ap_address` — `qr_util.detect_app_ip()`
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
# fix_alsa.sh, WirePlumber volume-default, và karaoke-audio-pinfix.service
# (fix pin widget ALC886 — gotcha #8) đều đã cài + enable trong provision.sh
```

**Gói bắt buộc phải có trên server** (đã vào provision.sh):
- `pulseaudio-utils` — cần cho `pactl` (đổi WirePlumber port)
- `mesa-va-drivers` — VAAPI backend cho AMD (H264 hardware decode)
- `mesa-vdpau-drivers` — VDPAU backend cho AMD (libvdpau_r600.so)
- `alsa-tools` — cần cho `hda-verb` (fix pin widget ALC886, xem gotcha #8)

---

## Systemd services

**User `karaoke`** (`~/.config/systemd/user/`):

| Service | Mô tả | Restart |
|---|---|---|
| `karaoke-core` | FastAPI + mpv | always, TimeoutStopSec=10 |
| `karaoke-dsp` | PipeWire DSP filter-chain | always |
| `karaoke-ui` | PySide6 kiosk UI (chưa dùng) | always |

`ExecStartPost=/bin/bash -c "/etc/karaoke/fix_alsa.sh &"` — unmute ALSA sau boot (background, không block stop).

Kiểm tra: `sudo -u karaoke XDG_RUNTIME_DIR=/run/user/1001 systemctl --user status karaoke-core`

**System (`/etc/systemd/system/`), chạy bằng root, độc lập user session:**

| Service | Mô tả |
|---|---|
| `karaoke-audio-pinfix` | oneshot, `WantedBy=sysinit.target` — fix pin widget ALC886, xem gotcha #8 |

---

## Gotchas hay gặp

1. **mpv IPC socket** — chỉ có thể read nếu không có process nào khác đang hold connection.
   Dùng `socat -t 3 - UNIX-CONNECT:/run/karaoke/mpv.sock` với timeout đủ.

2. **WirePlumber không lưu state** trên máy này — `~/.local/state/wireplumber/` luôn rỗng,
   nên `wpctl set-volume 1.0` chạy tay chỉ có tác dụng tới lần route tiếp theo (vài giây).
   Debian mặc định `device.routes.default-sink-volume = 0.064` (cubic = 40%, "safe listening").
   Fix: `/etc/wireplumber/wireplumber.conf.d/50-volume-default.conf` ép default = 1.0
   (xem `deploy/pipewire/50-volume-default.conf`). Đừng chạy đua với WP bằng loop `wpctl` —
   sửa default là xong, không phải chạy lại lệnh sau mỗi lần route apply.

3. **ALC886 sink index** — có thể thay đổi sau reboot. Dùng `pactl list sinks` để tìm index
   đúng trước khi gọi `set-sink-port`.

4. **`video-sync=display-resample`** — ngốn CPU 91.7% trên AMD Trinity. Phải dùng `audio`.

5. **VAAPI H264High** — hoạt động qua `r600_drv_video.so`. Cần `DISPLAY=:0` và
   `XDG_RUNTIME_DIR=/run/user/1001` được set khi kiểm tra `vainfo`.

6. **`StartLimitIntervalSec=0`** trên mọi service — không đặt thì systemd bỏ cuộc sau 5 lần
   crash trong 10s và máy chết hẳn giữa buổi hát.

7. **fix_alsa.sh** phải chạy background trong ExecStartPost, không thì block stop phase.

8. **ALC886 "SKU not ready 0x00000100"** (xem `dmesg`) — BIOS AEWIN MB-8390 không cung cấp
   đủ pin-config cho codec, nên driver `snd-hda-intel` không tự bật đúng pin widget cho
   node `0x14` (Line Out at Ext Rear = jack xanh **rear IO**, port `analog-output-lineout`).
   Triệu chứng: ALSA/PipeWire mixer báo "Front"/"lineout" **on, 100%**, PCM báo `RUNNING`,
   mpv/wpctl không báo lỗi gì — nhưng **im lặng hoàn toàn** ở jack, vì đó chỉ là amp gain,
   còn thanh ghi Pin-ctls thật của node (bật/tắt driver ra chân pin) vẫn là `0x00` (OUT
   chưa bật). Kiểm tra: `cat /proc/asound/card1/codec#0 | grep -A18 'Node 0x14 \['` →
   `Pin-ctls: 0x00` là dấu hiệu chắc chắn. Node `0x1b` (Headphone, jack mặt trước, không
   dùng) không bị lỗi này — driver tự bật đúng `Pin-ctls: 0xc0`.
   **Fix**: `hda-verb /dev/snd/hwC1D0 0x14 SET_PIN_WIDGET_CONTROL 0x40` (cần `alsa-tools`).
   Đây là thanh ghi runtime, **RESET mỗi khi mpv mở lại thiết bị** (không chỉ mất sau
   reboot) — restart `karaoke-core` cũng đủ làm mất tiếng lại. Chạy 1 lần lúc boot bằng
   `karaoke-audio-pinfix.service` KHÔNG đủ; `fix_alsa.sh` (chạy mỗi lần karaoke-core start)
   phải tự áp lại qua `sudo -n` (rule hẹp `/etc/sudoers.d/karaoke-hda-pinfix`, đúng 1 lệnh —
   karaoke user không có sudo chung). Nếu sau này đổi board/case và jack không ra tiếng
   nữa dù mọi thứ ALSA báo "on", **luôn nghi ngờ pin widget trước**, đừng chỉ nhìn mixer
   volume.

9. **ALC886 "Auto-Mute Mode: Enabled"** tự mute lại "Front" (node 0x14) dựa vào jack-sense
   unsolicited event của node Headphone (0x1b) — hoàn toàn độc lập với WirePlumber/hda-verb,
   xảy ra ở tầng driver/codec. Không cần trên máy cố định chỉ có 1 kết nối vật lý duy nhất
   → tắt hẳn: `amixer -c 1 sset 'Auto-Mute Mode' Disabled`.

10. **WirePlumber tự suspend + mute sink khi idle** (không có stream active) — đây là hành
    vi tiết kiệm điện BÌNH THƯỜNG của WP, dễ nhầm là "mất tiếng" khi kiểm tra lúc mpv đang
    `--idle` giữa 2 bài. `session.suspend-timeout-seconds = 0` trong `51-karaoke-usb.conf`
    trước đây chỉ khớp `device.name = "~alsa_card.usb-.*"` (mic-fx) — KHÔNG khớp ALC886
    onboard (`alsa_output.pci-...analog-stereo`), nên sink nhạc chính vẫn bị suspend/mute
    sau vài giây im lặng. Test: unmute tay rồi theo dõi `wpctl get-volume` vài giây — nếu tự
    lên lại `[MUTED]` dù **không** đang phát gì, đây chính là nguyên nhân (khác gotcha #9 —
    kiểm tra "Auto-Mute Mode" trước, đây là bước 2 nếu #9 đã Disabled mà vẫn mute idle).
    Fix: thêm rule riêng cho node ALC886 với `session.suspend-timeout-seconds = 0` (xem
    `deploy/pipewire/51-karaoke-usb.conf`) — KHÔNG gộp chung `api.alsa.period-size`/`periods`
    của rule USB, giá trị đó tune riêng cho mic, không áp dụng ở đây.

11. **Thứ tự lệnh trong fix_alsa.sh quan trọng**: đổi port (`pactl set-sink-port`) PHẢI
    chạy TRƯỚC `wpctl set-mute`/`set-volume`. Làm ngược lại, WirePlumber activate route mới
    sẽ reset lại mute state, xoá luôn unmute vừa gọi trước đó.
