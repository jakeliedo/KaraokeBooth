#!/bin/sh
# Phiên X của người dùng karaoke. LightDM gọi file này qua karaoke.desktop.
#
# Dùng LightDM autologin chứ KHÔNG tự chạy `startx` từ systemd: LightDM tạo phiên
# logind đầy đủ (XDG_RUNTIME_DIR, seat, PAM) mà PipeWire, WirePlumber và polkit
# đều phụ thuộc. Tự startx dẫn tới phiên nửa vời và những lỗi rất khó chẩn đoán.
set -eu

xset s off -dpms
xset s noblank

# Nhận diện màn theo EDID chứ không theo tên output — tên (HDMI-1/DP-2) đổi giữa
# các lần cắm. Ánh xạ được lưu lúc lắp đặt tại /persist/config/displays.json.
. /usr/lib/karaoke/detect-displays.sh   # xuất TOUCH_OUT, TV_OUT, TOUCH_DEV

xrandr --output "$TOUCH_OUT" --mode 1920x1080 --pos 0x0    --primary
xrandr --output "$TV_OUT"    --mode 1920x1080 --pos 1920x0

# BẮT BUỘC và phải chạy SAU mỗi lần xrandr. Nếu quên, vùng chạm trải trên toàn bộ
# desktop ảo 3840x1080 và mọi cú chạm lệch đúng một nửa màn hình.
if [ -n "${TOUCH_DEV:-}" ]; then
    xinput map-to-output "$TOUCH_DEV" "$TOUCH_OUT" || true
fi

openbox &
unclutter -idle 0.5 -root &

systemctl --user start karaoke-ui.service
wait
