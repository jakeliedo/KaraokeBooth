#!/usr/bin/env bash
# Cấu hình một máy Debian 13 trống thành máy karaoke.
#
# Idempotent: chạy lại nhiều lần không sao. Chạy được trong máy ảo lẫn trên
# MB-8390 thật. KHÔNG tự phân vùng ổ đĩa — phần đó làm bằng tay hoặc bằng
# build-image.sh, vì xoá nhầm ổ dữ liệu là lỗi không sửa được.
#
#   sudo ./provision.sh            # cài đầy đủ
#   sudo ./provision.sh --no-ap    # bỏ qua WiFi AP (dùng mạng sẵn có)
set -euo pipefail

REPO=$(cd "$(dirname "$0")/.." && pwd)
PREFIX=/opt/karaoke
USER_NAME=karaoke
WITH_AP=1
[ "${1:-}" = "--no-ap" ] && WITH_AP=0

[ "$(id -u)" -eq 0 ] || { echo "Phải chạy bằng root"; exit 1; }

log() { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }

# ---------------------------------------------------------------- gói
log "Cài gói"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends \
    xserver-xorg-core xserver-xorg-input-libinput xinit openbox lightdm \
    unclutter xinput x11-xserver-utils \
    firmware-misc-nonfree intel-media-va-driver-non-free \
    pipewire pipewire-audio pipewire-alsa pipewire-pulse pipewire-jack \
    wireplumber pipewire-bin libspa-0.2-modules alsa-utils \
    mpv ffmpeg fonts-noto-core \
    python3 python3-venv python3-systemd sqlite3 \
    nginx-light chrony jq curl git rsync bmap-tools

if [ "$WITH_AP" -eq 1 ]; then
    apt-get install -y --no-install-recommends hostapd dnsmasq iw wireless-regdb
fi

# PulseAudio và JACK server tranh chấp thiết bị với PipeWire.
apt-get purge -y pulseaudio jackd2 2>/dev/null || true

# ---------------------------------------------------------------- người dùng
log "Tạo user $USER_NAME"
id "$USER_NAME" >/dev/null 2>&1 || useradd -m -s /bin/bash "$USER_NAME"
usermod -aG audio,video,render "$USER_NAME"
# Để service của user chạy ngay từ lúc boot, không cần đăng nhập trước.
loginctl enable-linger "$USER_NAME"

# ---------------------------------------------------------------- thư mục
log "Tạo thư mục dữ liệu"
install -d -o "$USER_NAME" -g "$USER_NAME" \
    /data/db /data/db/backup /data/media /data/cache /data/config /data/log \
    /persist/config /persist/backup /run/karaoke
install -d /etc/karaoke /usr/lib/karaoke

# ---------------------------------------------------------------- mã nguồn
log "Cài ứng dụng vào $PREFIX"
install -d "$PREFIX"
rsync -a --delete "$REPO/core/"  "$PREFIX/core/"
rsync -a --delete "$REPO/web/"   "$PREFIX/web/"
rsync -a --delete "$REPO/ui/"    "$PREFIX/ui/"
cp "$REPO/deploy/network/portal.html" "$PREFIX/web/portal.html"

# venv riêng, ghim phiên bản độc lập với chu kỳ Debian
if [ ! -x "$PREFIX/venv/bin/python" ]; then
    python3 -m venv "$PREFIX/venv"
fi
"$PREFIX/venv/bin/pip" install --quiet --upgrade pip
"$PREFIX/venv/bin/pip" install --quiet -e "$PREFIX/core"
"$PREFIX/venv/bin/pip" install --quiet PySide6
chown -R "$USER_NAME:$USER_NAME" "$PREFIX"

# ---------------------------------------------------------------- cấu hình
log "Đặt file cấu hình"
[ -f /etc/karaoke/config.toml ] || cp "$REPO/deploy/config.toml.example" /etc/karaoke/config.toml
cp "$REPO/deploy/pipewire/dsp.conf" /etc/karaoke/dsp.conf

install -d /etc/pipewire/pipewire.conf.d /etc/wireplumber/wireplumber.conf.d
cp "$REPO/deploy/pipewire/10-karaoke-clock.conf" /etc/pipewire/pipewire.conf.d/
cp "$REPO/deploy/pipewire/51-karaoke-usb.conf"   /etc/wireplumber/wireplumber.conf.d/

