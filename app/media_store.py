import asyncio
import json
import os

from .config import Config

STORE_PATH = os.path.join(Config.WORKDIR, "data", "media_meta.json")


class MediaStore:
    """
    Keyed by LOG_CHANNEL message id (as a string). Holds the bits that
    don't fit in a signed token: a custom thumbnail URL and the extra
    audio/subtitle tracks the Fused Player switches between.
    """

    def __init__(self, path: str = STORE_PATH):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._lock = asyncio.Lock()
        self._data = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self._data, f)
        os.replace(tmp, self.path)

    async def set(self, message_id: int, thumb=None, audio=None, subs=None):
        async with self._lock:
            self._data[str(message_id)] = {
                "thumb": thumb,
                "audio": audio or [],
                "subs": subs or [],
            }
            self._save()

    async def get(self, message_id: int):
        async with self._lock:
            return self._data.get(str(message_id))


media_store = MediaStore()
