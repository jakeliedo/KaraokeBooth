"""Nguồn bài hát từ ổ đĩa — thư viện offline trên SSD."""

from __future__ import annotations

import logging
import sqlite3

from ..db import strip_diacritics
from ..models import PlayableMedia, SongRef, SourceKind
from .base import SongSource, SourceError

log = logging.getLogger(__name__)


class LocalSource(SongSource):
    kind = SourceKind.LOCAL

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    async def search(self, query: str, limit: int) -> list[SongRef]:
        query = query.strip()
        if not query:
            return []

        # Gõ toàn số = tra theo mã số bài, giống thao tác trên đầu karaoke thương mại.
        if query.isdigit():
            rows = self._conn.execute(
                "SELECT * FROM songs WHERE song_code LIKE ? ORDER BY song_code LIMIT ?",
                (f"{query}%", limit),
            ).fetchall()
            return [self._row_to_ref(r) for r in rows]

        needle = f"%{strip_diacritics(query)}%"
        rows = self._conn.execute(
            """SELECT * FROM songs
               WHERE path IS NOT NULL
                 AND (nodiacritic(title) LIKE ? OR nodiacritic(artist) LIKE ?)
               ORDER BY play_count DESC, title LIMIT ?""",
            (needle, needle, limit),
        ).fetchall()
        return [self._row_to_ref(r) for r in rows]

    async def resolve(self, ref: SongRef) -> PlayableMedia:
        row = self._conn.execute(
            "SELECT path FROM songs WHERE uid = ?", (ref.uid,)
        ).fetchone()
        if row is None or not row["path"]:
            raise SourceError(f"Không tìm thấy file cho {ref.uid}")
        return PlayableMedia(url=row["path"], is_local=True)

    @staticmethod
    def _row_to_ref(row: sqlite3.Row) -> SongRef:
        return SongRef(
            source=SourceKind(row["source"]),
            source_id=row["source_id"],
            title=row["title"],
            artist=row["artist"] or "",
            duration=row["duration"] or 0,
            thumbnail=row["thumbnail"] or "",
            channel=row["channel"] or "",
            song_code=row["song_code"] or "",
        )
