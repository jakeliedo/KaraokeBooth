"""karaoke_core — service lõi của hệ thống karaoke.

Đây là nguồn sự thật duy nhất của toàn hệ thống. Màn hình cảm ứng (PySide6) và
app điện thoại (PWA) đều chỉ là client của REST API + WebSocket ở đây; không có
state nào được giữ riêng trong UI.
"""

__version__ = "0.1.0"
