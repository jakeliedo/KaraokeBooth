"""Giao diện màn hình cảm ứng.

Đây là **client thuần** của karaoke-core, không giữ state riêng: mọi thao tác gửi
qua REST, mọi thay đổi nhận qua WebSocket. Nhờ vậy màn cảm ứng và điện thoại luôn
hiển thị giống nhau, và UI crash không làm mất bài đang hát.

Quy tắc luồng bắt buộc: thread đọc WebSocket **không được chạm vào đối tượng Qt**.
Mọi dữ liệu đi qua Signal với Qt.QueuedConnection. Vi phạm quy tắc này gây crash
ngẫu nhiên sau nhiều giờ chạy — loại lỗi rất khó tái hiện và rất khó debug.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

log = logging.getLogger("karaoke.ui")

API = os.environ.get("KARAOKE_API", "http://127.0.0.1:8080")
QML_DIR = Path(__file__).parent.parent / "qml"


class Backend(QObject):
    """Cầu nối giữa QML và karaoke-core."""

    stateChanged = Signal()
    connectionChanged = Signal()
    searchResults = Signal(list, str)
    ytdlpUpdateDone = Signal(bool, str)

    def __init__(self) -> None:
        super().__init__()
        self._state: dict = {"player": {}, "queue": {"items": [], "current": None}}
        self._connected = False
        self._stop = threading.Event()
        threading.Thread(target=self._ws_loop, daemon=True, name="ws").start()

    # ---------------------------------------------------------------- state

    @Property("QVariant", notify=stateChanged)
    def state(self) -> dict:
        return self._state

    @Property(bool, notify=connectionChanged)
    def connected(self) -> bool:
        return self._connected

    def _set_state(self, state: dict) -> None:
        self._state = state
        self.stateChanged.emit()

    # ---------------------------------------------------------------- lệnh

    @Slot(str)
    def search(self, query: str) -> None:
        def work() -> None:
            try:
                data = self._get(f"/api/search?q={urllib.parse.quote(query)}")
                self.searchResults.emit(data.get("results", []), data.get("error") or "")
            except OSError as exc:
                self.searchResults.emit([], f"Không tìm được: {exc}")

        threading.Thread(target=work, daemon=True).start()

    @Slot("QVariant", str)
    def enqueue(self, song: dict, singer: str) -> None:
        body = {k: song.get(k) for k in
                ("source", "source_id", "title", "artist", "channel", "duration", "thumbnail")}
        body["singer"] = singer
        self._post_async("/api/queue", body)

    @Slot(str)
    def removeItem(self, item_id: str) -> None:
        # Màn cảm ứng là quyền quản trị: không gửi client_id nên xoá được mọi bài.
        self._request_async("DELETE", f"/api/queue/{item_id}")

    @Slot()
    def togglePause(self) -> None:
        self._post_async("/api/player/toggle", {})

    @Slot()
    def playNext(self) -> None:
        self._post_async("/api/player/next", {})

    @Slot()
    def replay(self) -> None:
        self._post_async("/api/player/replay", {})

    @Slot(int)
    def setVolume(self, value: int) -> None:
        self._post_async("/api/mixer/volume", {"volume": value})

    @Slot(int)
    def setPitch(self, semitones: int) -> None:
        self._post_async("/api/mixer/pitch", {"semitones": semitones})

    @Slot(float)
    def setTempo(self, ratio: float) -> None:
        self._post_async("/api/mixer/tempo", {"ratio": ratio})

    @Slot()
    def swapDisplays(self) -> None:
        """Hoán đổi vai trò hai màn hình — gọi script detect-displays."""
        import subprocess
        threading.Thread(
            target=lambda: subprocess.run(
                ["/opt/karaoke/deploy/session/detect-displays.sh", "--swap"],
                check=False,
            ),
            daemon=True,
        ).start()

    @Slot()
    def updateYtdlp(self) -> None:
        def work() -> None:
            try:
                data = self._post_sync("/api/admin/ytdlp/update", {})
                self.ytdlpUpdateDone.emit(data.get("ok", False), data.get("detail", ""))
            except OSError as exc:
                self.ytdlpUpdateDone.emit(False, f"Lỗi kết nối: {exc}")

        threading.Thread(target=work, daemon=True).start()

    # ---------------------------------------------------------------- HTTP

    def _get(self, path: str) -> dict:
        with urllib.request.urlopen(API + path, timeout=15) as resp:
            return json.loads(resp.read())

    def _post_async(self, path: str, body: dict) -> None:
        self._request_async("POST", path, body)

    def _post_sync(self, path: str, body: dict) -> dict:
        """POST đồng bộ — chỉ gọi từ thread nền, không bao giờ từ Qt thread."""
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            API + path, data=data, method="POST",
            headers={"content-type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read())

    def _request_async(self, method: str, path: str, body: dict | None = None) -> None:
        def work() -> None:
            data = json.dumps(body).encode() if body is not None else None
            req = urllib.request.Request(
                API + path, data=data, method=method,
                headers={"content-type": "application/json"},
            )
            try:
                urllib.request.urlopen(req, timeout=15).read()
            except (OSError, urllib.error.HTTPError) as exc:
                log.warning("%s %s that bai: %s", method, path, exc)

        threading.Thread(target=work, daemon=True).start()

    # ---------------------------------------------------------------- WebSocket

    def _ws_loop(self) -> None:
        """Bám theo core, tự kết nối lại. Core có thể lên sau UI nên phải chịu lỗi.

        Dùng long-poll /api/state thay vì thư viện WebSocket để không thêm phụ
        thuộc vào UI; nhịp 1 giây là đủ cho màn điều khiển (vị trí phát được core
        throttle sẵn ở 5Hz). Chuyển sang WebSocket thật khi cần mượt hơn.
        """
        import time

        while not self._stop.is_set():
            try:
                state = self._get("/api/state")
                if not self._connected:
                    self._connected = True
                    self.connectionChanged.emit()
                self._set_state(state)
                time.sleep(1.0)
            except OSError:
                if self._connected:
                    self._connected = False
                    self.connectionChanged.emit()
                time.sleep(2.0)


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    app = QGuiApplication(sys.argv)
    app.setApplicationName("KaraokeBooth")

    engine = QQmlApplicationEngine()
    backend = Backend()
    engine.rootContext().setContextProperty("backend", backend)
    engine.load(QUrl.fromLocalFile(str(QML_DIR / "Main.qml")))

    if not engine.rootObjects():
        log.error("khong nap duoc QML tu %s", QML_DIR)
        return 1
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
