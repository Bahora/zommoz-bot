import discord
from discord.ext import commands
import os
import asyncio

intents = discord.Intents.default()
intents.message_content = True  # For at kunne læse beskeder

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f"Logget ind som {bot.user} ({bot.user.id})")
    await bot.tree.sync()

async def setup():
    await bot.load_extension("cogs.registreringer")

if __name__ == "__main__":
    asyncio.run(setup())
    bot.run(os.getenv("DISCORD_TOKEN"))  # Railway læser dette fra "Variables"