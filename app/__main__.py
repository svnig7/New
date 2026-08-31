import asyncio
import logging

from aiohttp import web

from .bot import register_handlers
from .client_manager import client_manager
from .config import Config
from .web_server import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("streambot")


async def main():
    await client_manager.start()
    register_handlers(client_manager.primary)

    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", Config.PORT)
    await site.start()
    logger.info("Web server listening on 0.0.0.0:%d", Config.PORT)
    logger.info("Base URL: %s", Config.BASE_URL)

    try:
        await asyncio.Event().wait()
    finally:
        await client_manager.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
