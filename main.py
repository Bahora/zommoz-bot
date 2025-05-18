import discord
from discord.ext import commands
import os
import asyncio
from database import Database

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)
db = Database()  # vi opretter db her én gang

@bot.event
async def on_ready():
    print(f"Logget ind som {bot.user} ({bot.user.id})")
    await bot.tree.sync()

async def setup():
    await db.connect()         # Opret forbindelse til DB én gang
    bot.db = db                # Gør den tilgængelig i botten
    await bot.load_extension("cogs.registreringer_postgres")

if __name__ == "__main__":
    asyncio.run(setup())
    bot.run(os.getenv("DISCORD_TOKEN"))
