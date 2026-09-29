#!/usr/bin/env bash
# Kiểm chứng phần cứng cho KaraokeBooth — chạy trên máy thật (MB-8390) hoặc trong VM.
# Chỉ đọc, không thay đổi gì. Xuất báo cáo ra stdout và /tmp/karaoke-hw-report.txt
set -uo pipefail

REPORT=/tmp/karaoke-hw-report.txt
exec > >(tee "$REPORT") 2>&1

section() { printf '\n\033[1;36m=== %s ===\033[0m\n' "$1"; }
have()    { command -v "$1" >/dev/null 2>&1; }
check()   { # check <mức> <mô tả> <lệnh test>
  local lvl=$1 desc=$2; shift 2
  if "$@" >/dev/null 2>&1; then printf '  \033[32m[ĐẠT]\033[0m  %s %s\n' "$lvl" "$desc"
  else                          printf '  \033[31m[HỎNG]\033[0m %s %s\n' "$lvl" "$desc"; fi
}

echo "KaraokeBooth — báo cáo kiểm chứng phần cứng"
echo "Thời điểm: $(date -Is)"
echo "Hostname : $(hostname)"

section "1. Hệ thống"
have hostnamectl && hostnamectl | sed 's/^/  /'
echo "  Kernel cmdline: $(cat /proc/cmdline)"
have dmidecode && sudo dmidecode -s baseboard-product-name 2>/dev/null | sed 's/^/  Mainboard: /'
have dmidecode && sudo dmidecode -s processor-version 2>/dev/null | sed 's/^/  CPU: /'
echo "  RAM: $(free -h | awk '/^Mem:/{print $2}')"

section "2. Đồ họa và màn hình"
have lspci && lspci -nnk | grep -A3 -E 'VGA|Display' | sed 's/^/  /'
echo "  Output DRM:"
for c in /sys/class/drm/card*-*; do
  [ -e "$c/status" ] || continue
  printf '    %-20s %s' "$(basename "$c")" "$(cat "$c/status")"
  [ -s "$c/edid" ] && printf '  edid_sha1=%s' "$(sha1sum < "$c/edid" | cut -c1-12)"
  echo
done
if [ -n "${DISPLAY:-}" ] && have xrandr; then
  echo "  xrandr:"; xrandr --listmonitors | sed 's/^/    /'
fi

section "3. Thiết bị cảm ứng"
if [ -n "${DISPLAY:-}" ] && have xinput; then
  xinput list --short | sed 's/^/  /'
  echo "  → gán bằng: xinput map-to-output '<tên>' '<output>'  (chạy SAU mỗi lần xrandr)"
else
  echo "  (không có DISPLAY — chạy lại trong phiên X)"
  have libinput && sudo libinput list-devices 2>/dev/null | grep -B2 -i touch | sed 's/^/  /'
fi

section "4. WiFi"
have iw || echo "  CHƯA CÀI iw — apt install iw"
if have iw; then
  for dev in $(iw dev 2>/dev/null | awk '/Interface/{print $2}'); do
    echo "  Interface: $dev"
    iw dev "$dev" info | sed 's/^/    /'
  done
  echo "  Chế độ hỗ trợ:"
  iw list 2>/dev/null | sed -n '/Supported interface modes/,/^\s*[A-Z]/p' | sed 's/^/    /'
  if iw list 2>/dev/null | grep -qE '^\s+\* AP$'; then
    echo "    → CÓ AP mode"
  else
    echo "    → KHÔNG thấy AP mode. Cân nhắc card MediaTek MT7921K"
  fi
fi

section "5. Âm thanh — thiết bị"
have aplay && aplay -l 2>/dev/null | sed 's/^/  /'
echo "  --- capture ---"
have arecord && arecord -l 2>/dev/null | sed 's/^/  /'
echo "  --- stream0 (UAC1 hay UAC2, số kênh thật) ---"
for s in /proc/asound/card*/stream0; do
  [ -e "$s" ] || continue
  echo "  $s:"; sed 's/^/    /' "$s"
done
have lsusb && lsusb | grep -iE 'yamaha|behringer|audio|steinberg' | sed 's/^/  USB audio: /'

section "6. PipeWire"
have pw-cli || echo "  CHƯA CÀI pipewire-bin"
if have pw-dump; then
  if have jq; then
    pw-dump | jq -r '.[] | select(.info.props."media.class") |
      "  \(.info.props."media.class"|.[0:18])  \(.info.props."node.name")"' 2>/dev/null | sort -u
  else
    echo "  (cài jq để xem danh sách node)"
  fi
  echo "  Quantum/rate hiện tại:"
  have pw-metadata && pw-metadata -n settings 2>/dev/null | grep -E 'clock.(rate|quantum)' | sed 's/^/    /'
fi
echo "  filter-chain plugin có sẵn:"
ls /usr/lib/*/spa-0.2/filter-graph/ 2>/dev/null | sed 's/^/    /' || echo "    (không có thư mục filter-graph → chỉ dùng được builtin + LADSPA)"

section "7. mpv / ffmpeg"
have mpv && mpv --version | head -1 | sed 's/^/  /'
if have mpv; then
  if mpv --af=help 2>/dev/null | grep -qi rubberband; then
    echo "  → mpv CÓ af rubberband (đổi tông video được)"
  else
    echo "  → mpv KHÔNG có af rubberband native, thử lavfi bên dưới"
  fi
fi
if have ffmpeg; then
  ffmpeg -hide_banner -filters 2>/dev/null | grep -qi rubberband \
    && echo "  → ffmpeg CÓ filter rubberband" \
    || echo "  → ffmpeg KHÔNG có rubberband (cần bản ffmpeg GPL với --enable-librubberband)"
fi
have yt-dlp && yt-dlp --version | sed 's/^/  yt-dlp: /'

section "8. Ổ đĩa"
lsblk -o NAME,SIZE,TYPE,FSTYPE,LABEL,MOUNTPOINT,DISC-GRAN 2>/dev/null | sed 's/^/  /'
echo "  (cột DISC-GRAN = 0B nghĩa là không hỗ trợ TRIM)"

section "9. Watchdog và RTC"
[ -e /dev/watchdog ] && echo "  CÓ /dev/watchdog" || echo "  KHÔNG có /dev/watchdog — kiểm modprobe iTCO_wdt"
dmesg 2>/dev/null | grep -i wdt | tail -3 | sed 's/^/  /'
have hwclock && sudo hwclock --show 2>/dev/null | sed 's/^/  RTC: /'

section "10. Nhiệt độ"
have sensors && sensors 2>/dev/null | sed 's/^/  /' || echo "  (apt install lm-sensors)"

section "TÓM TẮT"
check "🔴" "Có ít nhất 2 output hiển thị được kết nối" \
  bash -c '[ $(grep -l "^connected" /sys/class/drm/card*-*/status 2>/dev/null | wc -l) -ge 2 ]'
check "🔴" "WiFi hỗ trợ AP mode" bash -c 'iw list 2>/dev/null | grep -qE "^\s+\* AP$"'
check "🔴" "Có thiết bị capture USB audio" bash -c 'arecord -l 2>/dev/null | grep -q USB'
check "🔴" "PipeWire đang chạy" bash -c 'pw-cli info 0 >/dev/null 2>&1'
check "🟡" "Có /dev/watchdog" test -e /dev/watchdog
check "🟡" "mpv đã cài" have mpv

printf '\nBáo cáo đã lưu: %s\n' "$REPORT"
printf 'Điền kết quả vào docs/VERIFY.md rồi mới viết tiếp code.\n'
