#!/bin/sh
# Phiên X của người dùng karaoke. LightDM gọi file này qua karaoke.desktop.
#
# Dùng LightDM autologin chứ KHÔNG tự chạy `startx` từ systemd: LightDM tạo phiên
# logind đầy đủ (XDG_RUNTIME_DIR, seat, PAM) mà PipeWire, WirePlumber và polkit
# đều phụ thuộc. Tự startx dẫn tới phiên nửa vời và những lỗi rất khó chẩn đoán.
set -eu

xset s off -dpms
xset s noblank

# Cho phép karaoke user (chạy service) kết nối X display này
xhost +local:karaoke

# Nhận diện màn theo EDID chứ không theo tên output — tên (HDMI-1/DP-2) đổi giữa
# các lần cắm. Ánh xạ được lưu lúc lắp đặt tại /persist/config/displays.json.
. /usr/lib/karaoke/detect-displays.sh   # xuất TOUCH_OUT, TV_OUT, TOUCH_DEV

if [ "$TOUCH_OUT" = "$TV_OUT" ]; then
    # Chỉ một màn: TV chiếm toàn bộ, mpv dùng screen=0
    xrandr --output "$TV_OUT" --auto --pos 0x0 --primary
    KARAOKE_SCREEN=0
else
    # Hai màn: ELO (cảm ứng) ở x=0, TV ở x=1920 (right).
    # mpv đánh số theo vị trí vật lý: 0=trái(ELO), 1=phải(TV).
    xrandr --output "$TOUCH_OUT" --mode 1920x1080 --pos 0x0
    xrandr --output "$TV_OUT"    --auto --pos 1920x0 --primary
    KARAOKE_SCREEN=1
fi

# Ghi screen index vào config để karaoke-core dùng đúng màn
sed -i "s/^screen = .*/screen = ${KARAOKE_SCREEN}/" /etc/karaoke/config.toml 2>/dev/null || true

# BẮT BUỘC và phải chạy SAU mỗi lần xrandr. Nếu quên, vùng chạm trải trên toàn bộ
# desktop ảo 3840x1080 và mọi cú chạm lệch đúng một nửa màn hình.
if [ -n "${TOUCH_DEV:-}" ]; then
    xinput map-to-output "$TOUCH_DEV" "$TOUCH_OUT" || true
fi

openbox &
unclutter -idle 0.5 -root &

# Kiosk Chromium trên màn cảm ứng (TOUCH_OUT, luôn ở vị trí x=0)
# --app= bỏ thanh địa chỉ; --kiosk fullscreen trên màn hiện tại của cửa sổ;
# --window-position=0,0 đảm bảo bắt đầu trên màn trái (ELO), không phải TV.
chromium \
    --kiosk \
    --app=http://localhost/kiosk.html \
    --no-sandbox \
    --no-first-run \
    --disable-translate \
    --disable-extensions \
    --noerrdialogs \
    --disable-session-crashed-bubble \
    --disable-infobars \
    --disable-features=TranslateUI \
    --window-position=0,0 &

wait
