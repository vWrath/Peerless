import asyncio
import datetime
import os
import sys
from os import environ as env

import colorlog
import pytz
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

from resources.peerless import Peerless

class Formatter(colorlog.ColoredFormatter):
    def converter(self, timestamp):
        return datetime.datetime.fromtimestamp(timestamp, tz=pytz.timezone('US/Central')).timetuple()
    
class DiscordHandler(colorlog.StreamHandler):
    def __init__(self, bot: commands.AutoShardedBot):
        super().__init__()
        
        self.bot = bot
        
    def handle(self, record) -> bool:
        global fail_to_discord
        
        if fail_to_discord and record.levelno in [colorlog.WARN, colorlog.ERROR, colorlog.FATAL]:
            error_class, error, tb = record.exc_info or (None, None, None)
            
            self.bot.dispatch("fail", error_class=error_class, error=error, tb=tb)
        else:
            return super().handle(record)

async def main():
    global fail_to_discord
    
    print("which bot are you using?")
    print("---")
    print("1. Main")
    print("2. Beta")
    print("3. Alpha")
    print("4. Support")
    print("---")
    
    match input(""):
        case "1":
            token      = env["MAIN_TOKEN"]
            testing    = False
        case "2":
            token   = env["BETA_TOKEN"]
            testing = True
        case "3":
            token   = env["ALPHA_TOKEN"]
            testing = True
        case "4":
            token   = env["SUPPORT_TOKEN"]
            testing = False
        case _:
            token = env["MAIN_TOKEN"]
            testing = False
            
    print('---')
    
    match input("Do you want to log errors to discord? (y/n): ").lower():
        case "y":
            fail_to_discord = True
        case "n":
            fail_to_discord = False
        case _:
            fail_to_discord = False
            
    print('---')
    os.system('cls' if sys.platform == 'win32' else 'clear')
    
    bot    = Peerless(token, testing, fail_to_discord)
    colors = colorlog.default_log_colors | {"DEBUG": "BLACK"}
    
    discord_handler  = DiscordHandler(bot)
    mongodb_handler  = colorlog.StreamHandler()
    peerless_handler = colorlog.StreamHandler()
    
    discord_formatter  = Formatter(' %(log_color)s[%(asctime)s][DISCORD][%(levelname)s] %(message)s', datefmt='%d/%m/%Y %r', log_colors=colors | {"INFO": "purple"})
    mongodb_formatter  = Formatter(' %(log_color)s[%(asctime)s][MONGODB][%(levelname)s] %(message)s', datefmt='%d/%m/%Y %r', log_colors=colors | {"INFO": "blue"})
    peerless_formatter = Formatter('%(log_color)s[%(asctime)s][PEERLESS][%(levelname)s] %(message)s', datefmt='%d/%m/%Y %r', log_colors=colors | {"INFO": "bold_purple"})
    
    discord_handler.setFormatter(discord_formatter)
    mongodb_handler.setFormatter(mongodb_formatter)
    peerless_handler.setFormatter(peerless_formatter)
    
    discord_logger  = colorlog.getLogger("discord")  # purple
    mongodb_logger  = colorlog.getLogger("mongodb")  # blue
    peerless_logger = colorlog.getLogger("peerless") # pink (bold_purple)
    
    discord_logger.addHandler(discord_handler)
    mongodb_logger.addHandler(mongodb_handler)
    peerless_logger.addHandler(peerless_handler)
    
    discord_logger.setLevel(colorlog.INFO)
    mongodb_logger.setLevel(colorlog.INFO)
    peerless_logger.setLevel(colorlog.DEBUG)
    
    try:
        async with bot:
            await bot.start(token)
    except asyncio.CancelledError:
        pass
    finally:
            peerless_logger.info("Turning Off...")
            await bot.close()
            
            if bot.database:
                await bot.database.close()
                
            peerless_logger.info("Turned Off!")
    
asyncio.run(main())