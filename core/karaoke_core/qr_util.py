"""Tạo QR code và ảnh màn chờ TV.

Tách thành module riêng để tránh circular import giữa session.py và routes_admin.py.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- QR đơn


def make_qr_png(data: str, box_size: int = 10, border: int = 4) -> bytes:
    """Sinh QR code PNG. Nền trắng để camera đọc dễ hơn nền tối."""
    try:
        import qrcode
        from qrcode.image.pil import PilImage

        img = qrcode.make(
            data,
            image_factory=PilImage,
            box_size=box_size,
            border=border,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
        )
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        log.warning("thư viện qrcode chưa cài — chạy: pip install qrcode[pil]")
        return _minimal_png()


# --------------------------------------------------------------------------- Idle image


def make_idle_image(cfg) -> bytes:
    """Ghép QR WiFi + QR App + text hướng dẫn thành ảnh hiển thị trên TV."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        import qrcode

        W = getattr(getattr(cfg, "player", None), "screen_width", 1920)
        H = getattr(getattr(cfg, "player", None), "screen_height", 1080)
        BG = (15, 17, 21)        # #0f1115
        TEXT = (242, 244, 248)   # #f2f4f8
        ACCENT = (255, 176, 32)  # #ffb020

        canvas = Image.new("RGB", (W, H), BG)
        draw = ImageDraw.Draw(canvas)

        ap = cfg.network
        psk = getattr(ap, "ap_psk", "")
        auth = "WPA" if psk else "nopass"
        ssid = getattr(ap, "ap_ssid", "KaraokeBox")
        wifi_str = f"WIFI:S:{ssid};T:{auth};P:{psk};;"
        app_url = f"http://{ap.ap_address}/"

        def _qr_img(data: str, size: int = 420) -> Image.Image:
            qr = qrcode.QRCode(
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=10, border=2,
            )
            qr.add_data(data)
            qr.make(fit=True)
            return qr.make_image(fill_color="black", back_color="white")\
                     .convert("RGB").resize((size, size), Image.LANCZOS)

        qr_size = 420
        margin = 80
        qr_wifi = _qr_img(wifi_str, qr_size)
        qr_app  = _qr_img(app_url, qr_size)

        y_qr  = (H - qr_size) // 2 - 60
        x_wifi = W // 2 - qr_size - margin // 2
        x_app  = W // 2 + margin // 2

        canvas.paste(qr_wifi, (x_wifi, y_qr))
        canvas.paste(qr_app,  (x_app,  y_qr))

        # Font: thử Noto (đã cài trong provision.sh), fallback về PIL default
        def _font(size: int, bold: bool = False) -> "ImageFont.FreeTypeFont":
            base = "/usr/share/fonts/truetype/noto/NotoSans"
            name = f"{base}-Bold.ttf" if bold else f"{base}-Regular.ttf"
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                return ImageFont.load_default()

        draw.text((W // 2, 80),  "Chào mừng đến karaoke!",
                  font=_font(64, bold=True), fill=ACCENT, anchor="mm")
        draw.text((W // 2, 160), "Quét mã để bắt đầu chọn bài",
                  font=_font(36), fill=TEXT, anchor="mm")

        y_label = y_qr + qr_size + 28
        draw.text((x_wifi + qr_size // 2, y_label), "① Kết nối WiFi",
                  font=_font(34, bold=True), fill=ACCENT, anchor="mm")
        draw.text((x_wifi + qr_size // 2, y_label + 48), ssid,
                  font=_font(28), fill=TEXT, anchor="mm")

        draw.text((x_app + qr_size // 2, y_label), "② Mở ứng dụng",
                  font=_font(34, bold=True), fill=ACCENT, anchor="mm")
        draw.text((x_app + qr_size // 2, y_label + 48), app_url,
                  font=_font(28), fill=TEXT, anchor="mm")

        buf = io.BytesIO()
        canvas.save(buf, format="PNG", optimize=True)
        return buf.getvalue()

    except Exception as exc:
        log.warning("khong tao duoc idle image: %s — fallback QR app", exc)
        return make_qr_png(f"http://{cfg.network.ap_address}/", box_size=20, border=6)


def write_idle_image(cfg, dest: Path) -> bool:
    """Sinh ảnh và ghi ra file. Trả về True nếu thành công."""
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(make_idle_image(cfg))
        log.info("idle image -> %s", dest)
        return True
    except Exception as exc:
        log.warning("khong ghi duoc idle image: %s", exc)
        return False


# --------------------------------------------------------------------------- helper


def _minimal_png() -> bytes:
    """1×1 pixel transparent PNG — fallback khi qrcode chưa cài."""
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
        b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
