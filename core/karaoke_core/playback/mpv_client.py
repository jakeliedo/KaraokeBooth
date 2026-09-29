"""Client JSON IPC cho mpv.

mpv chạy như một **tiến trình riêng**, không nhúng libmpv vào app. Ba lý do:

- mpv crash chỉ mất video, UI và tiếng vẫn sống; ta tự khởi động lại và khôi phục
  bài đang phát.
- Không phải nhúng video vào widget Qt — đó là phần khó nhất của mọi dự án loại
  này (mpv `--wid` tạo native child window, widget Qt vẽ đè lên sẽ không hiện).
- Vị thế giấy phép sạch hơn: gọi qua tiến trình thay vì link libmpv (GPL).

Giao thức: JSON phân tách bằng '\\n' trên unix socket.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger(__name__)

_OBSERVED = ("time-pos", "duration", "pause", "eof-reached", "path", "media-title")


class MpvClient:
    """Một instance mpv thường trú, dùng chung cho mọi backend.

    `--idle --force-window --keep-open` giữ cửa sổ TV luôn tồn tại giữa các bài nên
    chuyển bài **không nháy đen**. Chuyển bài bằng lệnh `loadfile`, không bao giờ
    tắt rồi mở lại mpv.
    """

    def __init__(self, cfg, on_property: Callable[[str, object], None] | None = None) -> None:
        self._cfg = cfg
        self._on_property = on_property or (lambda name, value: None)
        self._proc: asyncio.subprocess.Process | None = None
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._pending: dict[int, asyncio.Future] = {}
        self._req_id = 0
        self._reader_task: asyncio.Task | None = None
        self._restart_task: asyncio.Task | None = None
        self._available = False

    @property
    def available(self) -> bool:
        """False khi không có mpv (máy phát triển, VM chưa cài). Core vẫn phải chạy."""
        return self._available

    # ------------------------------------------------------------------ lifecycle

    def _argv(self) -> list[str]:
        c = self._cfg
        return [
            c.mpv_binary,
            "--idle=yes", "--force-window=yes", "--keep-open=yes",
            "--no-config", "--no-terminal", "--really-quiet",
            f"--input-ipc-server={c.ipc_socket}",
            "--fullscreen", f"--screen={c.screen}", f"--fs-screen={c.screen}",
            "--ontop", "--no-osc", "--osd-level=0",
            "--no-input-default-bindings", "--input-vo-keyboard=no",
            "--cursor-autohide=always",
            "--vo=gpu", "--hwdec=auto-safe",
            "--video-sync=display-resample",
            *(
                [f"--audio-device={c.audio_device}"]
                if getattr(c, "audio_device", "") not in ("", "auto")
                else []
            ),
            f"--volume={c.volume}", f"--volume-max={c.volume_max}",
            "--audio-pitch-correction=yes",
            "--sub-auto=no",
        ]

    async def start(self) -> bool:
        sock = Path(self._cfg.ipc_socket)
        sock.parent.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(FileNotFoundError):
            sock.unlink()

        try:
            self._proc = await asyncio.create_subprocess_exec(
                *self._argv(),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except FileNotFoundError:
            log.warning("khong tim thay mpv (%s) — chay o che do khong co player",
                        self._cfg.mpv_binary)
            return False

        if not await self._wait_for_socket(sock):
            log.warning("mpv khong tao duoc socket IPC")
            await self.stop()
            return False

        self._reader, self._writer = await asyncio.open_unix_connection(str(sock))
        self._reader_task = asyncio.create_task(self._read_loop(), name="mpv-reader")
        for prop in _OBSERVED:
            await self.command("observe_property", _OBSERVED.index(prop) + 1, prop)
        self._available = True
        log.info("mpv san sang (pid=%s, man hinh %s)", self._proc.pid, self._cfg.screen)
        return True

    @staticmethod
    async def _wait_for_socket(sock: Path, timeout: float = 5.0) -> bool:
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            if sock.exists() or os.path.exists(sock):
                return True
            await asyncio.sleep(0.05)
        return False

    async def stop(self) -> None:
        self._available = False
        if self._restart_task and not self._restart_task.done():
            self._restart_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._restart_task
        if self._reader_task:
            self._reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader_task
        if self._writer:
            self._writer.close()
            with contextlib.suppress(Exception):
                await self._writer.wait_closed()
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._proc.wait(), timeout=3)

    # ------------------------------------------------------------------ IPC

    async def command(self, *args) -> object:
        if not self._writer:
            raise RuntimeError("mpv chua san sang")
        self._req_id += 1
        req_id = self._req_id
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[req_id] = fut
        payload = json.dumps({"command": list(args), "request_id": req_id}) + "\n"
        self._writer.write(payload.encode())
        await self._writer.drain()
        try:
            return await asyncio.wait_for(fut, timeout=5)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise

    async def set_property(self, name: str, value) -> None:
        await self.command("set_property", name, value)

    async def get_property(self, name: str):
        return await self.command("get_property", name)

    async def loadfile(self, path: str) -> None:
        await self.command("loadfile", path, "replace")

    async def _read_loop(self) -> None:
        assert self._reader
        while True:
            try:
                line = await self._reader.readline()
            except (ConnectionResetError, asyncio.IncompleteReadError):
                line = b""
            if not line:
                log.warning("mpv dong ket noi IPC")
                self._available = False
                self._restart_task = asyncio.create_task(self._restart())
                return
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            if "request_id" in msg:
                fut = self._pending.pop(msg["request_id"], None)
                if fut and not fut.done():
                    if msg.get("error") == "success":
                        fut.set_result(msg.get("data"))
                    else:
                        fut.set_exception(RuntimeError(msg.get("error", "loi khong ro")))
            elif msg.get("event") == "property-change":
                # Chạy trong event loop của core; tầng trên tự throttle trước khi
                # broadcast, không phát mỗi frame ra WebSocket.
                self._on_property(msg.get("name", ""), msg.get("data"))
            elif msg.get("event"):
                self._on_property(f"event:{msg['event']}", None)

    async def _restart(self) -> None:
        """mpv chết giữa buổi hát thì phải tự sống lại, không chờ người can thiệp."""
        await asyncio.sleep(1)
        log.info("khoi dong lai mpv")
        await self.stop()
        await self.start()
