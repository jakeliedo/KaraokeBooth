# Hệ thống karaoke chuyên nghiệp trên Linux — MB-8390

## Context

Xây mới hoàn toàn một máy karaoke chạy Linux cho quán (1 máy, không phải sản phẩm bán ra hàng loạt). Phần cứng: mainboard công nghiệp AEWIN MB-8390, boot từ CFast 2.0 16GB, dữ liệu trên SSD riêng, 2 màn hình (1 cảm ứng làm bàn điều khiển, 1 TV chiếu video), card WiFi phát sóng nội bộ cho khách chọn bài bằng điện thoại, tiếng ra mixer Yamaha MG10XU → amply → loa.

Hiện chưa có mã nguồn nào. Quy trình làm việc: phát triển và test trong máy ảo QEMU trên PC Windows này, khi chạy được thì ghi image (gồm cả Debian) ra thẻ CFast và cắm vào MB-8390 thật.

Ưu tiên giai đoạn 1 theo yêu cầu: **chọn bài từ YouTube** (video beat, không phân biệt có vocal hay không) — phát được lên TV, chọn được từ điện thoại. Thư viện offline, mixer phần mềm và MIDI/Arirang làm ở các giai đoạn sau, nhưng kiến trúc phải chừa sẵn chỗ ngay từ đầu.

### Hai điểm cần nói rõ trước

**1. Mixer MG10XU và giới hạn thật của nó.** Cổng USB của MG10XU lấy tín hiệu từ **stereo bus** (bản trộn chính), không tách được từng kênh mic. Hệ quả: không thể đưa mic vào máy tính để xử lý rồi trả ngược về mixer — tín hiệu trả về lại nằm trên stereo bus và tạo vòng lặp phản hồi số, hú ngay. Nghĩa là **chức năng chống hú bằng phần mềm và reverb/echo mic chỉnh từ màn cảm ứng không thực hiện được nếu chỉ có MG10XU**.

Kế hoạch này vì vậy chia đường tiếng làm hai mức:
- **Mức A (mặc định, không mua thêm gì):** mic xử lý hoàn toàn trên MG10XU (D-PRE preamp, HPF, 1-knob compressor, hiệu ứng SPX reverb/echo có sẵn). Máy tính chỉ xử lý **nhạc**: EQ, âm lượng, đổi tông, đổi tempo, limiter — chỉnh được từ màn cảm ứng và điện thoại. Không có chống hú phần mềm.
- **Mức B (nâng cấp, khi muốn đúng yêu cầu ban đầu):** thêm một audio interface class-compliant 2 in/2 out (Behringer UMC204HD, ~2.5–3 triệu). Mic → interface → máy tính (DSP đầy đủ: gate, comp, EQ, de-esser, reverb, echo, notch chống hú, limiter) → line out → một kênh line-in của MG10XU. MG10XU lúc này chỉ còn làm khối trộn analog cuối. Không có vòng lặp vì máy thu từ interface, không thu từ MG10XU.

Tầng audio được thiết kế trừu tượng để chuyển từ A sang B chỉ là đổi file cấu hình + bật thêm node DSP, không phải viết lại. Giai đoạn 0 có bước đo để chốt (MG10XU có cổng insert trên kênh mono hay không quyết định có cần mua interface).

**2. YouTube.** Phát từ YouTube bằng `yt-dlp` trong môi trường kinh doanh là vùng xám về điều khoản dịch vụ, và `yt-dlp` hay hỏng khi YouTube đổi giao diện nên phải cập nhật thường xuyên. Thiết kế vì vậy **cache mọi bài đã phát xuống SSD** — vừa chạy mượt lần sau, vừa dần tự hình thành thư viện offline, vừa giảm phụ thuộc mạng.

---

## Kiến trúc tổng thể

```
┌─────────────────────┐     ┌──────────────────────┐
│  Màn cảm ứng (DP-1) │     │   TV (HDMI-1)        │
│  PySide6/QML kiosk  │     │   mpv fullscreen     │
└──────────┬──────────┘     └──────────▲───────────┘
           │ HTTP/WS                   │ JSON IPC (unix socket)
           ▼                           │
      ┌────────────────────────────────┴──────────────┐
      │  karaoke-core  (Python, FastAPI + asyncio)    │
      │  ├─ Library   : SQLite WAL + FTS5, quét SSD   │
      │  ├─ Sources   : LocalSource | YouTubeSource   │
      │  ├─ Queue     : hàng chờ, người hát, ưu tiên  │
      │  ├─ Playback  : PlaybackEngine (video/midi)   │
      │  ├─ Mixer     : MixerState + PwControl        │
      │  └─ WebSocket : đồng bộ mọi client realtime   │
      └──────┬────────────────────────────────┬───────┘
             │ HTTP/WS qua WiFi nội bộ        │ pw-cli
             ▼                                ▼
      ┌──────────────┐              ┌──────────────────────┐
      │ PWA điện     │              │ PipeWire             │
      │ thoại/tablet │              │  karaoke_music sink  │
      │ (nginx)      │              │  → EQ → limiter      │
      └──────────────┘              │  → USB out           │
                                    └──────────┬───────────┘
                                               ▼
                                    MG10XU → amply → loa
                                       ▲
                                    Mic 1/2 (xử lý trên mixer, Mức A)
```

**Nguyên tắc bất biến:** `karaoke-core` là nguồn sự thật duy nhất. Màn cảm ứng và điện thoại đều chỉ là client gọi cùng một REST API và nhận cùng một luồng WebSocket. Không có state nào sống riêng trong UI. Nhờ vậy hai màn luôn khớp nhau và thêm client mới (tablet thứ 3, remote hồng ngoại) không phải sửa gì.

---

## Quyết định kỹ thuật đã chốt

