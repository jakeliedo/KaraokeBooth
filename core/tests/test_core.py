"""Test cho các phần chạy được mà không cần phần cứng.

Toàn bộ test suite phải chạy xanh trên máy không có mpv, không có card âm thanh và
không có mạng — nếu không thì CI và máy ảo đều vô dụng.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from karaoke_core import config as config_module
from karaoke_core.bus import EventBus
from karaoke_core.db import connect, migrate, strip_diacritics
from karaoke_core.main import create_app
from karaoke_core.models import PlayerState, SongRef, SourceKind
from karaoke_core.session import Session


@pytest.fixture
def cfg(tmp_path):
    c = config_module.Config()
    c.data_dir = tmp_path
    c.player.mpv_binary = "mpv-khong-ton-tai"  # ép chạy chế độ không có player
    c.youtube.enabled = False
    c.ensure_dirs()
    return c


@pytest.fixture
def conn(cfg):
    c = connect(cfg.db_path)
    migrate(c)
    yield c
    c.close()


# ---------------------------------------------------------------- bỏ dấu


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Em ơi Hà Nội phố", "em oi ha noi pho"),
        ("Đường tôi chở em về", "duong toi cho em ve"),
        ("NỐI VÒNG TAY LỚN", "noi vong tay lon"),
        ("Tình đơn phương", "tinh don phuong"),
    ],
)
def test_strip_diacritics(raw, expected):
    assert strip_diacritics(raw) == expected


def _seed_song(conn, source_id: str, title: str, **extra) -> None:
    """Thêm một bài local có `path` — LocalSource.resolve() chỉ cần path trong DB,
    không cần file thật, nên test chạy được ở mọi máy."""
    conn.execute(
        """INSERT INTO songs (uid, source, source_id, title, artist, path, song_code)
           VALUES (?,'local',?,?,?,?,?)""",
        (f"local:{source_id}", source_id, title, extra.get("artist", ""),
         f"/media/{source_id}.mp4", extra.get("song_code", "")),
    )
    conn.commit()


def test_local_search_khong_dau(conn, cfg):
    _seed_song(conn, "1", "Em ơi Hà Nội phố", artist="Bằng Kiều", song_code="123456")
    session = Session(cfg, conn, EventBus())

    import asyncio

    found = asyncio.run(session.local.search("ha noi", 10))
    assert len(found) == 1 and found[0].title == "Em ơi Hà Nội phố"

    by_code = asyncio.run(session.local.search("1234", 10))
    assert len(by_code) == 1


# ---------------------------------------------------------------- event bus


def test_bus_seq_tang_dan():
    bus = EventBus()
    q = bus.subscribe()
    bus.emit("a", 1)
    bus.emit("b", 2)
    assert q.get_nowait()["seq"] == 1
    assert q.get_nowait()["seq"] == 2


def test_bus_ngat_client_cham():
    bus = EventBus()
    bus.subscribe()
    for _ in range(200):
        bus.emit("spam")
    # Client không đọc kịp bị loại bỏ thay vì để hàng đợi phình vô hạn
    assert bus.subscriber_count == 0


# ---------------------------------------------------------------- hàng chờ


async def test_hang_cho_va_chuyen_bai(conn, cfg):
    session = Session(cfg, conn, EventBus())
    await session.start()  # mpv không tồn tại -> available=False, không được ném lỗi
    assert session.mpv.available is False

    _seed_song(conn, "1", "Bài A")
    song = SongRef(source=SourceKind.LOCAL, source_id="1", title="Bài A")
    await session.enqueue(song, singer="Liêm")
    snap = session.snapshot()
    assert snap["queue"]["current"]["song"]["title"] == "Bài A"
    assert snap["player"]["state"] == PlayerState.PLAYING.value

    await session.close()


async def test_khach_khong_xoa_duoc_bai_nguoi_khac(conn, cfg):
    session = Session(cfg, conn, EventBus())
    _seed_song(conn, "9", "Bài B")
    _seed_song(conn, "10", "Bài C")

    # Bài đầu vào là phát ngay, nên bài thứ hai mới là bài nằm trong hàng chờ
    await session.enqueue(SongRef(source=SourceKind.LOCAL, source_id="9", title="Bài B"))
    item = await session.enqueue(
        SongRef(source=SourceKind.LOCAL, source_id="10", title="Bài C"), added_by="phone-A"
    )

    assert session.remove(item.id, requester="phone-B") is False
    assert session.remove(item.id, requester="phone-A") is True
    assert session.queue_snapshot()["items"] == []


# ---------------------------------------------------------------- API


def test_api_chay_duoc_khi_thieu_phan_cung(cfg):
    """Ràng buộc quan trọng nhất: thiếu mpv/card âm thanh thì core vẫn phục vụ."""
    app = create_app(cfg)
    _seed_song(app.state.db, "42", "Bài C")
    with TestClient(app) as client:
        health = client.get("/api/health").json()
        assert health["ok"] is True
        assert health["mpv"] is False

        state = client.get("/api/state").json()
        assert state["player"]["state"] == PlayerState.IDLE.value
        assert state["queue"]["items"] == []

        added = client.post(
            "/api/queue",
            json={"source": "local", "source_id": "42", "title": "Bài C", "singer": "An"},
        )
        assert added.status_code == 200
        assert client.get("/api/queue").json()["current"]["song"]["title"] == "Bài C"


def test_api_tu_choi_nguon_la(cfg):
    app = create_app(cfg)
    with TestClient(app) as client:
        r = client.post("/api/queue", json={"source": "spotify", "source_id": "x", "title": "y"})
        assert r.status_code == 400
