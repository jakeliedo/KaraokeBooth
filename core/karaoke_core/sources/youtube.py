"""Nguồn YouTube qua yt-dlp.

Ba quyết định thiết kế đáng nhớ:

1. Gọi yt-dlp bằng **API Python trong tiến trình**, không spawn subprocess mỗi lần
   — fork tốn 200-500ms và tạo rác process khi khách gõ liên tục. Chạy trong
   thread pool vì yt-dlp là code đồng bộ.
2. **Tải hẳn về cache trước khi phát**, không stream trực tiếp. Mạng quán chập
   chờn thì bài đang hát không được phép giật.
3. Mọi bài đã tải được ghi vào bảng `songs` → thư viện offline tự lớn dần và bớt
   phụ thuộc vào YouTube.

yt-dlp sẽ hỏng mỗi khi YouTube đổi giao diện — đó là chuyện khi nào chứ không
phải có hay không. Vì vậy màn Cài đặt có nút cập nhật yt-dlp, và khi nguồn này
lỗi thì UI phải rơi về thư viện local chứ không được chết.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..models import PlayableMedia, SongRef, SourceKind
from .base import SongSource, SourceError

log = logging.getLogger(__name__)

_FORMAT = "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]/best"


class YouTubeSource(SongSource):
    kind = SourceKind.YOUTUBE

    def __init__(self, conn: sqlite3.Connection, cache_dir: Path, cfg) -> None:
        self._conn = conn
        self._cache = cache_dir
        self._cfg = cfg
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ytdlp")
        self._downloading: dict[str, asyncio.Task] = {}
        self._cache.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ search

    async def search(self, query: str, limit: int) -> list[SongRef]:
        query = query.strip()
        if not query:
            return []

        cached = self._read_cache(query)
        if cached is not None:
            return cached

        loop = asyncio.get_running_loop()
        try:
            raw = await loop.run_in_executor(self._pool, self._search_blocking, query, limit)
        except Exception as exc:  # yt-dlp ném đủ loại exception, không bắt hẹp được
            log.warning("tim kiem YouTube loi: %s", exc)
            raise SourceError("Không kết nối được YouTube") from exc

        refs = [r for r in (self._entry_to_ref(e) for e in raw) if r is not None]
        self._write_cache(query, refs)
        return refs

    def _search_blocking(self, query: str, limit: int) -> list[dict]:
        from yt_dlp import YoutubeDL

        term = f"ytsearch{limit}:{query} {self._cfg.search_suffix}".strip()
        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": True,  # không giải mã từng video -> nhanh hơn nhiều
            "default_search": "ytsearch",
            "socket_timeout": 10,
        }
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(term, download=False)
        return info.get("entries") or []

    def _entry_to_ref(self, entry: dict) -> SongRef | None:
        if not entry or not entry.get("id"):
            return None
        duration = int(entry.get("duration") or 0)
        # Lọc video quá ngắn (trailer) và quá dài (playlist liền mạch nhiều giờ)
        if duration and not (self._cfg.min_duration <= duration <= self._cfg.max_duration):
            return None
        return SongRef(
            source=SourceKind.YOUTUBE,
            source_id=entry["id"],
            title=entry.get("title") or "(không có tiêu đề)",
            channel=entry.get("uploader") or entry.get("channel") or "",
            duration=duration,
            thumbnail=(entry.get("thumbnails") or [{}])[0].get("url", ""),
        )

    # ------------------------------------------------------------------ resolve

    async def resolve(self, ref: SongRef) -> PlayableMedia:
        path = self._cached_file(ref.source_id)
        if path is not None:
            return PlayableMedia(url=str(path), is_local=True)

        task = self._downloading.get(ref.source_id)
        if task is None:
            task = asyncio.create_task(self._download(ref))
            self._downloading[ref.source_id] = task
        path = await task
        return PlayableMedia(url=str(path), is_local=True)

    async def prefetch(self, ref: SongRef) -> None:
        if not self._cfg.prefetch or self._cached_file(ref.source_id):
            return
        if ref.source_id not in self._downloading:
            self._downloading[ref.source_id] = asyncio.create_task(self._download(ref))

    async def _download(self, ref: SongRef) -> Path:
        self._free_space_if_needed()
        loop = asyncio.get_running_loop()
        try:
            path = await loop.run_in_executor(self._pool, self._download_blocking, ref.source_id)
        except Exception as exc:
            log.warning("tai %s loi: %s", ref.source_id, exc)
            raise SourceError(f"Không tải được bài: {ref.title}") from exc
        finally:
            self._downloading.pop(ref.source_id, None)
        self._record(ref, path)
        return path

    def _download_blocking(self, video_id: str) -> Path:
        from yt_dlp import YoutubeDL

        opts = {
            "quiet": True,
            "no_warnings": True,
            "format": _FORMAT,
            "merge_output_format": "mp4",
            "outtmpl": str(self._cache / "%(id)s.%(ext)s"),
            "noplaylist": True,
            "socket_timeout": 15,
            "retries": 3,
        }
        with YoutubeDL(opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
        path = self._cached_file(video_id)
        if path is None:
            raise SourceError(f"yt-dlp báo xong nhưng không thấy file cho {video_id}")
        return path

    def _cached_file(self, video_id: str) -> Path | None:
        for candidate in self._cache.glob(f"{video_id}.*"):
            if candidate.suffix not in (".part", ".ytdl") and candidate.stat().st_size > 0:
                return candidate
        return None

    # ------------------------------------------------------------------ cache

    def _free_space_if_needed(self) -> None:
        """Dọn cache theo LRU. Bài được ghim (`pinned`) thì không bao giờ xóa."""
        usage = shutil.disk_usage(self._cache)
        if usage.free / usage.total * 100 >= self._cfg.keep_free_percent:
            return
        rows = self._conn.execute(
            """SELECT uid, path FROM songs
               WHERE source='youtube' AND path IS NOT NULL AND pinned=0
               ORDER BY COALESCE(last_played, added_at) ASC LIMIT 20"""
        ).fetchall()
        for row in rows:
            try:
                Path(row["path"]).unlink(missing_ok=True)
            except OSError as exc:
                log.warning("khong xoa duoc %s: %s", row["path"], exc)
                continue
            self._conn.execute("UPDATE songs SET path=NULL WHERE uid=?", (row["uid"],))
            log.info("don cache: %s", row["path"])
            usage = shutil.disk_usage(self._cache)
            if usage.free / usage.total * 100 >= self._cfg.keep_free_percent:
                break
        self._conn.commit()

    def _record(self, ref: SongRef, path: Path) -> None:
        """Ghi bài đã tải vào thư viện — đây là cách thư viện offline tự lớn dần."""
        self._conn.execute(
            """INSERT INTO songs (uid, source, source_id, title, artist, channel,
                                  duration, path, thumbnail, format)
               VALUES (?,?,?,?,?,?,?,?,?,'video')
               ON CONFLICT(uid) DO UPDATE SET path=excluded.path""",
            (ref.uid, ref.source.value, ref.source_id, ref.title, ref.artist,
             ref.channel, ref.duration, str(path), ref.thumbnail),
        )
        self._conn.commit()

    def _read_cache(self, query: str) -> list[SongRef] | None:
        row = self._conn.execute(
            "SELECT payload, fetched_at FROM yt_cache WHERE query=?", (query,)
        ).fetchone()
        if row is None:
            return None
        if time.time() - row["fetched_at"] > self._cfg.cache_ttl_hours * 3600:
            return None
        return [
            SongRef(source=SourceKind.YOUTUBE, **item)
            for item in json.loads(row["payload"])
        ]

    def _write_cache(self, query: str, refs: list[SongRef]) -> None:
        skip = {"source", "uid"}
        payload = json.dumps(
            [{k: v for k, v in r.to_dict().items() if k not in skip} for r in refs],
            ensure_ascii=False,
        )
        self._conn.execute(
            "INSERT OR REPLACE INTO yt_cache (query, payload, fetched_at) VALUES (?,?,?)",
            (query, payload, time.time()),
        )
        self._conn.commit()

    async def close(self) -> None:
        for task in list(self._downloading.values()):
            task.cancel()
        self._pool.shutdown(wait=False)
