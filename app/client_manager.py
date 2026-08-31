import asyncio
import logging

from pyrogram import Client

from .config import Config

logger = logging.getLogger(__name__)


class PooledClient:
    __slots__ = ("client", "index", "active")

    def __init__(self, client: Client, index: int):
        self.client = client
        self.index = index
        self.active = 0


class ClientManager:
    """
    Owns the primary bot plus every STREAM_TOKENS worker bot.

    Each viewer stream is handed to whichever client currently has the
    fewest active viewers (below STREAM_PER_CLIENT if possible), and the
    whole pool is capped by a global STREAM_GATE semaphore so the process
    never opens more concurrent Telegram downloads than it can serve.
    """

    def __init__(self):
        self.pool: list[PooledClient] = []
        self.gate = asyncio.Semaphore(Config.STREAM_GATE)
        self._lock = asyncio.Lock()

    async def start(self):
        primary = Client(
            "streambot_primary",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            in_memory=True,
        )
        await primary.start()
        me = await primary.get_me()
        self.pool.append(PooledClient(primary, 0))
        logger.info("Primary bot started: @%s", me.username)

        tokens = [t.strip() for t in Config.STREAM_TOKENS.split(",") if t.strip()]
        for i, token in enumerate(tokens, start=1):
            worker = Client(
                f"streambot_worker_{i}",
                api_id=Config.API_ID,
                api_hash=Config.API_HASH,
                bot_token=token,
                in_memory=True,
            )
            await worker.start()
            wme = await worker.get_me()
            self.pool.append(PooledClient(worker, i))
            logger.info("Stream worker %d started: @%s", i, wme.username)

        if len(self.pool) == 1:
            logger.warning(
                "No STREAM_TOKENS configured — running with a single bot. "
                "Add comma-separated worker tokens to STREAM_TOKENS and make "
                "each one an admin of LOG_CHANNEL to enable pooled streaming."
            )

    async def stop(self):
        await asyncio.gather(*(pc.client.stop() for pc in self.pool), return_exceptions=True)

    @property
    def primary(self) -> Client:
        return self.pool[0].client

    async def acquire(self) -> PooledClient:
        """Reserve the least-loaded client for one viewer's stream."""
        await self.gate.acquire()
        async with self._lock:
            under_cap = [p for p in self.pool if p.active < Config.STREAM_PER_CLIENT]
            candidates = under_cap or self.pool
            pc = min(candidates, key=lambda p: p.active)
            pc.active += 1
        return pc

    def release(self, pc: PooledClient):
        pc.active = max(0, pc.active - 1)
        self.gate.release()


client_manager = ClientManager()
