"""Lớp truy cập SQLite.

WAL + synchronous=NORMAL: cho phép đọc trong khi ghi (core + UI + web cùng truy
cập) và chịu mất điện tốt hơn rollback journal — quán karaoke mất điện đột ngột
là chuyện thường.
"""

from __future__ import annotations

import logging
import sqlite3
import unicodedata
from pathlib import Path

log = logging.getLogger(__name__)

SCHEMA = Path(__file__).parent / "schema.sql"


def strip_diacritics(text: str) -> str:
    """'Em ơi Hà Nội phố' -> 'em oi ha noi pho' — để gõ không dấu vẫn tìm ra bài."""
    text = text.replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.create_function("nodiacritic", 1, strip_diacritics, deterministic=True)
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.commit()
    version = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()["v"]
    log.info("schema version %s", version)
