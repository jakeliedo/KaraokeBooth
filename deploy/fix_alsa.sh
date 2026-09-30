#!/bin/bash
# Đảm bảo audio hoạt động sau khi karaoke-core khởi động.
# Chạy ở background qua ExecStartPost — không block stop phase.
# Deploy to: /etc/karaoke/fix_alsa.sh
#
# Script này chạy AS USER karaoke (từ user systemd service).
# KHÔNG dùng "sudo -u karaoke" — karaoke không có sudo, sẽ fail silently.
#
# Jack thật đang dùng là rear IO (lineout, NID 0x14) — KHÔNG phải headphone
# jack mặt trước (NID 0x1b, không có gì cắm vào). Xem CLAUDE.md gotcha #8 —
# port đúng thôi chưa đủ, còn cần bật Pin-ctls thật cho node 0x14 (driver
# không tự làm trên board này, dmesg: "ALC886: SKU not ready"). Thanh ghi này
# RESET mỗi khi mpv mở lại thiết bị (karaoke-core restart) — không chỉ chạy
# 1 lần lúc boot (karaoke-audio-pinfix.service) là đủ, phải chạy lại ở đây.
# Cần root — dùng sudoers rule hẹp /etc/sudoers.d/karaoke-hda-pinfix (đúng
# 1 lệnh, không phải NOPASSWD chung chung).
#
# Volume 40% mặc định của WirePlumber (device.routes.default-sink-volume) đã
# ép = 1.0 qua wireplumber.conf.d/50-volume-default.conf; suspend-khi-idle mute
# sink đã tắt qua wireplumber.conf.d/51-karaoke-usb.conf (session.suspend-
# timeout-seconds=0 cho node này) — 2 lệnh wpctl dưới đây chỉ là belt-and-
# suspenders, KHÔNG phải fix chính. Thứ tự quan trọng: đổi port TRƯỚC, unmute
# SAU — làm ngược lại thì WP reset mute khi activate route mới, mất tiếng.
SINK="alsa_output.pci-0000_00_14.2.analog-stereo"
export XDG_RUNTIME_DIR=/run/user/1001
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1001/bus

# Đợi WirePlumber sẵn sàng
sleep 4

sudo -n /usr/bin/hda-verb /dev/snd/hwC1D0 0x14 SET_PIN_WIDGET_CONTROL 0x40 2>/dev/null || true

# Belt-and-suspenders: Auto-Mute Mode phải Disabled (đã persist vào asound.state
# bằng `alsactl store`, nhưng nếu ai đó cài lại/asound.state hỏng thì vẫn cần
# dòng này — không thì driver tự mute lại Front theo jack-sense sai của node
# Headphone, xem CLAUDE.md gotcha #9).
/usr/bin/amixer -c 1 sset 'Auto-Mute Mode' Disabled 2>/dev/null || true

pactl set-sink-port "$SINK" analog-output-lineout 2>/dev/null || true

# Set PipeWire sink volume=1.0 + unmute (belt-and-suspenders, xem comment trên)
for i in 1 2 3; do
    sleep 2
    wpctl set-volume @DEFAULT_AUDIO_SINK@ 1.0 2>/dev/null && break
done
wpctl set-mute @DEFAULT_AUDIO_SINK@ 0 2>/dev/null || true

# Belt-and-suspenders: ALSA Front (rear IO) vẫn đúng
/usr/bin/amixer -c 1 sset Front 100% unmute 2>/dev/null || true
