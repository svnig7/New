import asyncio
import logging

from .byte_streamer import stream_chunks

logger = logging.getLogger(__name__)


async def remux_to_mp4(client, message, size: int):
    """
    Stream-copies (no re-encoding) into fragmented MP4 so browsers that
    can't parse Matroska/AVI natively can still play H.264/AAC content
    through a plain <video> tag. Because ffmpeg consumes the source
    sequentially, this only supports playback from the start -- no
    server-side seeking on a remuxed stream.
    """
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-loglevel", "error",
        "-i", "pipe:0",
        "-c", "copy",
        "-f", "mp4",
        "-movflags", "frag_keyframe+empty_moov+default_base_moof",
        "pipe:1",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    async def feed():
        try:
            async for chunk in stream_chunks(client, message, 0, size):
                proc.stdin.write(chunk)
                await proc.stdin.drain()
        except (ConnectionResetError, BrokenPipeError):
            pass
        except Exception:
            logger.exception("remux feed failed for message %s", message.id)
        finally:
            try:
                proc.stdin.close()
            except Exception:
                pass

    feeder = asyncio.create_task(feed())

    try:
        while True:
            chunk = await proc.stdout.read(65536)
            if not chunk:
                break
            yield chunk
    finally:
        feeder.cancel()
        if proc.returncode is None:
            proc.kill()
        try:
            err = await proc.stderr.read()
        except Exception:
            err = b""
        if proc.returncode not in (0, None) and err:
            logger.error(
                "ffmpeg exited %s for message %s: %s",
                proc.returncode, message.id, err.decode(errors="ignore")[:500],
            )
        await proc.wait()
