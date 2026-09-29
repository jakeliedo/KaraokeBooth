"""Endpoint quản trị: QR code, thông tin hệ thống, cập nhật yt-dlp.

QR code là đường vào chính cho khách:
  QR1 — WiFi: quét bằng camera là tự nối, không cần gõ mật khẩu.
  QR2 — App:  mở trực tiếp http://192.168.50.1/ (hoặc http://karaoke.box/).

Cả hai ảnh được cache trong bộ nhớ sau lần render đầu (hình ảnh không thay đổi
giữa các lần restart trừ khi file cấu hình thay đổi).
"""

from __future__ import annotations

import logging
import subprocess

from fastapi import APIRouter, Request
from fastapi.responses import Response

from ..qr_util import make_idle_image, make_qr_png

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin")

# Cache ảnh trong process — hình chỉ thay đổi khi cấu hình thay đổi.
_qr_cache: dict[str, bytes] = {}


def invalidate_qr_cache() -> None:
    """Gọi khi cấu hình WiFi thay đổi để QR được sinh lại."""
    _qr_cache.clear()


@router.get("/qr/wifi.png", responses={200: {"content": {"image/png": {}}}})
async def qr_wifi(request: Request):
    """QR WIFI: quét là tự nối mạng karaoke, không cần gõ mật khẩu."""
    cfg = request.app.state.cfg
    if "wifi" not in _qr_cache:
        ap = cfg.network
        psk = getattr(ap, "ap_psk", "")
        auth = "WPA" if psk else "nopass"
        ssid = getattr(ap, "ap_ssid", "KaraokeBox")
        wifi_str = f"WIFI:S:{ssid};T:{auth};P:{psk};;"
        _qr_cache["wifi"] = make_qr_png(wifi_str)
    return Response(content=_qr_cache["wifi"], media_type="image/png")


@router.get("/qr/app.png", responses={200: {"content": {"image/png": {}}}})
async def qr_app(request: Request):
    """QR URL app điện thoại."""
    cfg = request.app.state.cfg
    if "app" not in _qr_cache:
        url = f"http://{cfg.network.ap_address}/"
        _qr_cache["app"] = make_qr_png(url)
    return Response(content=_qr_cache["app"], media_type="image/png")


@router.get("/qr/idle.png", responses={200: {"content": {"image/png": {}}}})
async def qr_idle(request: Request):
    """Ảnh kết hợp WiFi + App QR hiển thị trên TV khi rảnh."""
    cfg = request.app.state.cfg
    if "idle" not in _qr_cache:
        _qr_cache["idle"] = make_idle_image(cfg)
    return Response(content=_qr_cache["idle"], media_type="image/png")


@router.post("/ytdlp/update")
async def update_ytdlp():
    """Cập nhật yt-dlp — nút này trên màn Cài đặt."""
    try:
        result = subprocess.run(
            ["/opt/karaoke/venv/bin/pip", "install", "--upgrade", "yt-dlp"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            last_line = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "ok"
            return {"ok": True, "detail": last_line}
        return {"ok": False, "detail": result.stderr.strip()}
    except subprocess.TimeoutExpired:
        return {"ok": False, "detail": "Hết thời gian chờ"}
    except FileNotFoundError:
        return {"ok": False, "detail": "Không tìm thấy pip trong venv"}
