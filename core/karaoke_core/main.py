"""Điểm vào của karaoke-core.

Nguyên tắc bất biến: service này phải khởi động được **kể cả khi thiếu mpv, thiếu
thiết bị âm thanh và thiếu SSD**. Nó báo lỗi lên UI rồi tự kết nối lại khi thiết
bị xuất hiện. Nếu nó crash vì thiếu phần cứng thì không test được gì trong máy ảo.
"""

from __future__ import annotations

import contextlib
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config as config_module
from .api.routes import router
from .api.routes_admin import router as admin_router
from .bus import EventBus
from .db import connect, migrate
from .session import Session

log = logging.getLogger("karaoke")

WEB_ROOT = Path(os.environ.get("KARAOKE_WEB_ROOT", "/opt/karaoke/web"))


def create_app(cfg=None) -> FastAPI:
    cfg = cfg or config_module.load()
    cfg.ensure_dirs()

    conn = connect(cfg.db_path)
    migrate(conn)

    bus = EventBus()
    session = Session(cfg, conn, bus)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await session.start()
        if not session.mpv.available:
            log.warning("mpv chua san sang — UI se hien canh bao, core van chay")
        yield
        await session.close()
        with contextlib.suppress(Exception):
            conn.close()

    app = FastAPI(title="KaraokeBooth", version="0.1.0", docs_url="/api/docs",
                  lifespan=lifespan)
    app.include_router(router)
    app.include_router(admin_router)

    app.state.cfg = cfg
    app.state.db = conn
    app.state.bus = bus
    app.state.session = session

    # PWA cho điện thoại. Trên máy thật nginx phục vụ tĩnh cho nhanh; ở đây phục
    # vụ trực tiếp để chạy được ngay trong máy ảo mà không cần dựng nginx.
    if WEB_ROOT.is_dir():
        app.mount("/app", StaticFiles(directory=WEB_ROOT, html=True), name="web")

        @app.get("/")
        async def _index():
            return FileResponse(WEB_ROOT / "index.html")

    return app


def run() -> None:
    logging.basicConfig(
        level=os.environ.get("KARAOKE_LOG", "INFO").upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    cfg = config_module.load()
    uvicorn.run(
        create_app(cfg),
        host=cfg.network.host,
        port=cfg.network.port,
        log_config=None,
        access_log=False,
    )


if __name__ == "__main__":
    run()
