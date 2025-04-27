from aiohttp import web as webserver
import pyromod.listen
from pyrogram import Client
from pyrogram.enums import ParseMode
from pyrogram import enums
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler

# Telegram API credentials
BOT_TOKEN = "7828141236:AAHVOwmyG9zJ96KJ9ugXoi1aZsKXpvKSldo"
API_ID = "22136772"
API_HASH = "7541e5b6d298eb1f60dac89aae92868c"

PORT_CODE = "8080"
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s - %(levelname)s] - %(name)s - %(message)s",
    datefmt='%d-%b-%y %H:%M:%S',
    handlers=[
        RotatingFileHandler(
            "primedlbot.txt",
            maxBytes=50000000,
            backupCount=10
        ),
        logging.StreamHandler()
    ]
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

def LOGGER(name: str) -> logging.Logger:
    return logging.getLogger(name)

routes = webserver.RouteTableDef()

@routes.get("/", allow_head=True)
async def root_route_handler(request):
    return webserver.json_response("AstroBotz")

async def web_server():
    web_app = webserver.Application(client_max_size=30000000)
    web_app.add_routes(routes)
    return web_app

async def bot_run():
    _app = webserver.Application(client_max_size=30000000)
    _app.add_routes(routes)
    return _app




ascii_art = """
Made By @AstroBotz..❤
"""

class Bot(Client):
    def __init__(self):
        super().__init__(
            "bot",
            api_hash=API_HASH,
            api_id=API_ID,
            plugins={
                "root": "bot/plugins"
            },
            workers=200,
            bot_token=BOT_TOKEN,
            sleep_threshold=10
        )
        self.LOGGER = LOGGER

    async def start(self):
        await super().start()
        
        client = webserver.AppRunner(await bot_run())
        await client.setup()
        bind_address = "0.0.0.0"
        await webserver.TCPSite(client, bind_address,
        PORT_CODE).start()
        
        bot_details = await self.get_me()
        self.set_parse_mode(enums.ParseMode.HTML)
        self.LOGGER(__name__).info(
            f"@{bot_details.username}  started! "
        )
        

    async def stop(self, *args):
        await super().stop()
        self.LOGGER(__name__).info("Bot stopped. Bye.")
