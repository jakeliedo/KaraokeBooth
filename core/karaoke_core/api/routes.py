"""REST API + WebSocket.

Màn hình cảm ứng và app điện thoại dùng **cùng một API này**. Khác biệt duy nhất:
client điện thoại gửi kèm `client_id` và bị giới hạn quyền (chỉ xóa được bài của
chính mình, không điều khiển phát/dừng trừ khi bật "chế độ tiệc").
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from ..models import SongRef, SourceKind

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


def _session(request: Request):
    return request.app.state.session


# ---------------------------------------------------------------- schemas


class EnqueueBody(BaseModel):
    source: str
    source_id: str
    title: str
    artist: str = ""
    channel: str = ""
    duration: int = 0
    thumbnail: str = ""
    singer: str = ""
    client_id: str = ""


class ReorderBody(BaseModel):
    item_id: str
    index: int = Field(ge=0)


class SeekBody(BaseModel):
    seconds: float
    mode: str = "absolute"


class VolumeBody(BaseModel):
    volume: int | None = None
    muted: bool | None = None


class PitchBody(BaseModel):
    semitones: int


class TempoBody(BaseModel):
    ratio: float


# ---------------------------------------------------------------- state


@router.get("/state")
async def get_state(request: Request):
    """Client gọi khi mới kết nối, và khi phát hiện `seq` nhảy cóc."""
    return _session(request).snapshot()


@router.get("/health")
async def health(request: Request):
    s = _session(request)
    return {
        "ok": True,
        "mpv": s.mpv.available,
        "youtube": s._cfg.youtube.enabled,
    }


# ---------------------------------------------------------------- tìm kiếm


@router.get("/search")
async def search(
    request: Request,
    q: str = Query(min_length=1, max_length=120),
    source: str = Query("all", pattern="^(all|local|youtube)$"),
    limit: int = Query(20, ge=1, le=50),
):
    return await _session(request).search(q, source, limit)


# ---------------------------------------------------------------- hàng chờ


@router.get("/queue")
async def get_queue(request: Request):
    return _session(request).queue_snapshot()


@router.post("/queue")
async def enqueue(request: Request, body: EnqueueBody):
    try:
        kind = SourceKind(body.source)
    except ValueError:
        raise HTTPException(400, f"nguồn không hợp lệ: {body.source}") from None

    song = SongRef(
        source=kind,
        source_id=body.source_id,
        title=body.title,
        artist=body.artist,
        channel=body.channel,
        duration=body.duration,
        thumbnail=body.thumbnail,
    )
    item = await _session(request).enqueue(song, body.singer, body.client_id)
    return item.to_dict()


@router.delete("/queue/{item_id}")
async def dequeue(request: Request, item_id: str, client_id: str | None = None):
    if not _session(request).remove(item_id, client_id):
        raise HTTPException(404, "không tìm thấy bài, hoặc bài này không phải của bạn")
    return {"ok": True}


@router.post("/queue/reorder")
async def reorder(request: Request, body: ReorderBody):
    if not _session(request).reorder(body.item_id, body.index):
        raise HTTPException(404, "không tìm thấy bài")
    return {"ok": True}


# ---------------------------------------------------------------- điều khiển phát


@router.post("/player/play")
async def play(request: Request):
    await _session(request).player.play()
    return {"ok": True}


@router.post("/player/pause")
async def pause(request: Request):
    await _session(request).player.pause()
    return {"ok": True}


@router.post("/player/toggle")
async def toggle(request: Request):
    await _session(request).player.toggle_pause()
    return {"ok": True}


@router.post("/player/next")
async def next_song(request: Request):
    await _session(request).play_next()
    return {"ok": True}


@router.post("/player/replay")
async def replay(request: Request):
    await _session(request).player.restart()
    return {"ok": True}


@router.post("/player/seek")
async def seek(request: Request, body: SeekBody):
    await _session(request).player.seek(body.seconds, body.mode)
    return {"ok": True}


# ---------------------------------------------------------------- mixer (nhạc)


@router.post("/mixer/volume")
async def set_volume(request: Request, body: VolumeBody):
    player = _session(request).player
    if body.volume is not None:
        await player.set_volume(body.volume)
    if body.muted is not None:
        await player.set_mute(body.muted)
    return player.snapshot()


@router.post("/mixer/pitch")
async def set_pitch(request: Request, body: PitchBody):
    player = _session(request).player
    await player.set_pitch(body.semitones)
    return player.snapshot()


@router.post("/mixer/tempo")
async def set_tempo(request: Request, body: TempoBody):
    player = _session(request).player
    await player.set_tempo(body.ratio)
    return player.snapshot()


# ---------------------------------------------------------------- WebSocket


@router.websocket("/ws")
async def websocket(ws: WebSocket):
    await ws.accept()
    bus = ws.app.state.bus
    session = ws.app.state.session
    queue = bus.subscribe()
    try:
        await ws.send_json({"seq": 0, "event": "snapshot", "data": session.snapshot()})
        while True:
            message = await queue.get()
            await ws.send_json(message)
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception as exc:
        log.debug("websocket dong: %s", exc)
    finally:
        bus.unsubscribe(queue)
