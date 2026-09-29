#!/usr/bin/env python3
"""Sinh icon PWA (icon-192.png, icon-512.png) cho web/.

Chạy một lần khi cài đặt hoặc khi muốn cập nhật icon:
    python3 tools/gen-icons.py
"""

import io
import sys
from pathlib import Path

WEB_DIR = Path(__file__).parent.parent / "web"


def make_icon(size: int) -> bytes:
    """Sinh icon hình tròn nền tối với ký tự 🎤 màu vàng."""
    try:
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Hình tròn nền
        margin = size // 12
        draw.ellipse(
            [margin, margin, size - margin, size - margin],
            fill=(25, 29, 38),   # #191d26
        )

        # Chữ "K" to ở giữa — microphone emoji có thể không render được
        # trên mọi máy nên dùng chữ cái thay thế.
        font_size = size // 2
        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf", font_size
            )
        except OSError:
            font = ImageFont.load_default()

        text = "K"
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = (size - tw) // 2 - bbox[0]
        ty = (size - th) // 2 - bbox[1]
        draw.text((tx, ty), text, fill=(255, 176, 32), font=font)  # #ffb020

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    except ImportError:
        print("Pillow chưa cài — cần: pip install Pillow", file=sys.stderr)
        # Fallback: 1×1 PNG trong suốt
        return (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
            b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
            b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )


if __name__ == "__main__":
    for size in (192, 512):
        dest = WEB_DIR / f"icon-{size}.png"
        dest.write_bytes(make_icon(size))
        print(f"  {dest} ({size}×{size})")
    print("Xong.")
