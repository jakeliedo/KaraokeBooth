# Xử lý sự cố tại quán

Bắt đầu từ đây trước khi mở code. Mỗi mục là một triệu chứng nhân viên quán mô tả
được qua điện thoại.

## "Không có tiếng"

```bash
systemctl --user status karaoke-core karaoke-dsp
pw-cli info 0                  # PipeWire còn sống?
pw-dump | jq -r '.[] | select(.info.props."media.class"=="Audio/Sink") | .info.props."node.name"'
```

| Nguyên nhân hay gặp | Dấu hiệu | Xử lý |
|---|---|---|
| Nhạc ra HDMI (loa TV) | `node.name` chứa `hdmi` | Kiểm tra `player.audio_device` trong `/etc/karaoke/config.toml`, và rule vô hiệu hoá HDMI trong `51-karaoke-usb.conf` |
| Thiết bị USB đổi chỉ số sau reboot | sink cũ biến mất | Ghim theo `node.name`, không theo chỉ số card |
| Cáp USB lỏng | `dmesg` có `USB disconnect` | Cắm trực tiếp vào board, cố định cáp bằng dây rút |
| `karaoke-dsp` chết | `systemctl --user status karaoke-dsp` | Nó tự restart sau 1-2s; nếu lặp liên tục thì xem plugin nào crash trong journal |

## "Tiếng kêu tách tách / giật"

```bash
pw-top          # cột ERR phải bằng 0
journalctl --user -u karaoke-dsp --since -1h | grep -i xrun
```

Xử lý theo thứ tự: tăng `api.alsa.headroom` trước → tăng `quantum` lên 512 sau.
Kiểm tra có tác vụ nặng chạy nền không (quét thư viện, tải YouTube) — chúng phải
chạy với `Nice=10 IOSchedulingClass=idle`. Kiểm tra `intel_idle.max_cstate=1` còn
trong `/proc/cmdline` không.

## "Màn hình TV không hiện gì"

```bash
DISPLAY=:0 xrandr --listmonitors
systemctl --user status karaoke-core | grep -i mpv
```

Nếu TV vừa bị tắt/bật, X có thể đã bỏ output đó và cửa sổ mpv nhảy sang màn cảm
ứng. Chạy lại `/usr/lib/karaoke/session.sh` hoặc khởi động lại lightdm.
Cách chống triệt để: ép mode tĩnh trong kernel cmdline
(`video=HDMI-A-1:1920x1080@60`).

## "Chạm không đúng chỗ"

Gần như luôn là thiếu `xinput map-to-output`. Vùng chạm đang trải trên toàn bộ
desktop ảo 3840×1080 nên mọi cú chạm lệch đúng một nửa màn hình.

```bash
DISPLAY=:0 xinput list
DISPLAY=:0 xinput map-to-output "<tên thiết bị>" "<output của màn cảm ứng>"
```

Phải chạy **sau** mỗi lần `xrandr` đổi layout.

## "Điện thoại không vào được app"

```bash
systemctl status hostapd dnsmasq nginx
iw dev wlan0 station dump | grep -c Station     # có bao nhiêu máy đang nối
journalctl -u dnsmasq --since -10m | grep DHCP
```

- Điện thoại nối được WiFi nhưng không mở được trang → kiểm tra nginx và DNS
  wildcard (`address=/#/192.168.50.1`).
- Không thấy SSID → card WiFi có thể đã rớt; `ip link` xem `wlan0` còn không.
- Android không vào được bằng tên miền → dùng QR trên TV hoặc gõ thẳng
  `192.168.50.1`. Không dựa vào `.local`.

## "Tìm bài trên YouTube không ra kết quả"

yt-dlp hỏng mỗi khi YouTube đổi giao diện — đây là chuyện thường, không phải máy
hỏng. Vào màn Cài đặt bấm "Cập nhật yt-dlp", hoặc:

```bash
/opt/karaoke/venv/bin/pip install -U yt-dlp
systemctl --user restart karaoke-core
```

Trong lúc chờ, thư viện offline vẫn tìm và hát được bình thường.

## Xuất gói chẩn đoán

Màn Cài đặt có nút "Xuất nhật ký". Bằng tay:

```bash
tar czf /tmp/karaoke-logs.tar.gz \
  <(journalctl --since -3d) <(pw-dump) <(dmesg) <(lsusb -v) \
  <(DISPLAY=:0 xrandr --verbose) /etc/karaoke/
```

Kèm luôn truy vấn nhật ký nghiệp vụ — nhanh hơn lội journald nhiều:

```bash
sqlite3 /data/db/karaoke.db \
  "SELECT datetime(at,'unixepoch','localtime'), kind, detail
   FROM events ORDER BY at DESC LIMIT 50"
```