install -d /etc/X11/xorg.conf.d
cp "$REPO"/deploy/xorg/*.conf /etc/X11/xorg.conf.d/

install -m755 "$REPO"/deploy/session/*.sh /usr/lib/karaoke/
install -m644 "$REPO/deploy/session/karaoke.desktop" /usr/share/xsessions/

install -d /etc/lightdm/lightdm.conf.d
cat > /etc/lightdm/lightdm.conf.d/50-karaoke.conf <<EOF
[Seat:*]
autologin-user=$USER_NAME
autologin-user-timeout=0
autologin-session=karaoke
user-session=karaoke
allow-guest=false
EOF

# ---------------------------------------------------------------- bảo vệ CFast
log "Giảm ghi lên thẻ CFast"
cat > /etc/sysctl.d/90-karaoke.conf <<'EOF'
vm.swappiness = 1
vm.dirty_writeback_centisecs = 1500
vm.dirty_expire_centisecs = 3000
kernel.sysrq = 0
EOF
sysctl -q --system

# Log ghi ra SSD chứ KHÔNG dùng Storage=volatile: log mất sau reboot là ác mộng
# khi phải chẩn đoán sự cố qua điện thoại với nhân viên quán.
install -d /etc/systemd/journald.conf.d
cat > /etc/systemd/journald.conf.d/karaoke.conf <<'EOF'
[Journal]
Storage=persistent
SystemMaxUse=300M
SystemMaxFileSize=50M
Compress=yes
SyncIntervalSec=60
EOF

# apt-daily tự tải index vào giờ ngẫu nhiên — có thể gây xrun giữa buổi hát.
for t in apt-daily.timer apt-daily-upgrade.timer man-db.timer e2scrub_all.timer; do
    systemctl mask "$t" 2>/dev/null || true
done

# Chặn lối thoát khỏi kiosk
for n in 2 3 4 5 6; do systemctl mask "getty@tty$n.service" 2>/dev/null || true; done

# Governor performance: ondemand/schedutil đổi tần số gây jitter -> xrun.
cat > /etc/systemd/system/cpu-performance.service <<'EOF'
[Unit]
Description=Đặt CPU governor = performance
[Service]
Type=oneshot
ExecStart=/bin/sh -c 'for g in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do echo performance > "$g" 2>/dev/null || true; done'
[Install]
WantedBy=multi-user.target
EOF
systemctl enable --now cpu-performance.service

# ---------------------------------------------------------------- mạng
log "Cấu hình web + mạng"
cp "$REPO/deploy/network/nginx-karaoke.conf" /etc/nginx/sites-available/karaoke
ln -sf /etc/nginx/sites-available/karaoke /etc/nginx/sites-enabled/karaoke
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx || systemctl restart nginx

if [ "$WITH_AP" -eq 1 ]; then
    cp "$REPO/deploy/network/hostapd.conf" /etc/hostapd/hostapd.conf
    cp "$REPO/deploy/network/dnsmasq-karaoke.conf" /etc/dnsmasq.d/karaoke.conf
    cat > /etc/systemd/network/10-wlan0.network <<'EOF'
[Match]
Name=wlan0
[Network]
Address=192.168.50.1/24
# KHÔNG cho khách ra Internet qua máy này: giảm tải, giảm rủi ro, và buộc điện
# thoại giữ kết nối với portal.
IPForward=no
ConfigureWithoutCarrier=yes
EOF
    sed -i 's/^#*DAEMON_CONF=.*/DAEMON_CONF="\/etc\/hostapd\/hostapd.conf"/' /etc/default/hostapd 2>/dev/null || true
    systemctl unmask hostapd 2>/dev/null || true
    systemctl enable systemd-networkd hostapd dnsmasq
fi

# ---------------------------------------------------------------- service
log "Cài systemd units"
USER_UNITS=/home/$USER_NAME/.config/systemd/user
install -d -o "$USER_NAME" -g "$USER_NAME" "$USER_UNITS"
install -o "$USER_NAME" -g "$USER_NAME" -m644 \
    "$REPO"/deploy/systemd/karaoke-core.service \
    "$REPO"/deploy/systemd/karaoke-dsp.service \
    "$REPO"/deploy/systemd/karaoke-ui.service "$USER_UNITS/"

install -m644 "$REPO/deploy/systemd/karaoke-backup.service" \
              "$REPO/deploy/systemd/karaoke-backup.timer" /etc/systemd/system/

systemctl daemon-reload
systemctl enable --now karaoke-backup.timer
sudo -u "$USER_NAME" XDG_RUNTIME_DIR="/run/user/$(id -u "$USER_NAME")" \
    systemctl --user daemon-reload || true
sudo -u "$USER_NAME" XDG_RUNTIME_DIR="/run/user/$(id -u "$USER_NAME")" \
    systemctl --user enable karaoke-core.service karaoke-dsp.service || true

systemctl enable lightdm

log "Xong"
cat <<'EOF'
Các bước tiếp theo:
  1. sudo ./tools/verify-hardware.sh    — điền kết quả vào docs/VERIFY.md
  2. Sửa /etc/karaoke/config.toml       — nhất là player.audio_device và player.screen
     Lấy tên node thật bằng:
       pw-dump | jq -r '.[] | select(.info.props."media.class"=="Audio/Sink") | .info.props."node.name"'
  3. Đổi ssid + wpa_passphrase trong /etc/hostapd/hostapd.conf
  4. reboot
EOF