| Hạng mục | Chọn | Lý do quyết định |
|---|---|---|
| Distro | **Debian 13 trixie**, netinst không desktop | PipeWire 1.x + WirePlumber 0.5, kho plugin LV2/LADSPA đầy đủ nhất, gói không đổi phiên bản trong 2 năm |
| Hiển thị | **Xorg + openbox**, LightDM autologin | Wayland không cho client tự chọn màn hình; `--fs-screen`, `--ontop`, `xinput map-to-output` chỉ chạy đủ trên X11. Với kiosk 2 màn hình đây là lựa chọn thực dụng |
| Player | **mpv chạy tiến trình riêng, điều khiển qua JSON IPC** | mpv crash không kéo sập UI; không cần nhúng video vào widget Qt (phần khó nhất của mọi dự án loại này); vị thế giấy phép GPL sạch hơn libmpv |
| YouTube | **yt-dlp** (cài trong venv, tự cập nhật) | mpv gọi thẳng yt-dlp; đồng thời dùng để tải về cache |
| UI cảm ứng | **PySide6 + Qt Quick (QML)** | Nút to, cuộn mượt bằng ngón tay, animation GPU — QML hợp màn cảm ứng hơn Widgets |
| App điện thoại | **PWA: Vite + Svelte**, build sẵn, nginx phục vụ tĩnh | Bundle nhỏ, không cần toolchain trên máy đích |
| CSDL | **SQLite WAL + FTS5** | Một file, chịu mất điện tốt, FTS5 tìm kiếm nhanh; có `unicode61 remove_diacritics` cho tìm không dấu |
| Âm thanh | **PipeWire + WirePlumber**, filter-chain chạy **tiến trình riêng** (`pipewire -c /etc/karaoke/dsp.conf`) | Plugin crash chỉ chết tiến trình DSP, systemd restart trong 1–2s; nếu nhét vào daemon thì mất toàn bộ tiếng |
| MIDI (GĐ3) | **FluidSynth** + sinh file `.ass` cho mpv render lời | GStreamer `fluiddec` không cho lấy lyric event, không transpose theo nốt, không mute kênh hát mẫu → không dùng được cho karaoke |
| Build image | **Cài Debian vào file `.raw` 15GB dưới QEMU → chạy `provision.sh` → `bmaptool copy` ra CFast** | Quy mô 1 máy: mkosi/A-B partition/kho apt riêng là thừa. Cách này vẫn lặp lại được và đúng quy trình "test VM rồi ghi thẻ" |

---

## Cấu trúc repo

Tạo tại `C:\Users\ADMIN\karaoke` (git repo, đồng bộ sang VM/máy thật qua git hoặc rsync).

```
karaoke/
├── core/                        # gói Python karaoke_core
│   ├── main.py                  # FastAPI app + WebSocket hub
│   ├── config.py                # đọc /etc/karaoke/config.toml
│   ├── db/schema.sql  migrations/  models.py
│   ├── library/  scanner.py  search.py  metadata.py
│   ├── sources/  base.py  local.py  youtube.py      # giao diện SongSource chung
│   ├── queue/    manager.py
│   ├── playback/ engine.py  mpv_client.py  video_backend.py
│   │             midi_backend.py            # GĐ3
│   ├── lyrics/   midi_parser.py  encoding.py  ass_generator.py   # GĐ3
│   ├── audio/    pw_control.py  mixer_state.py  presets.py
│   └── api/      routes_library.py  routes_queue.py
│                 routes_player.py   routes_mixer.py  routes_admin.py
├── ui/                          # PySide6 + QML, màn cảm ứng
│   ├── app.py  client.py        # client HTTP/WS tới core
│   └── qml/  Main.qml  SearchPage.qml  QueuePage.qml
│             MixerPage.qml  SettingsPage.qml
├── web/                         # PWA điện thoại (Vite + Svelte)
│   └── src/  routes/  lib/api.ts  lib/ws.ts
├── deploy/
│   ├── provision.sh             # script cấu hình toàn bộ máy, idempotent
│   ├── build-image.sh           # QEMU install + provision + xuất .raw
│   ├── systemd/  *.service  *.target
│   ├── xorg/     10-serverflags.conf  20-intel.conf
│   ├── session/  session.sh     # xrandr + map touch + openbox + unclutter
│   ├── pipewire/ 10-karaoke-clock.conf  51-karaoke-usb.conf  dsp.conf
│   ├── network/  hostapd.conf  dnsmasq-karaoke.conf  nginx-karaoke.conf
│   └── presets/  nam.json  nu.json  bolero.json  nhac-tre.json  mc.json
├── tools/  verify-hardware.sh   # chạy trên máy thật, in bảng kiểm chứng
└── docs/   INSTALL.md  WIRING.md  TROUBLESHOOT.md
```

---

## Giai đoạn 0 — Kiểm chứng (làm trước, ~2–3 ngày)

Viết `tools/verify-hardware.sh` in ra một báo cáo; chạy trên VM trước, rồi trên MB-8390 thật. Không viết code ứng dụng trước khi chốt xong bảng này.

**Trên MG10XU (quan trọng nhất — quyết định Mức A hay B):**
```bash
cat /proc/asound/card*/stream0      # UAC1 hay UAC2, số kênh in/out thật
arecord -D hw:1,0 -f cd -d 10 test.wav && aplay test.wav
```
- Kéo fader mic lên, hát thử → nghe file thu được. Nếu nghe thấy **cả nhạc lẫn mic trộn chung** ⇒ USB out là stereo bus ⇒ xác nhận Mức A.
- Kiểm tra mặt sau MG10XU có **cổng INSERT** trên kênh 1/2 không. Có ⇒ có thể làm Mức B mà chỉ cần thêm một soundcard USB rẻ + 2 cáp insert TRS→TS. Không có ⇒ Mức B phải mua UMC204HD.
- Ghi lại chuỗi `node.name` thật: `pw-dump | jq -r '.[] | select(.info.props."media.class") | .info.props."node.name"'` — tuyệt đối không đoán tên node.

