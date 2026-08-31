import hashlib
import logging

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from .cmd_parse import human_ttl, parse_stream_args
from .config import Config
from .media_store import media_store
from .playlist_store import playlist_store
from .token_utils import TYPE_FILE, TYPE_PLAYLIST, encode_token

logger = logging.getLogger(__name__)


def _playlist_id(chat_id: int, name: str) -> str:
    return hashlib.sha256(f"{chat_id}:{name.lower()}".encode()).hexdigest()[:16]


def _media_of(msg: Message):
    return (
        msg.document
        or msg.video
        or msg.audio
        or msg.animation
        or msg.voice
        or msg.photo
    )


async def _collect_extra_tracks(client: Client, target: Message, log_channel: int):
    """
    If the replied-to message is part of a Telegram album (media group),
    pulls sibling files in as extra tracks for the Fused Player: audio
    files become alternate audio tracks, .srt/.vtt/.ass files become
    switchable subtitles. Send the video + its alt-language audio/subs as
    one album, then reply /stream to any item in it.
    """
    tracks = {"audio": [], "subs": []}
    if not target.media_group_id:
        return tracks

    try:
        group = await client.get_media_group(target.chat.id, target.id)
    except Exception:
        return tracks

    for m in group:
        if m.id == target.id:
            continue
        doc = m.document
        name = (getattr(doc, "file_name", "") or "").lower()
        if m.audio or (doc and (doc.mime_type or "").startswith("audio/")):
            copied = await m.copy(log_channel)
            label = (m.audio.title if m.audio else None) or name or f"Audio {len(tracks['audio']) + 1}"
            tracks["audio"].append({"message_id": copied.id, "label": label})
        elif name.endswith((".srt", ".vtt", ".ass")):
            copied = await m.copy(log_channel)
            label = name.rsplit(".", 1)[0] or f"Subtitle {len(tracks['subs']) + 1}"
            tracks["subs"].append({"message_id": copied.id, "label": label})

    return tracks


def register_handlers(bot: Client):
    @bot.on_message(filters.command("start") & filters.private)
    async def start_cmd(client, message: Message):
        await message.reply_text(
            "Send me a file, video or audio, then reply to it with /stream "
            "to get a streaming + download link.\n\n"
            "Flags:\n"
            "`-pl <name>`  add to a playlist\n"
            "`-t <url>`  custom thumbnail\n"
            "`-ttl <30m|2h|1d>`  self-expiring link\n\n"
            "For multi-audio / multi-subtitle switching, send the video "
            "plus its alternate audio and .srt/.vtt files as one album, "
            "then reply /stream to any item in it."
        )

    @bot.on_message(filters.command("stream"))
    async def stream_cmd(client, message: Message):
        if Config.AUTH_USERS and message.from_user.id not in Config.AUTH_USERS:
            return await message.reply_text("You're not authorized to use this bot.")

        target = message.reply_to_message
        media = target and _media_of(target)
        if not target or not media:
            return await message.reply_text("Reply to a file, video or audio with /stream.")

        if not Config.LOG_CHANNEL:
            return await message.reply_text("LOG_CHANNEL isn't configured on the bot.")

        raw_parts = message.text.split(None, 1)
        args = parse_stream_args(raw_parts[1] if len(raw_parts) > 1 else "")

        status = await message.reply_text("Generating link…")
        try:
            log_msg = await target.copy(Config.LOG_CHANNEL)
        except Exception as e:
            logger.error("copy to log channel failed: %s", e)
            return await status.edit_text(
                "Couldn't process that file — check that the bot is an admin of LOG_CHANNEL."
            )

        tracks = await _collect_extra_tracks(client, target, Config.LOG_CHANNEL)
        if args["thumb"] or tracks["audio"] or tracks["subs"]:
            await media_store.set(
                log_msg.id, thumb=args["thumb"], audio=tracks["audio"], subs=tracks["subs"]
            )

        ttl = args["ttl"] or 0

        if args["playlist"]:
            pl_id = _playlist_id(message.chat.id, args["playlist"])
            await playlist_store.add_item(pl_id, args["playlist"], message.from_user.id, log_msg.id)
            token = encode_token(int(pl_id, 16), TYPE_PLAYLIST, ttl)
            watch_url = f"{Config.BASE_URL}/playlist/{token}"
            note = f"Added to playlist **{args['playlist']}**"
            buttons = InlineKeyboardMarkup([[InlineKeyboardButton("📜 Open playlist", url=watch_url)]])
        else:
            token = encode_token(log_msg.id, TYPE_FILE, ttl)
            watch_url = f"{Config.BASE_URL}/watch/{token}"
            stream_url = f"{Config.BASE_URL}/stream/{token}"
            note = "Your link is ready"
            buttons = InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("▶️ Watch / Listen", url=watch_url)],
                    [InlineKeyboardButton("⬇️ Direct link", url=stream_url)],
                ]
            )

        ttl_note = f"\nExpires in {human_ttl(ttl)}." if ttl else ""
        track_note = ""
        if tracks["audio"] or tracks["subs"]:
            track_note = f"\n{len(tracks['audio'])} audio + {len(tracks['subs'])} subtitle track(s) attached."

        await status.edit_text(
            f"**{note}**\n\n`{watch_url}`{ttl_note}{track_note}",
            reply_markup=buttons,
            disable_web_page_preview=True,
        )
