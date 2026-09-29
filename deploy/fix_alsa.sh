#!/bin/bash
# Unmute ALSA controls sau khi PipeWire/WirePlumber khởi động.
# Chạy ở background qua ExecStartPost trong karaoke-core.service.
# Deploy to: /etc/karaoke/fix_alsa.sh
#
# Lý do cần: WirePlumber đôi khi reset volume về 0 khi load profile ALSA.
# Vòng lặp 5x2s đảm bảo unmute ngay cả khi WirePlumber khởi động chậm.
for i in 1 2 3 4 5; do
    sleep 2
    /usr/bin/amixer -c 1 sset Master 100% unmute 2>/dev/null || true
    /usr/bin/amixer -c 1 sset Headphone 100% unmute 2>/dev/null || true
    /usr/bin/amixer -c 1 sset Front 100% unmute 2>/dev/null || true
    /usr/bin/amixer -c 1 sset PCM 100% 2>/dev/null || true
done
/usr/sbin/alsactl store 1 2>/dev/null || true