**Trên MB-8390:**
```bash
lspci -nnk | grep -A3 -E 'VGA|Ethernet|Network'   # GPU bind i915/xe? NIC? WiFi?
ls /sys/class/drm/                                 # có mấy output, tên gì
for f in /sys/class/drm/card*/card*-*/edid; do echo $f; done   # EDID để nhận diện màn
iw list | grep -A10 "Supported interface modes"    # có "* AP" không
dmesg | grep -i wdt ; ls /dev/watchdog             # hardware watchdog
hwclock --show                                     # pin RTC còn không
xinput list                                        # tên thiết bị cảm ứng
```

**Danh sách chặn (phải xanh mới đi tiếp):**

| # | Hạng mục | Nếu đỏ thì sao |
|---|---|---|
| 1 | Debian 13 boot và bind được GPU trên MB-8390 | Thêm `firmware-misc-nonfree`, `intel-media-va-driver-non-free`; cùng lắm chuyển Ubuntu 24.04 HWE |
| 2 | Hai output hiển thị hoạt động độc lập, `xrandr` gán được vị trí | Kiểm tra cáp/EDID; ép mode tĩnh qua kernel cmdline |
| 3 | `xinput map-to-output` gán đúng touch vào đúng màn | Dùng `TransformationMatrix` trong xorg.conf.d |
| 4 | Card WiFi có AP mode | Thay card MediaTek MT7921K (M.2 2230, driver mainline, AP ổn định). Tránh Intel AX2xx |
| 5 | MG10XU: xác định USB out lấy từ đâu | Quyết định Mức A hay B như trên |
| 6 | `pw-cli` đọc lệnh liên tục từ stdin | Viết daemon nhỏ dùng `libpipewire`, hoặc gọi qua `pw-dump`/`wpctl` |

**Song song, dựng VM để phát triển:**
```bash
qemu-system-x86_64 -enable-kvm -m 4096 -smp 4 -cpu host -machine q35 \
  -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE.fd \
  -drive if=pflash,format=raw,file=./OVMF_VARS.fd \
  -drive file=karaoke-os.raw,format=raw,if=virtio \
  -drive file=data-ssd.qcow2,format=qcow2,if=virtio \
  -device virtio-vga-gl,max_outputs=2 -display gtk,gl=on \
  -device qemu-xhci -device usb-tablet \
  -netdev user,id=n0,hostfwd=tcp::8080-:8080 -device virtio-net,netdev=n0
```
Dùng **một** `virtio-vga-gl` với `max_outputs=2` (một GPU, hai output — giống máy thật). Nếu khai báo hai card GPU riêng thì logic gán màn hình sẽ sai khi lên phần cứng thật. USB passthrough MG10XU vào VM (`-device usb-host,vendorid=...`) để test chuỗi audio thật; **không lấy số đo độ trễ từ VM**.

---

## Giai đoạn 1 — v1 chạy được: YouTube + 2 màn hình + app điện thoại

Mục tiêu nghiệm thu: *khách quét QR trên TV → mở app trên điện thoại → gõ tên bài → thấy kết quả YouTube → chọn → bài vào hàng chờ → phát lên TV, tiếng ra loa qua MG10XU → nhân viên điều khiển được từ màn cảm ứng.*

### 1.1 Nền hệ thống (`deploy/provision.sh`)
Script bash idempotent, chạy được nhiều lần. Các bước:
- `apt install` danh sách gói (xem phụ lục dưới), tạo user `karaoke`, `loginctl enable-linger karaoke`
- Phân vùng CFast: `ESP 512M` / `root 12G ext4` / `persist 2G` — **chừa ~1.5GB chưa cấp phát** cho wear-leveling
- SSD: `/data` với `media/ db/ log/ config/ cache/`
- fstab: `noatime` mọi nơi, `/tmp` và `/var/tmp` là tmpfs, bind `/var/log` → `/data/log`, `/data` phải có **`nofail,x-systemd.device-timeout=10`** (SSD hỏng thì máy vẫn boot và báo lỗi rõ ràng, không rơi vào emergency shell)
- Mask `apt-daily.timer`, `apt-daily-upgrade.timer`, `man-db.timer`, `e2scrub_all.timer` — chúng ghi CFast và có thể gây giật tiếng giữa buổi hát
- LightDM autologin → session `karaoke` → `session.sh`
- Kernel cmdline: `quiet loglevel=3 preempt=full threadirqs intel_idle.max_cstate=1 processor.max_cstate=1 usbcore.autosuspend=-1`
- CPU governor `performance` qua systemd oneshot

### 1.2 Kiosk hai màn hình (`deploy/session/session.sh`)
```sh
xset s off -dpms s noblank
# Nhận diện màn theo hash EDID, KHÔNG theo tên output (tên đổi giữa các lần cắm)
eval "$(karaoke-detect-displays)"     # xuất TOUCH_OUT, TV_OUT từ /persist/config/displays.json
xrandr --output "$TOUCH_OUT" --mode 1920x1080 --pos 0x0    --primary
xrandr --output "$TV_OUT"    --mode 1920x1080 --pos 1920x0
xinput map-to-output "$TOUCH_DEV" "$TOUCH_OUT"    # BẮT BUỘC, chạy SAU mỗi lần xrandr
openbox & unclutter -idle 0.5 -root &
systemctl --user start karaoke-ui.target
wait
```
Nếu quên `map-to-output`, vùng chạm sẽ trải trên desktop ảo 3840×1080 → chạm lệch một nửa. Đây là lỗi kinh điển của cấu hình 2 màn + touch. Khi chưa có `displays.json`, dùng heuristic mặc định + **nút "Đổi vai trò hai màn hình"** trên màn cài đặt.

Khóa lối thoát: `DontVTSwitch`/`DontZap` trong xorg.conf.d, mask `getty@tty2..6`, openbox `rc.xml` bỏ hết keybinding và menu chuột phải, `kernel.sysrq=0`, GRUB `timeout=0 style=hidden`.

