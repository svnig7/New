import base64
import hashlib
import hmac
import struct
import time

from .config import Config

TYPE_FILE = 0
TYPE_PLAYLIST = 1
TYPE_SUB = 2

_STRUCT = ">BQI"  # kind(1) + ref_id(8) + expire_at(4) = 13 bytes


def _sign(payload: bytes) -> bytes:
    return hmac.new(Config.SECRET_KEY.encode(), payload, hashlib.sha256).digest()[:8]


def encode_token(ref_id: int, kind: int = TYPE_FILE, ttl_seconds: int = 0) -> str:
    """
    Encodes a reference id (a LOG_CHANNEL message id, or a playlist id) into
    a short, URL-safe, HMAC-signed token. We never store the file_id
    itself -- Telegram's file_reference expires after ~24h, so the message
    is re-fetched by id at stream time to get a fresh one instead.

    ttl_seconds > 0 makes the link self-expiring: decode_token returns
    None once time.time() passes expire_at.
    """
    expire_at = int(time.time()) + ttl_seconds if ttl_seconds else 0
    payload = struct.pack(_STRUCT, kind, ref_id, expire_at)
    sig = _sign(payload)
    raw = payload + sig
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_token(token: str):
    padding = "=" * (-len(token) % 4)
    try:
        raw = base64.urlsafe_b64decode(token + padding)
    except Exception:
        return None
    if len(raw) != 21:  # 13 byte payload + 8 byte sig
        return None
    payload, sig = raw[:13], raw[13:]
    if not hmac.compare_digest(sig, _sign(payload)):
        return None
    kind, ref_id, expire_at = struct.unpack(_STRUCT, payload)
    if expire_at and time.time() > expire_at:
        return None  # link has expired
    return {"kind": kind, "ref_id": ref_id, "expire_at": expire_at}
