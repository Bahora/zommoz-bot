import discord
import aiohttp
import re
import asyncio
from discord.ext import commands
from database import Database

spec_til_rolle = {
    # Tank specs
    "Blood": "tank",
    "Protection": "tank",
    "Guardian": "tank",
    "Brewmaster": "tank",
    "Vengeance": "tank",

    # Healer specs
    "Holy": "healer",
    "Mistweaver": "healer",
    "Restoration": "healer",
    "Preservation": "healer",

    # DPS specs
    "Arms": "dps",
    "Fury": "dps",
    "Havoc": "dps",
    "Survival": "dps",
    "Subtlety": "dps",
    "Outlaw": "dps",
    "Assassination": "dps",
    "Unholy": "dps",
    "Frost": "dps",
    "Enhancement": "dps",
    "Elemental": "dps",
    "Balance": "dps",
    "Beastmastery": "dps",
    "Marksmanship": "dps",
    "Devastation": "dps",
    "Destruction": "dps",
    "Affliction": "dps",
    "Demonology": "dps",
    "Arcane": "dps",
    "Fire": "dps",
    "Frost (Mage)": "dps"
}

class ZommozBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db

    async def hent_data_fra_rio(self, rio_link):
        match = re.search(r"raider\.io/characters/(\w+)/([^/]+)/([^/?#]+)", rio_link)
        if not match:
            return None
        region, realm, name = match.groups()
        url = f"https://raider.io/api/v1/characters/profile?region={region}&realm={realm}&name={name}&fields=gear,spec"

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {
                        "name": name.capitalize(),
                        "spec": data.get("active_spec_name"),
                        "class": data.get("class"),
                        "ilvl": int(data.get("gear", {}).get("item_level_equipped", 0)),
                        "rio": rio_link
                    }
        return None

    @commands.command(name="zinit")
    async def zinit(self, ctx, listename: str, *, titel: str = None):
        listename = listename.lower()
        tilladt = any(r.name == "Group Organisator" for r in ctx.author.roles)
        if ctx.author.guild_permissions.administrator:
            tilladt = True
        if not tilladt:
            await ctx.send("⛔ Du skal have rollen **Group Organisator** eller være administrator for at bruge !zinit.")
            return

        guild_id = str(ctx.guild.id)
        kanal = ctx.channel

        existing = await self.db.get_liste(guild_id, listename)
        if existing and existing.get("besked_id"):
            try:
                _ = await kanal.fetch_message(existing["besked_id"])
                link = f"https://discord.com/channels/{ctx.guild.id}/{ctx.channel.id}/{existing['besked_id']}"
                await ctx.send(f"🟢 Listen **{listename}** er allerede oprettet.\n🔗 {link}")
                return
            except discord.NotFound:
                pass

        titel = titel or f"Mythic List ({listename})"
        besked = await kanal.send(f"**{titel}**\n\n_Opsætning klaret..._\n\n\u200b\n\u200b")
        await self.db.opret_liste(guild_id, listename, titel, besked.id, ctx.author.id)
        await ctx.send(f"✅ Listen **{listename}** er nu klar.")
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass

    @commands.command(name="ztilmeld")
    async def ztilmeld(self, ctx, listename: str, rio_link: str):
        listename = listename.lower()
        guild_id = str(ctx.guild.id)
        user_id = str(ctx.author.id)

        # Tjek om listen eksisterer
        existing_liste = await self.db.get_liste(guild_id, listename)
        if not existing_liste:
            await ctx.send(f"❌ Listen **{listename}** findes ikke. Brug `!zlister` for at se tilgængelige.")
            return

        # Hent data fra Raider.IO
        info = await self.hent_data_fra_rio(rio_link)
        if not info:
            await ctx.send("❌ Kunne ikke hente karakterdata fra Raider.IO-linket.")
            return

        charname = info["name"]
        rolle = spec_til_rolle.get(info["spec"], "dps")

        # Tjek om karakter allerede er tilmeldt af denne bruger
        eksisterende = await self.db.hent_alle(guild_id, listename)
        for r in eksisterende:
            if r["user_id"] == user_id and r["charname"] == charname:
                embed = discord.Embed(
                    title="Bekræft overskrivning",
                    description=f"Du har allerede **{charname}** tilmeldt **{listename}**.\nVil du overskrive den?",
                    color=discord.Color.orange()
                )
                prompt = await ctx.send(embed=embed)
                await prompt.add_reaction("✅")
                await prompt.add_reaction("❌")

                def check(reaction, user):
                    return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == prompt.id

                try:
                    reaction, _ = await self.bot.wait_for("reaction_add", timeout=30.0, check=check)
                    await prompt.delete()  # 👈 slet altid prompten uanset hvad
                    if str(reaction.emoji) == "❌":
                        await ctx.send("❌ Tilmelding annulleret.")
                        return
                except asyncio.TimeoutError:
                    await prompt.delete()
                    await ctx.send("⏰ Tilmelding afbrudt (ingen bekræftelse modtaget).")
                    return

        # Gem registrering
        await self.db.add_registrering(
            guild_id=guild_id,
            listename=listename,
            user_id=user_id,
            charname=charname,
            spec=info["spec"],
            class_=info["class"],
            ilvl=info["ilvl"],
            rio=info["rio"],
            rolle=rolle
        )

        # Opdater og besked
        await self.opdater_besked(guild_id, listename)
        await ctx.send(f"{ctx.author.mention} tilmeldte **{charname}** til **{listename}**.")
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass

    @commands.command(name="zfjern")
    async def zfjern(self, ctx, listename: str, charname: str = None):
        listename = listename.lower()
        await self.db.fjern_registrering(str(ctx.guild.id), listename, str(ctx.author.id), charname.capitalize() if charname else None)
        await self.opdater_besked(ctx.guild.id, listename)
        besked = f"{ctx.author.mention} fjernede "
        besked += f"**{charname}**" if charname else "alle dine karakterer"
        besked += f" fra **{listename}**."
        await ctx.send(besked)
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass

    @commands.command(name="zvis")
    async def zvis(self, ctx, listename: str):
        listename = listename.lower()
        ldata = await self.db.get_liste(str(ctx.guild.id), listename)
        if not ldata or not ldata.get("besked_id"):
            await ctx.send("Beskeden er ikke oprettet endnu. Brug `!zinit <liste>`.")
            return
        link = f"https://discord.com/channels/{ctx.guild.id}/{ctx.channel.id}/{ldata['besked_id']}"
        await ctx.send(f"Se listen **{listename}** her: {link}")

    @commands.command(name="zlister")
    async def zlister(self, ctx):
        guild_id = str(ctx.guild.id)
        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch("SELECT listename, titel FROM lister WHERE guild_id = $1", guild_id)
        if not rows:
            await ctx.send("❌ Der er ingen lister oprettet på denne server.")
            return
        beskeder = [f"`{row['listename']}` — **{row['titel']}**" for row in rows]
        await ctx.send("📋 **Lister du kan tilmelde dig:**" + "\n\n".join(beskeder))

    @commands.command(name="zreset")
    async def zreset(self, ctx, listename: str):
        listename = listename.lower()
        ldata = await self.db.get_liste(str(ctx.guild.id), listename)
        if not ldata:
            await ctx.send("❌ Listen findes ikke.")
            return
        if str(ldata.get("ejer_id")) != str(ctx.author.id) and not ctx.author.guild_permissions.administrator:
            await ctx.send("⛔ Kun opretteren af listen **eller en administrator** kan slette den.")
            return
        await self.db.slet_liste(str(ctx.guild.id), listename)
        await ctx.send(f"🗑️ Listen **{listename}** er blevet slettet.")

    async def opdater_besked(self, guild_id, listename):
        listename = listename.lower()
        guild_id = str(guild_id)
        ldata = await self.db.get_liste(guild_id, listename)
        if not ldata:
            return
        
        resultater = await self.db.hent_alle(guild_id, listename)
        grupper = {"tank": [], "healer": [], "dps": []}
        for row in resultater:
            tekst = f"**{row['charname']}** - {row['spec']} {row['class']} - {row['ilvl']} ilvl - [Raider.IO](<{row['rio']}>)"
            grupper[row["rolle"]].append(tekst)

        content = f"**{ldata.get('titel', listename)}**\n\n"
        if grupper["tank"]:
            content += "**🛡️ TANKS**\n" + "\n".join(grupper["tank"]) + "\n"
        if grupper["healer"]:
            content += "\n**💚 HEALERS**\n" + "\n".join(grupper["healer"]) + "\n"
        if grupper["dps"]:
            content += "\n**⚔️ DPS**\n" + "\n".join(grupper["dps"]) + "\n"
        content += "\n\u200b\n\u200b"

        besked_id = ldata.get("besked_id")
        if not besked_id:
            return

        for kanal in self.bot.get_all_channels():
            if isinstance(kanal, discord.TextChannel):
                try:
                    besked = await kanal.fetch_message(int(besked_id))
                    await besked.edit(content=content)
                    return
                except (discord.NotFound, discord.Forbidden):
                    continue

async def setup(bot):
    await bot.add_cog(ZommozBot(bot))