### 1.3 `karaoke-core`
- FastAPI + uvicorn trên `127.0.0.1:8080` (nginx reverse proxy ra `0.0.0.0:80` cho điện thoại)
- SQLite `/data/db/karaoke.db`, `PRAGMA journal_mode=WAL; synchronous=NORMAL`
- WebSocket hub: mọi thay đổi state broadcast cho tất cả client. Message có `seq` để client phát hiện mất gói và gọi `GET /api/state` lấy lại toàn bộ
- REST tối thiểu cho v1:
  `GET /api/search?q=&source=youtube|local` · `GET /api/state` · `POST /api/queue` ·
  `DELETE /api/queue/{id}` · `POST /api/queue/reorder` · `POST /api/player/{play,pause,next,replay,seek}` ·
  `POST /api/mixer/music` (volume, EQ, key, tempo)
- **Chịu được không có thiết bị audio**: khởi động bình thường, hiện lỗi trên UI, tự kết nối lại khi thiết bị xuất hiện. Nếu crash khi thiếu card thì không test được gì trong VM/CI

### 1.4 `sources/` — trừu tượng nguồn bài hát
Một giao diện `SongSource` duy nhất, hai hiện thực:
```python
class SongSource(ABC):
    async def search(self, q: str, limit: int) -> list[SongRef]
    async def resolve(self, ref: SongRef) -> PlayableMedia   # trả path hoặc URL + headers
```
- `YouTubeSource`: `yt-dlp` gọi bằng **API Python trong tiến trình**, không `subprocess` mỗi lần. Tìm kiếm `ytsearch20:<query> karaoke`, lọc theo thời lượng 1–15 phút. Cache metadata vào bảng `yt_cache` (TTL 24h) để gõ lại không phải gọi mạng.
- Prefetch: khi một bài vào hàng chờ, **tải nền ngay** xuống `/data/cache/` (`nice -n 10`, `IOSchedulingClass=idle` để không gây xrun). Bài đang phát đọc từ file đã tải → không giật khi mạng chập chờn. Đã tải xong thì ghi vào bảng `library` luôn → thư viện offline tự lớn dần.
- Dọn cache theo LRU khi `/data` còn dưới 15% trống; bài được đánh dấu "giữ lại" thì không xóa.
- `yt-dlp` phải cập nhật được từ màn cài đặt (nút "Cập nhật yt-dlp") vì nó hỏng mỗi khi YouTube đổi giao diện.

### 1.5 `playback/` — mpv một instance thường trú
```
mpv --idle=yes --force-window=yes --keep-open=yes --no-config --no-terminal
    --input-ipc-server=/run/karaoke/mpv.sock
    --fullscreen --fs-screen=1 --screen=1 --ontop --no-osc --osd-level=0
    --no-input-default-bindings --input-vo-keyboard=no --cursor-autohide=always
    --vo=gpu --gpu-context=x11egl --hwdec=auto-safe --video-sync=display-resample
    --audio-device=pipewire/karaoke_music --volume=100 --volume-max=130
    --audio-pitch-correction=yes
```
`--idle --force-window --keep-open` giữ cửa sổ TV luôn tồn tại giữa các bài → **không nháy đen khi chuyển bài**; chuyển bài bằng lệnh `loadfile`. `--audio-device` phải ghim tường minh — tuyệt đối không để mpv tự chọn HDMI (nên vô hiệu hóa hẳn node HDMI audio bằng rule WirePlumber).

`MpvClient` (~200 dòng): socket unix, JSON phân tách bằng `\n`, `observe_property` cho `time-pos`/`duration`/`eof-reached`, tự khởi động lại khi mpv chết và khôi phục bài + vị trí. **Thread đọc socket không được chạm vào bất kỳ đối tượng Qt nào** — mọi event qua `Signal` với `Qt.QueuedConnection`; vi phạm gây crash ngẫu nhiên sau nhiều giờ, rất khó debug.

`PlaybackEngine` (ABC) định nghĩa ngay từ v1 dù mới có một backend, để GĐ3 cắm `MidiBackend` vào không phải sửa tầng trên:
`load / play / pause / stop / seek / restart`, `position / duration / state`,
`set_volume / set_pitch / set_tempo / set_mute`, `capabilities`, và signal
`state_changed, media_ready, position_changed (throttle 5–10Hz), ended, error, pitch_changed, tempo_changed`.

`Capabilities` cho UI biết bật/tắt nút mà không cần biết backend nào: `can_pitch, pitch_range, pitch_quality ('lossless'|'dsp'), can_tempo, tempo_range, has_lyrics`.

**Đổi tông cho video:** `af=lavfi=[rubberband=pitch=<2**(n/12)>]`. Cần kiểm chứng sớm `mpv --af=help | grep -i rubberband` và `ffmpeg -h filter=rubberband` (librubberband là GPL, phải là bản ffmpeg GPL). Giới hạn video ở **±4 nửa cung** — pitch-shift một bản mix hoàn chỉnh bằng phase-vocoder luôn có artifact, đầu karaoke thương mại cũng vậy. Nếu không có rubberband: làm mờ nút đổi tông cho bài video và ghi rõ trên UI, không phải blocker.

### 1.6 WiFi nội bộ + đường vào cho khách
- `hostapd` **5GHz kênh 36** (non-DFS). Băng 2.4GHz trong quán thường kẹt cứng, và chính USB3 của máy phát nhiễu 2.4GHz. Có tùy chọn chuyển 2.4GHz kênh 1/6/11 trong màn cài đặt cho phòng tường dày. `ap_isolate=1`, `max_num_sta=24`, `country_code=VN`
- `systemd-networkd`: `wlan0 = 192.168.50.1/24`, **`IPForward=no`** — khách không ra Internet qua máy này
- `dnsmasq`: DHCP `.50–.200`, `dhcp-option=114` (captive-portal URI), **`address=/#/192.168.50.1`** (DNS wildcard), `address=/karaoke.box/192.168.50.1`
- **Đừng dựa vào mDNS/`.local`** — Android phân giải `.local` không đáng tin. Ở đây máy *chính là* DNS server của mạng nên `karaoke.box` chắc chắn hơn avahi
- **Đường vào chính là QR trên TV**, không phải tên miền: QR1 `WIFI:S:<ssid>;T:WPA;P:<psk>;;` (quét là tự nối WiFi), QR2 `http://192.168.50.1/`
- Captive portal: nginx trả **302** cho `/generate_204`, `/gen_204`, `/hotspot-detect.html`, `/connecttest.txt`, `/ncsi.txt`. Trang portal phải là **trang tĩnh đơn giản có nút "Mở ứng dụng"** — WebView captive của iOS/Android không chạy đúng JavaScript phức tạp và WebSocket
- Cấu hình lắp đặt khuyến nghị: **Ethernet nối router quán** (để có Internet cho YouTube + đồng bộ giờ) **+ wlan0 chạy AP** cho khách. Hai interface độc lập, không cần card hỗ trợ AP+STA đồng thời

