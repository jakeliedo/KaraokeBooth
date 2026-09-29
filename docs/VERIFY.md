# Bảng kiểm chứng phần cứng (Giai đoạn 0)

Chạy `sudo ./tools/verify-hardware.sh` trên máy thật và điền kết quả vào đây.
**Không viết tiếp code ứng dụng trước khi mọi mục 🔴 đã xanh.**

| # | Hạng mục | Lệnh | Mức | Kết quả |
|---|---|---|---|---|
| 1 | Debian 13 boot, GPU bind được driver | `lspci -nnk \| grep -A3 VGA` | 🔴 | |
| 2 | Hai output hiển thị độc lập | `ls /sys/class/drm/` + `xrandr` | 🔴 | |
| 3 | Touchscreen gán đúng màn | `xinput list` + `xinput map-to-output` | 🔴 | |
| 4 | Card WiFi có AP mode | `iw list \| grep -A10 "interface modes"` | 🔴 | |
| 5 | **MG10XU: USB out lấy từ đâu** | `arecord` rồi nghe lại | 🔴 | |
| 6 | MG10XU có cổng INSERT không | nhìn mặt sau mixer | 🔴 | |
| 7 | `pw-cli` đọc lệnh liên tục từ stdin | script test | 🔴 | |
| 8 | filter-chain có hỗ trợ node `lv2` | `ls /usr/lib/*/spa-0.2/filter-graph/` | 🟡 | |
| 9 | mpv/ffmpeg có `rubberband` (đổi tông video) | `mpv --af=help`, `ffmpeg -h filter=rubberband` | 🟡 | |
| 10 | Hardware watchdog | `ls /dev/watchdog`, `dmesg \| grep wdt` | 🟡 | |
| 11 | Pin RTC còn tốt | `hwclock --show` sau khi rút điện qua đêm | 🟡 | |
| 12 | Nhiệt độ CPU với `max_cstate=1` trong vỏ kín | đo sau 4h chạy | 🟡 | |
| 13 | CFast hỗ trợ TRIM | `lsblk --discard` | 🟢 | |
| 14 | Captive portal trên iOS + Android thật | test tay | 🟡 | |
| 15 | QEMU `virtio-vga-gl,max_outputs=2` | `qemu-system-x86_64 -device virtio-vga-gl,help` | 🟡 | |

## Mục 5 — cách đo quan trọng nhất

```bash
arecord -l                                    # tìm card của MG10XU
arecord -D hw:1,0 -f cd -d 10 /tmp/test.wav   # thu 10 giây
aplay /tmp/test.wav
```

Trong lúc thu: **kéo fader mic lên và hát, đồng thời cho máy phát nhạc**.

- Nghe thấy **cả mic lẫn nhạc trộn chung** ⇒ USB out là stereo bus ⇒ **Mức A**.
- Nghe thấy **chỉ mic, không có nhạc** ⇒ có đường gửi riêng ⇒ có thể làm **Mức B**
  mà không cần mua interface. Rất ít khả năng với MG10XU, nhưng phải đo mới biết.

Ghi lại tên node thật, **tuyệt đối không đoán**:
```bash
pw-dump | jq -r '.[] | select(.info.props."media.class") |
  "\(.info.props."media.class")\t\(.info.props."node.name")"'
cat /proc/asound/card*/stream0      # UAC1 hay UAC2, số kênh, altsetting
```

## Nếu một mục đỏ

| Mục | Phương án |
|---|---|
| 1 | Thêm `firmware-misc-nonfree`, `intel-media-va-driver-non-free`; cùng lắm đổi Ubuntu 24.04 HWE |
| 2 | Kiểm tra cáp/EDID; ép mode tĩnh qua kernel cmdline `video=HDMI-A-1:1920x1080@60` |
| 3 | Dùng `TransformationMatrix` trong `/etc/X11/xorg.conf.d/40-touchscreen.conf` |
| 4 | Thay card MediaTek MT7921K (M.2 2230, driver `mt7921e` mainline). Tránh Intel AX2xx — `iwlwifi` hỗ trợ AP nhưng không ổn định khi nhiều client |
| 5, 6 | Xem [WIRING.md](WIRING.md) — quyết định Mức A hay B |
| 7 | Viết daemon nhỏ dùng `libpipewire`, hoặc dùng `wpctl`/`pw-dump` |
| 8 | Toàn bộ chuỗi DSP vẫn làm được bằng node builtin + LADSPA |
| 9 | Làm mờ nút đổi tông cho bài video, ghi rõ trên UI. Không phải blocker |

## Test tải WiFi

Lỗi card WiFi chỉ xuất hiện dưới tải, không xuất hiện khi test một máy.
**Phải test với 8–10 điện thoại thật cùng lúc trong 2 giờ**, theo dõi:

```bash
watch -n2 'iw dev wlan0 station dump | grep -c Station'
journalctl -u hostapd -f
```
