import os

from dotenv import load_dotenv

load_dotenv()


def _int_env(key: str, default: str) -> int:
    return int(os.environ.get(key, default))


class Config:
    # --- Core Telegram credentials ---
    API_ID = _int_env("API_ID", "0")
    API_HASH = os.environ.get("API_HASH", "")
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

    # Comma-separated extra bot tokens dedicated purely to streaming.
    # Each of these bots MUST be an admin in LOG_CHANNEL so it can fetch
    # messages and pull file chunks independently of the primary bot.
    STREAM_TOKENS = os.environ.get("STREAM_TOKENS", "")

    # Private channel/group the bot copies files into. Links are derived
    # from (message_id in this channel), never from the original chat, so
    # the bot doesn't need to keep standing access to wherever the file
    # came from.
    LOG_CHANNEL = _int_env("LOG_CHANNEL", "0")

    # Optional allowlist. Empty set = anyone can use /stream.
    AUTH_USERS = {
        int(x) for x in os.environ.get("AUTH_USERS", "").split(",") if x.strip()
    }

    # Used to HMAC-sign generated link tokens so they can't be guessed or
    # tampered with.
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-please")

    BASE_URL = os.environ.get("BASE_URL", "http://localhost:8080").rstrip("/")
    PORT = _int_env("PORT", "8080")

    # --- Streaming tuning knobs (mirrors WZML-X's STREAM_* config) ---
    # How many chunks are fetched concurrently per active viewer. Higher =
    # smoother playback on fast links, more load per stream.
    STREAM_PIPELINE = _int_env("STREAM_PIPELINE", "4")

    # Bytes per MTProto chunk request. Must stay <= 1 MiB.
    STREAM_CHUNK = _int_env("STREAM_CHUNK", str(1024 * 1024))

    # Max concurrent viewers routed to a single bot client before the pool
    # starts preferring a less-loaded one.
    STREAM_PER_CLIENT = _int_env("STREAM_PER_CLIENT", "6")

    # Hard ceiling on total concurrent streams across the whole pool. Acts
    # as a global backpressure valve so the process never opens more
    # concurrent downloads than the host can actually serve.
    STREAM_GATE = _int_env("STREAM_GATE", "96")

    WORKDIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