### 1.7 UI màn cảm ứng + PWA điện thoại
Màn cảm ứng (QML): Đang phát (tên bài, thời gian, nút Tạm dừng / Bài kế / Hát lại / Âm lượng / Tông) · Hàng chờ (kéo thả đổi thứ tự, xóa) · Tìm bài (bàn phím ảo, tìm không dấu) · Mixer · Cài đặt (WiFi, màn hình, cập nhật yt-dlp, xuất nhật ký).

PWA điện thoại: tìm bài → chọn → nhập tên người hát → xem hàng chờ realtime → xóa bài mình đặt. Manifest + service worker để "Thêm vào màn hình chính". Không cho điều khiển phát/dừng từ điện thoại theo mặc định (tránh khách phá bài người khác); có công tắc "chế độ tiệc" bật quyền đó.

### 1.8 systemd
```
(system)  hostapd → dnsmasq → nginx → karaoke-core.service
          karaoke-core: After=data.mount network-online.target, Restart=always, WatchdogSec=30
(user karaoke, lingering)  pipewire → wireplumber → karaoke-dsp → karaoke-player → karaoke-ui
```
`karaoke-core` là **system service** (chạy sớm, sống sót qua việc X restart); DSP/player/UI là **user service** (cần session âm thanh + đồ họa). Nếu X sập, tiếng vẫn chạy và điện thoại vẫn đặt bài được — người đang hát không bị ngắt.

**Mọi unit phải đặt `StartLimitIntervalSec=0`.** Mặc định systemd bỏ cuộc sau 5 lần restart trong 10s — máy sẽ chết hẳn giữa buổi hát. Đây là bẫy hay gặp nhất.

---

## Giai đoạn 2 — Thư viện offline + mixer phần mềm

### 2.1 Thư viện
- `library/scanner.py`: quét `/data/media` bằng `ffprobe`, trích thời lượng/độ phân giải/codec, sinh thumbnail, hash nội dung để phát hiện trùng. Chạy nền `Nice=10 IOSchedulingClass=idle`, theo dõi thay đổi bằng `inotify`
- Tìm kiếm: FTS5 với cột `title_nodiacritic` (tự sinh bằng `unicodedata.normalize('NFD')` + bỏ dấu) → gõ "em oi ha noi" ra "Em ơi Hà Nội phố". Thêm **mã số bài 6 chữ số** như đầu karaoke thương mại để khách quen thao tác cũ vẫn dùng được
- Playlist, bài yêu thích, lịch sử, thống kê bài hát nhiều nhất

### 2.2 Mixer phần mềm — Mức A (nhạc)
Chuỗi filter-chain chạy tiến trình riêng `/etc/karaoke/dsp.conf`:
```
mpv (+ fluidsynth ở GĐ3) → sink karaoke_music → music_eq (4 băng biquad builtin)
                                              → music_gain → limiter → USB out (MG10XU)
```
Dùng **node builtin `bq_*`** của filter-chain cho EQ: không phụ thuộc plugin ngoài, CPU gần bằng 0, không có latency ẩn. Limiter: `x42 dpl.lv2` hoặc `LSP Limiter`, ceiling −1.0 dBFS.

Cấu hình PipeWire bắt buộc (`51-karaoke-usb.conf`):
```
api.alsa.period-size = 256
api.alsa.periods     = 2
api.alsa.headroom    = 256
node.pause-on-idle   = false
session.suspend-timeout-seconds = 0     # BẮT BUỘC
```
Mặc định WirePlumber treo node sau 5s im lặng; khi người hát bắt đầu, thiết bị phải wake up → nghe "tách" và trễ đầu câu. Đây là lỗi hay gặp nhất khi làm karaoke trên PipeWire.

Ghim thiết bị theo `node.name`/serial USB, **không theo chỉ số card** (thứ tự đổi sau mỗi lần reboot). Vô hiệu hóa hẳn node HDMI audio để nhạc không bao giờ ra TV.

### 2.3 Điều khiển từ Python
`PwControl`: **một tiến trình `pw-cli` chạy nền, ghi lệnh vào stdin** — `subprocess.run` mỗi lần tốn 5–15ms, kéo slider sẽ tạo hàng trăm process/giây. Coalescing bằng QTimer 50ms gom mọi thay đổi slider thành một lệnh. Âm lượng đi qua `Props.volume` của node (PipeWire nội suy mượt, không click), tham số DSP đi qua `Props.params`.

`MixerState` trong core là nguồn sự thật, **không phải PipeWire** — khi `karaoke-dsp` restart sau crash, core chỉ cần đẩy lại toàn bộ state là tự khôi phục.

Preset JSON tại `/data/config/presets/`: Nam / Nữ / Bolero / Nhạc trẻ / MC (reverb=0, echo=0 — rất cần khi MC nói). Có trường `version` để migrate khi sơ đồ DSP đổi. Áp preset = **một lệnh `set-param` duy nhất** → chuyển tức thì, không nghe thấy quá độ.

