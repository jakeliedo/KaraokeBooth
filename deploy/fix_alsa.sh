#!/bin/bash
# Đảm bảo audio hoạt động sau khi karaoke-core khởi động.
# Chạy ở background qua ExecStartPost — không block stop phase.
# Deploy to: /etc/karaoke/fix_alsa.sh
#
# Root cause: WirePlumber 0.5.x khởi động với vol ~40% và không tự lưu state.
# asound.state đã được patch Headphone=31 + device.restore-routes=false ngăn
# WP override Headphone về 0. Script này chỉ cần đẩy PW node volume lên 1.0.
SINK="alsa_output.pci-0000_00_14.2.analog-stereo"
export XDG_RUNTIME_DIR=/run/user/1001
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1001/bus

# Đợi WirePlumber sẵn sàng
sleep 4

# Set PipeWire sink volume=1.0 + unmute (WP khởi động ở ~0.40, không muted)
for i in 1 2 3; do
    sleep 2
    /usr/bin/sudo -u karaoke -E wpctl set-volume @DEFAULT_AUDIO_SINK@ 1.0 2>/dev/null && break
done
/usr/bin/sudo -u karaoke -E wpctl set-mute @DEFAULT_AUDIO_SINK@ 0 2>/dev/null || true
/usr/bin/sudo -u karaoke -E pactl set-sink-port "$SINK" analog-output-headphones 2>/dev/null || true

# Belt-and-suspenders: ALSA Headphone vẫn đúng (device.restore-routes=false giữ nó)
/usr/bin/amixer -c 1 sset Headphone 100% unmute 2>/dev/null || true
