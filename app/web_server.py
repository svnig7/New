import asyncio
import json
import logging
import mimetypes
import os
import time

from aiohttp import web
from jinja2 import Environment, FileSystemLoader

from .byte_streamer import stream_chunks
from .client_manager import client_manager
from .config import Config
from .media_store import media_store
from .playlist_store import playlist_store
from .remux import remux_to_mp4
from .subtitle_utils import ass_to_vtt, srt_to_vtt
from .token_utils import TYPE_FILE, TYPE_PLAYLIST, TYPE_SUB, decode_token, encode_token

logger = logging.getLogger(__name__)
routes = web.RouteTableDef()

# Containers Chrome/most browsers won't play natively in a <video> tag,
# even when the codecs inside (H.264/AAC) are otherwise fine. These get
# routed through /remux instead of /stream for inline playback.
REMUX_MIMES = {"video/x-matroska", "video/x-msvideo", "video/x-flv"}
REMUX_EXTS = (".mkv", ".avi", ".flv")


def _needs_remux(mime: str, name: str) -> bool:
    return mime in REMUX_MIMES or name.lower().endswith(REMUX_EXTS)

_env = Environment(
    loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), "templates"))
)
_watch_template = _env.get_template("watch.html")
_playlist_template = _env.get_template("playlist.html")
_index_template = _env.get_template("index.html")


def _media_of(msg):
    return (
        msg.document
        or msg.video
        or msg.audio
        or msg.animation
        or msg.voice
        or msg.photo
    )


def _file_meta(media):
    name = getattr(media, "file_name", None) or f"file_{media.file_unique_id}"
    size = getattr(media, "file_size", 0) or 0
    mime = (
        getattr(media, "mime_type", "")
        or mimetypes.guess_type(name)[0]
        or "application/octet-stream"
    )
    return name, size, mime


async def _get_message(message_id: int):
    return await client_manager.primary.get_messages(Config.LOG_CHANNEL, message_id)


async def _resolve_file(token: str):
    decoded = decode_token(token)
    if not decoded or decoded["kind"] != TYPE_FILE:
        return None
    msg = await _get_message(decoded["ref_id"])
    if not msg or msg.empty:
        return None
    media = _media_of(msg)
    if not media:
        return None
    return msg, media, decoded["expire_at"]


def _remaining_ttl(expire_at: int) -> int:
    return max(int(expire_at - time.time()), 0) if expire_at else 0


@routes.get("/watch/{token}")
async def watch(request: web.Request):
    token = request.match_info["token"]
    resolved = await _resolve_file(token)
    if not resolved:
        raise web.HTTPNotFound(text="Link expired or invalid.")
    msg, media, expire_at = resolved
    name, size, mime = _file_meta(media)
    meta = await media_store.get(msg.id) or {}
    remaining = _remaining_ttl(expire_at)

    audio_tracks = [
        {
            "label": a["label"],
            "url": f"{Config.BASE_URL}/stream/{encode_token(a['message_id'], TYPE_FILE, remaining)}",
        }
        for a in meta.get("audio", [])
    ]
    sub_tracks = [
        {
            "label": s["label"],
            "url": f"{Config.BASE_URL}/subs/{encode_token(s['message_id'], TYPE_SUB, remaining)}",
        }
        for s in meta.get("subs", [])
    ]

    remux_needed = mime.startswith("video/") and _needs_remux(mime, name)
    video_src = f"{Config.BASE_URL}/remux/{token}" if remux_needed else f"{Config.BASE_URL}/stream/{token}"

    html = _watch_template.render(
        name=name,
        size=size,
        mime=mime,
        video_src=video_src,
        stream_url=f"{Config.BASE_URL}/stream/{token}",
        dl_url=f"{Config.BASE_URL}/dl/{token}",
        poster=meta.get("thumb") or "",
        is_video=mime.startswith("video/"),
        is_audio=mime.startswith("audio/"),
        remux_needed=remux_needed,
        tracks_json=json.dumps({"audio": audio_tracks, "subs": sub_tracks}),
    )
    return web.Response(text=html, content_type="text/html")


@routes.get("/playlist/{token}")
async def playlist_view(request: web.Request):
    token = request.match_info["token"]
    decoded = decode_token(token)
    if not decoded or decoded["kind"] != TYPE_PLAYLIST:
        raise web.HTTPNotFound(text="Link expired or invalid.")

    pl_id = f"{decoded['ref_id']:016x}"
    pl = await playlist_store.get(pl_id)
    if not pl:
        raise web.HTTPNotFound(text="Playlist not found.")

    remaining = _remaining_ttl(decoded["expire_at"])
    items = []
    for message_id in pl["items"]:
        msg = await _get_message(message_id)
        if not msg or msg.empty:
            continue
        media = _media_of(msg)
        if not media:
            continue
        name, size, mime = _file_meta(media)
        item_token = encode_token(message_id, TYPE_FILE, remaining)
        items.append(
            {
                "name": name,
                "size": size,
                "mime": mime,
                "watch_url": f"{Config.BASE_URL}/watch/{item_token}",
            }
        )

    html = _playlist_template.render(name=pl["name"], items=items)
    return web.Response(text=html, content_type="text/html")