### 2.4 Mức B (chỉ làm nếu quyết định đưa mic qua máy)
Thêm node `karaoke_mic_fx` vào cùng `dsp.conf`:
```
mic1: HPF(2 tầng) → Gate → De-esser → EQ4 → Comp → NotchBank(8 bq_peaking) → gain
mic2: (giống hệt)
sum → dry ─┬→ Reverb (Dragonfly Hall, dry=0/wet=100, trộn ngoài bằng node mixer)
           └→ Echo (Calf Vintage Delay — filter-chain cấm chu trình nên echo có
                    feedback PHẢI dùng plugin có feedback nội bộ, không dùng node delay builtin)
```
Gói: `calf-plugins lsp-plugins-lv2 x42-plugins zam-plugins dragonfly-reverb swh-plugins tap-plugins`. Kiểm tra trước filter-chain của Debian có hỗ trợ node type `lv2` không (`ls /usr/lib/*/spa-0.2/filter-graph/`); nếu không, toàn bộ chuỗi vẫn làm được bằng builtin + LADSPA.

**Chống hú — không hứa "nút thần kỳ", làm 4 lớp:** (1) vật lý: mic supercardioid, loa hướng ra xa mic — hiệu quả nhất và miễn phí, phải ghi vào tài liệu lắp đặt; (2) **wizard ring-out lúc lắp đặt**: tăng dần gain, phát hiện tần số ring, cắm notch Q=20 gain −8dB, lặp 6–8 lần, lưu vào preset phòng — đây là kỹ thuật chuẩn ngành PA và làm được hoàn toàn bằng builtin + Python; (3) notch động lúc chạy: nhánh phân tích đọc monitor ở quantum 1024, FFT bằng numpy, tìm đỉnh hẹp tăng đơn điệu >300ms → gán notch tạm 20–30s — chạy **ngoài đường audio**, không gây xrun; (4) master limiter + **nút PANIC to trên UI** (mute toàn bộ mic tức thì).

Ngân sách độ trễ round-trip: 12–24ms tùy interface. **Phải đo, không được đoán** — cắm cáp loopback vật lý rồi `pw-jack jack_iodelay`. Quy trình: bắt đầu quantum 256 + headroom 256, chạy 2h với `pw-top` cột ERR = 0, rồi mới thử giảm 128. *Thà 18ms mà không bao giờ xrun, còn hơn 11ms mà mỗi tối kêu "tách" vài lần.*

---

## Giai đoạn 3 — MIDI/Arirang (.mid, .kar)

Đây là phần rủi ro cao nhất và chiếm ~40% khối lượng. **Bắt đầu bằng spike, không bắt đầu bằng code.**

