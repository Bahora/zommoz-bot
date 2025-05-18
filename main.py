import discord
from discord.ext import commands
import os
from database import Database
import logging

logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)
db = Database()

@bot.event
async def on_ready():
    logging.info(f"Logget ind som {bot.user} ({bot.user.id})")
    await bot.tree.sync()

@bot.event
async def setup_hook():
    await db.connect()
    bot.db = db
    await bot.load_extension("cogs.registreringer_postgres")

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))
