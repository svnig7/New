import asyncio
import json
import os
import time

from .config import Config

STORE_PATH = os.path.join(Config.WORKDIR, "data", "playlists.json")


class PlaylistStore:
    """
    Keyed by a stable playlist id (sha256 of chat_id + lowercased name,
    truncated to 16 hex chars so it round-trips through the token's
    8-byte ref_id field). Holds an ordered list of LOG_CHANNEL message ids.
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

    async def add_item(self, playlist_id: str, name: str, owner_id: int, message_id: int):
        async with self._lock:
            pl = self._data.setdefault(
                playlist_id,
                {"name": name, "owner_id": owner_id, "items": [], "created": time.time()},
            )
            if message_id not in pl["items"]:
                pl["items"].append(message_id)
            self._save()
            return pl

    async def get(self, playlist_id: str):
        async with self._lock:
            return self._data.get(playlist_id)


playlist_store = PlaylistStore()