**Spike bắt buộc (2–3 ngày):** lấy 30–50 file `.mid`/`.kar` Arirang/California thật, dump toàn bộ meta-event `0x01`/`0x05` ra hex. Hai câu hỏi phải trả lời trước khi viết parser:
1. Lời nằm ở Lyric (0x05) hay Text (0x01) kiểu `.kar`? Quy ước ngắt dòng có đúng là `\` (sang trang) và `/` (xuống dòng) không?
2. Bảng mã thực tế là gì — nghi ngờ mạnh **VNI-Windows** (đời mới) và **TCVN3/ABC** (đời cũ)?

**Parser** (`lyrics/midi_parser.py`): dùng **mido** (`python3-mido`), đọc với `charset='latin1'` để **giữ nguyên byte gốc** cho khâu chuyển bảng mã. Không dùng `pretty_midi` (bỏ qua Text 0x01 → mất hết file .kar) hay `music21` (quá nặng). Tempo map phải **gộp từ mọi track** rồi sort theo absolute tick — tempo event có thể nằm ở bất kỳ track nào. Thang fallback 3 tầng: mido → parser SMF tự viết (~150 dòng, chịu được file phi chuẩn) → **phát nhạc không hiện lời**. Không bao giờ để exception thoát ra khỏi backend; file lỗi đưa vào bảng `quarantine`.

**Bảng mã** (`lyrics/encoding.py`): Python stdlib **không có** codec cho TCVN3/VNI/VPS/VISCII → phải nhúng bảng ánh xạ tự viết, và **kiểm thử từng ô** bằng file có đủ 134 chữ cái tiếng Việt. Thuật toán: thử lần lượt các codec ứng viên → `NFC normalize` → chấm điểm (tỉ lệ ký tự tiếng Việt hợp lệ +40, tỉ lệ token là âm tiết Việt hợp lệ +40 dùng từ điển ~7000 âm tiết đóng gói sẵn, tần suất từ phổ biến `anh/em/yêu/tình/người/không/đời/mưa/nhớ` +15, có ký tự điều khiển −50) → chọn điểm cao nhất. **Suy luận theo cụm**: file cùng thư mục gần như luôn cùng bảng mã, ≥80% khớp thì áp cho cả thư mục. Kèm màn "Sửa bảng mã" có preview 4 dòng đầu + nút "Áp cho cả thư mục", và nút "Lỗi font?" xoay vòng codec ngay lúc đang hát.

**Render lời**: **sinh file `.ass` hoàn chỉnh lúc nạp bài, cho mpv/libass render** — không vẽ bằng Qt. Ba lý do: (a) bài MP4 vốn đã có lời cháy sẵn trong video, không đáng gánh rủi ro compositing chỉ để phục vụ MIDI; (b) với MIDI ta biết toàn bộ timing ngay lúc nạp nên sinh file tĩnh là khả thi 100%; (c) tách lời khỏi runtime Python → GC pause không làm giật lời. Dùng tag `\kf` (quét mượt, phân giải 10ms), hai dòng luân phiên `\pos(960,820)`/`\pos(960,930)`, mỗi dòng hiện sớm 2.0s. **Nhớ: trong ASS chữ CHƯA hát dùng `SecondaryColour`, chữ ĐÃ hát dùng `PrimaryColour`** — ngược với trực giác. Ghi file ra `/run/karaoke/` (tmpfs). Font: `Be Vietnam Pro` (OFL) hoặc `fonts-noto-core`, cài system-wide để fontconfig thấy.

**Video nền:** chuẩn bị bộ nền **dài ≥ 8 phút**, đặt `keep-open=yes`, và **tuyệt đối không bật `loop-file`** khi có phụ đề — loop sẽ reset `time-pos` về 0 và phá hỏng toàn bộ timeline lời.

**Đồng bộ lời–nhạc < 50ms:** đo một lần hằng `AUDIO_LATENCY_MS` (quay video 240fps màn TV + mic để đối chiếu), cộng vào offset; thêm vòng hiệu chỉnh trôi clock chạy 2s/lần: `delta = fluid_position - mpv_time_pos`, nếu lệch >15ms thì set `sub-delay`. Thêm slider "Lệch lời" ±300ms bước 10ms lưu theo từng bài — mọi đầu karaoke thương mại đều có, không nên bỏ.

**Đổi tông MIDI:** `fluid_synth_activate_key_tuning` — lossless, không artifact, đổi tức thì, **bỏ kênh 9 (trống)**. pyFluidSynth có thể chưa wrap hàm này; nó vốn là wrapper ctypes nên gọi thẳng `_fl.fluid_synth_*` được. Đổi tempo: `fluid_player_set_tempo(..., FLUID_PLAYER_TEMPO_INTERNAL, ratio)` — không ảnh hưởng cao độ; khi đổi tempo phải **sinh lại file .ass** (chia mọi mốc cho `ratio`).

**Tắt giọng hát mẫu:** dò kênh giai điệu bằng track name (`MELODY/VOCAL/GIAI DIEU/HAT MAU`) và bằng **tương quan thời gian** — kênh có tỉ lệ note-on rơi vào ±80ms quanh mốc âm tiết cao nhất chính là kênh giai điệu. Kỹ thuật này cũng dùng để căn lại timing khi lyric event bị lệch hàng loạt.

**Soundfont:** `fluid-soundfont-gm` (gói Debian, ~141MB) làm mặc định, cho phép override theo từng bài trong DB. Đặt **`synth.midi-bank-select = gs`** — file karaoke VN hay dùng Bank Select theo chuẩn Roland GS; nếu soundfont chỉ có bank 0 thì nhạc cụ sẽ mất tiếng hoặc ra sai. Nghe kiểm tra: Piano(0), Nylon Guitar(24), Strings(48/49), Flute(73)/Pan Flute(75)/Shakuhachi(77) — bản phối VN hay dùng để giả sáo/đàn bầu, Brass(61), trống bank 128. `synth.gain = 0.6` (mặc định 0.2 quá nhỏ, nhưng đừng vượt 1.0 — FluidSynth không có limiter), `polyphony = 256`, `sample-rate = 48000` khớp PipeWire.

---

## Giai đoạn 4 — Đóng gói và vận hành

- `deploy/build-image.sh`: cài Debian vào `karaoke-os.raw` 15GB dưới QEMU → chạy `provision.sh` → `git clone` mã nguồn vào `/opt/karaoke` → thu nhỏ + `bmaptool copy` ra CFast (nhanh hơn `dd` ~3 lần và ít hao CFast hơn)
- **First-boot** (`ConditionPathExists=!/persist/.provisioned`): sinh `machine-id` mới, sinh SSH host key, sinh SSID `KARAOKE-<4 ký tự cuối MAC>` + PSK ngẫu nhiên lưu `/persist`, phát hiện và khởi tạo SSD nếu trống
- **Watchdog ba tầng:** (1) `WatchdogSec=30` + `sd_notify("WATCHDOG=1")` mỗi 10s từ trong event loop asyncio — bắt được treo deadlock mà `Restart=always` không bắt được; (2) hardware `RuntimeWatchdogSec=60` (cần `iTCO_wdt`, đã kiểm ở GĐ0); (3) **watchdog nghiệp vụ**: core tự kiểm tra node `karaoke_bus` còn tồn tại không, mpv IPC còn trả lời không, `/data` còn ghi được không → tự restart unit tương ứng. Tầng 3 quan trọng nhất trong thực tế và hay bị bỏ quên — nó bắt được "mọi tiến trình đều sống nhưng không có tiếng"
- **Log ra SSD, không dùng `Storage=volatile`** — log mất khi reboot là ác mộng khi debug qua điện thoại. journald `SystemMaxUse=300M`, `SyncIntervalSec=60`. Thêm bảng `events` trong SQLite ghi sự kiện nghiệp vụ (mỗi bài hát, mỗi lần đổi preset, mỗi xrun, mỗi lần mất thiết bị) để trả lời "tối qua 9h có chuyện gì" mà không phải lội journal
- **Nút "Xuất nhật ký"** trên màn cài đặt: đóng gói `journalctl --since -3d` + `pw-dump` + `dmesg` + `lsusb -v` + `xrandr --verbose` + config hiện tại ra `.tar.gz` lên USB
- **Backup DB** hàng ngày 5:00 bằng `sqlite3 ... ".backup"` (**không dùng `cp`** — copy file SQLite đang mở là cách chắc chắn nhất để có bản sao hỏng), giữ 7 ngày + 4 tuần + 3 tháng, chép một bản sang `/persist` trên CFast để SSD chết vẫn còn metadata thư viện, và chạy `PRAGMA integrity_check` sau mỗi lần backup
- `chrony` thay `systemd-timesyncd` (xử lý mất mạng dài và bước nhảy lớn tốt hơn). Nếu pin RTC của MB-8390 đã hết (board công nghiệp lưu kho lâu hay bị), mỗi lần boot mất mạng giờ sẽ về 1970 và log thành vô dụng — kiểm ở GĐ0
- Cập nhật phần mềm: `git pull` + `systemctl restart` qua script, có `git tag` để rollback. Quy mô 1 máy không cần kho apt riêng hay A/B partition

---

## Kiểm thử và nghiệm thu

**Trong VM (mỗi giai đoạn):**
```bash
pytest core/tests/                                  # parser, encoding, queue, search
qemu-system-x86_64 ...                              # 2 output, boot vào kiosk
curl localhost:8080/api/state | jq                  # core sống
# duyệt http://localhost:8080 từ Windows → PWA hoạt động
modprobe snd-dummy                                  # card ảo 2in/2out, test định tuyến khi không có phần cứng
```

**Trên MB-8390 thật — bảng nghiệm thu:**

| Hạng mục | Cách đo | Đạt khi |
|---|---|---|
| Boot đến màn hình chọn bài | bấm nguồn, bấm giờ | < 40s |
| Hai màn hình đúng vai trò | nhìn | UI ở màn cảm ứng, video ở TV |
| Chạm đúng vị trí | chạm 4 góc màn cảm ứng | lệch < 5mm |
| Tắt/bật TV 20 lần | rút HDMI, cắm lại | cửa sổ mpv không nhảy sang màn cảm ứng |
| Điện thoại đặt bài | 5 máy khác nhau (iOS + Android) | quét QR → vào app < 15s, đặt bài hiện ngay trên TV |
| Chuyển bài | bấm Bài kế | không nháy đen, < 1s |
| Chạy liên tục 4 giờ | `pw-top` cột ERR, nhiệt độ CPU | **ERR = 0**, không giật tiếng |
| Mất điện đột ngột 10 lần | rút phích khi đang phát | boot lại bình thường, DB không hỏng |
| Rút USB mixer khi đang phát | rút, cắm lại | tự phục hồi tiếng < 5s, UI báo rõ |
| SSD chưa cắm | tháo SSD, boot | vẫn boot, hiện màn hình báo lỗi rõ ràng (không vào emergency shell) |
| Round-trip mic (chỉ Mức B) | cáp loopback + `pw-jack jack_iodelay` | < 20ms |
| Đồng bộ lời MIDI (GĐ3) | quay 240fps màn TV + tiếng | lệch < 50ms sau 5 phút phát |

---

## Rủi ro lớn nhất

| # | Rủi ro | Giảm thiểu |
|---|---|---|
| 1 | **MG10XU không cho tách mic** → không làm được mixer mic phần mềm và chống hú | Đã nêu ở đầu kế hoạch. GĐ0 đo để chốt Mức A hay B; tầng audio thiết kế trừu tượng để đổi sau không phải viết lại |
| 2 | **yt-dlp hỏng khi YouTube đổi giao diện** — sẽ xảy ra, chỉ là khi nào | Cache mọi bài đã phát xuống SSD (thư viện offline tự lớn dần) + nút cập nhật yt-dlp trên UI + fallback sang thư viện local khi YouTube lỗi |
| 3 | **Bảng mã tiếng Việt dò sai** (GĐ3) → lời thành ký tự rác | Spike với 50 file thật trước khi code; suy luận theo thư mục; màn sửa tay có preview; nút xoay codec khi đang hát |
| 4 | **Quy ước lyric Arirang khác giả định** (GĐ3) | Cùng spike; parser theo strategy pattern (`ArirangStrategy`/`KarStandardStrategy`/`PlainLyricStrategy`) để bổ sung dễ |
| 5 | **TV tắt → X mất output → cửa sổ mpv nhảy sang màn cảm ứng** | Ép EDID/mode tĩnh qua kernel cmdline; theo dõi RandR event và tự đặt lại cửa sổ. Phải thử tắt/bật TV 20 lần |
| 6 | **Xrun / giật tiếng** khi quét thư viện hoặc tải YouTube | quantum/headroom dư dả, `max_cstate=1`, governor performance, tác vụ nền `Nice=10 IOSchedulingClass=idle`, tắt `apt-daily.timer`; core tự nâng quantum lên 256 nếu ERR tăng |
| 7 | **USB audio rớt** (cáp lỏng, autosuspend, nhiễu USB3) | `usbcore.autosuspend=-1`, cắm trực tiếp vào board không qua hub, cáp ngắn có ferrite, cố định bằng dây rút; udev rule → restart `karaoke-dsp` |
| 8 | **CFast hỏng do ghi nhiều / mất điện** | `noatime`, tmpfs cho `/tmp`, log sang SSD, chừa 1.5GB chưa cấp phát, tắt swap trên CFast. Nếu về sau muốn chắc hơn: `systemd.volatile=overlay` cho root read-only + mục GRUB "Service Mode" |
| 9 | **Card WiFi không hỗ trợ AP mode hoặc đuối khi nhiều client** | Kiểm `iw list` ở GĐ0; test tải với 8–10 điện thoại thật trong 2 giờ — loại lỗi này chỉ xuất hiện dưới tải. Phương án thay: card MediaTek MT7921K |
| 10 | **Giấy phép** — mpv GPL, librubberband GPL, soundfont | Chạy 1 máy trong quán của mình thì không phát sinh nghĩa vụ phân phối. Nếu sau này bán ra, phải xem lại: mpv chạy tiến trình riêng (đã chọn) là vị thế an toàn hơn libmpv |

---

## Phụ lục — Gói Debian cần cài

```
# Nền + đồ họa
xserver-xorg-core xserver-xorg-input-libinput xinit openbox lightdm
unclutter xinput x11-xserver-utils
firmware-misc-nonfree intel-media-va-driver-non-free

# Âm thanh
pipewire pipewire-audio pipewire-alsa pipewire-pulse pipewire-jack
wireplumber pipewire-bin libspa-0.2-modules alsa-utils
calf-plugins lsp-plugins-lv2 x42-plugins zam-plugins dragonfly-reverb
swh-plugins tap-plugins

# Phát nhạc
mpv fluidsynth fluid-soundfont-gm fonts-noto-core

# Mạng
hostapd dnsmasq iw wireless-regdb nginx-light chrony

# Ứng dụng
python3 python3-venv python3-systemd python3-mido sqlite3 ffmpeg
bmap-tools git

# Chỉ trên bản DEV
rt-tests jack-example-tools qpwgraph openssh-server
```
`PySide6`, `yt-dlp`, `fastapi`, `uvicorn` cài bằng **venv ghim phiên bản** tại `/opt/karaoke/venv` — không dùng gói Debian, để phiên bản UI độc lập với chu kỳ Debian. Gỡ/chặn `pulseaudio` và `jackd2`.