@routes.get("/subs/{token}")
async def subs_endpoint(request: web.Request):
    token = request.match_info["token"]
    decoded = decode_token(token)
    if not decoded or decoded["kind"] != TYPE_SUB:
        raise web.HTTPNotFound()
    msg = await _get_message(decoded["ref_id"])
    if not msg or msg.empty or not msg.document:
        raise web.HTTPNotFound()

    buf = await client_manager.primary.download_media(msg, in_memory=True)
    raw = buf.getvalue() if hasattr(buf, "getvalue") else bytes(buf)
    text = raw.decode("utf-8", errors="ignore")

    name = (msg.document.file_name or "").lower()
    if name.endswith(".srt"):
        vtt = srt_to_vtt(text)
    elif name.endswith(".ass"):
        vtt = ass_to_vtt(text)
    else:
        vtt = text

    return web.Response(text=vtt, content_type="text/vtt")


@routes.get("/remux/{token}")
async def remux_endpoint(request: web.Request):
    token = request.match_info["token"]
    resolved = await _resolve_file(token)
    if not resolved:
        raise web.HTTPNotFound(text="Link expired or invalid.")
    msg, media, _ = resolved
    name, size, _ = _file_meta(media)

    pooled = await client_manager.acquire()
    gen = remux_to_mp4(pooled.client, msg, size)

    try:
        first_chunk = await gen.__anext__()
    except StopAsyncIteration:
        first_chunk = b""
    except Exception:
        client_manager.release(pooled)
        logger.exception("remux failed for message %s", msg.id)
        raise web.HTTPBadGateway(
            text="Couldn't convert this file for playback. Make sure "
            "ffmpeg is installed in the container."
        )

    headers = {
        "Content-Type": "video/mp4",
        "Content-Disposition": f'inline; filename="{os.path.splitext(name)[0]}.mp4"',
    }
    resp = web.StreamResponse(status=200, headers=headers)
    try:
        await resp.prepare(request)
    except (ConnectionResetError, asyncio.CancelledError, ConnectionError):
        client_manager.release(pooled)
        return resp

    try:
        if first_chunk:
            await resp.write(first_chunk)
        async for chunk in gen:
            await resp.write(chunk)
    except (ConnectionResetError, asyncio.CancelledError):
        pass
    except Exception:
        logger.exception("remux streaming interrupted for message %s", msg.id)
    finally:
        client_manager.release(pooled)

    return resp


async def _serve(request: web.Request, force_download: bool):
    token = request.match_info["token"]
    resolved = await _resolve_file(token)
    if not resolved:
        raise web.HTTPNotFound(text="Link expired or invalid.")
    msg, media, _ = resolved
    name, size, mime = _file_meta(media)

    start, end = 0, max(size - 1, 0)
    status = 200
    range_header = request.headers.get("Range")
    if range_header:
        try:
            _, rng = range_header.split("=")
            start_s, end_s = rng.split("-")
            start = int(start_s) if start_s else 0
            end = int(end_s) if end_s else size - 1
            status = 206
        except Exception:
            start, end, status = 0, size - 1, 200

    end = min(end, size - 1) if size else end
    length = max(end - start + 1, 0)

    pooled = await client_manager.acquire()
    gen = stream_chunks(pooled.client, msg, start, length)

    # Pull the first chunk BEFORE sending any headers. If Telegram fetch
    # fails, this lets us return a real error instead of committing a
    # 200/206 response with a Content-Length promise we can't keep --
    # which is what produces a "downloads but is 0 bytes / broken" file.
    try:
        first_chunk = await gen.__anext__()
    except StopAsyncIteration:
        first_chunk = b""
    except Exception:
        client_manager.release(pooled)
        logger.exception("initial fetch failed for message %s", msg.id)
        raise web.HTTPBadGateway(
            text="Couldn't fetch this file from Telegram. Make sure the "
            "bot (and every STREAM_TOKENS worker) is still an admin of "
            "LOG_CHANNEL, and check the server logs for details."
        )

    headers = {
        "Content-Type": mime,
        "Accept-Ranges": "bytes",
        "Content-Length": str(length),
        "Content-Disposition": f'{"attachment" if force_download else "inline"}; filename="{name}"',
    }
    if status == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"

    resp = web.StreamResponse(status=status, headers=headers)
    try:
        await resp.prepare(request)
    except (ConnectionResetError, asyncio.CancelledError, ConnectionError):
        # Client (often Chrome's download hand-off) closed the connection
        # before we could even send headers -- nothing more to do.
        client_manager.release(pooled)
        return resp

    try:
        if first_chunk:
            await resp.write(first_chunk)
        async for chunk in gen:
            await resp.write(chunk)
    except (ConnectionResetError, asyncio.CancelledError):
        pass
    except Exception:
        logger.exception("streaming interrupted for message %s", msg.id)
    finally:
        client_manager.release(pooled)

    return resp


@routes.get("/stream/{token}")
async def stream_endpoint(request: web.Request):
    return await _serve(request, force_download=False)


@routes.get("/dl/{token}")
async def download_endpoint(request: web.Request):
    return await _serve(request, force_download=True)


@routes.get("/")
async def index(request: web.Request):
    return web.Response(text=_index_template.render(), content_type="text/html")


def create_app() -> web.Application:
    app = web.Application(client_max_size=0)
    app.add_routes(routes)
    app.router.add_static("/static", os.path.join(os.path.dirname(__file__), "static"))
    return app
