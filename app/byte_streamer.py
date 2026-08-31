import asyncio
import logging
from typing import AsyncGenerator

from pyrogram import Client
from pyrogram.types import Message

from .config import Config

logger = logging.getLogger(__name__)

PYROGRAM_CHUNK_SIZE = 1024 * 1024  # fixed chunk size used by Client.stream_media


async def stream_chunks(
    client: Client,
    message: Message,
    offset_bytes: int,
    length: int,
) -> AsyncGenerator[bytes, None]:
    """
    Wraps Client.stream_media (Pyrogram's own DC-aware chunked downloader)
    with a small read-ahead buffer, depth = STREAM_PIPELINE. That overlaps
    "fetch next chunk from Telegram" with "write previous chunk to the HTTP
    response", which is what keeps playback from stalling on every chunk
    boundary on a slow connection.
    """
    first_chunk = offset_bytes // PYROGRAM_CHUNK_SIZE
    skip = offset_bytes % PYROGRAM_CHUNK_SIZE

    queue: asyncio.Queue = asyncio.Queue(maxsize=max(1, Config.STREAM_PIPELINE))
    sentinel = object()

    async def producer():
        sent = 0
        try:
            async for chunk in client.stream_media(message, offset=first_chunk):
                if sent == 0 and skip:
                    chunk = chunk[skip:]
                if chunk and sent + len(chunk) > length:
                    chunk = chunk[: length - sent]
                if chunk:
                    await queue.put(chunk)
                    sent += len(chunk)
                if sent >= length or not chunk:
                    break
        except Exception:
            logger.exception("stream producer failed for message %s", message.id)
        finally:
            await queue.put(sentinel)

    task = asyncio.create_task(producer())
    try:
        while True:
            chunk = await queue.get()
            if chunk is sentinel:
                break
            yield chunk
    finally:
        task.cancel()
