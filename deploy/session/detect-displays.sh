#!/bin/sh
# Xác định output nào là TV, output nào là màn cảm ứng.
#
# Ưu tiên ánh xạ đã lưu lúc lắp đặt (theo hash EDID, bền qua các lần cắm lại).
# Chưa có thì dùng heuristic: output đầu tiên đang kết nối là màn cảm ứng, output
# thứ hai là TV — và UI có nút "Đổi vai trò hai màn hình" để kỹ thuật viên sửa.
MAP=/persist/config/displays.json

CONNECTED=$(xrandr --query | awk '/ connected/{print $1}')
TOUCH_OUT=$(echo "$CONNECTED" | sed -n 1p)
TV_OUT=$(echo "$CONNECTED" | sed -n 2p)

if [ -r "$MAP" ] && command -v jq >/dev/null 2>&1; then
    SAVED_TOUCH=$(jq -r '.touch // empty' "$MAP")
    SAVED_TV=$(jq -r '.tv // empty' "$MAP")
    echo "$CONNECTED" | grep -qx "$SAVED_TOUCH" && TOUCH_OUT=$SAVED_TOUCH
    echo "$CONNECTED" | grep -qx "$SAVED_TV"    && TV_OUT=$SAVED_TV
fi

# Chỉ có một màn (đang sửa chữa, TV chưa cắm): dồn cả hai vai trò vào một output
# để máy vẫn dùng được thay vì không hiện gì.
[ -z "$TV_OUT" ] && TV_OUT=$TOUCH_OUT

TOUCH_DEV=$(xinput list --name-only 2>/dev/null | grep -i -m1 -E 'touch|elan|ilitek|egalax' || true)

export TOUCH_OUT TV_OUT TOUCH_DEV
