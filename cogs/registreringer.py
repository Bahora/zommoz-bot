import discord
from discord.ext import commands
import json
import os
import re
import aiohttp
from discord.ext.commands import MissingRole

DATAFIL = "data/registreringer.json"

spec_til_rolle = {
    "Blood": "tank", "Protection": "tank", "Guardian": "tank", "Brewmaster": "tank", "Vengeance": "tank",
    "Holy": "healer", "Mistweaver": "healer", "Restoration": "healer", "Preservation": "healer",
    "Arms": "dps", "Fury": "dps", "Havoc": "dps", "Survival": "dps", "Subtlety": "dps",
    "Outlaw": "dps", "Assassination": "dps", "Unholy": "dps", "Frost": "dps",
    "Enhancement": "dps", "Elemental": "dps", "Balance": "dps", "Beastmastery": "dps",
    "Marksmanship": "dps", "Devastation": "dps", "Destruction": "dps", "Affliction": "dps",
    "Demonology": "dps", "Arcane": "dps", "Fire": "dps", "Frost (Mage)": "dps"
}

def indlaes_data():
    if not os.path.exists(DATAFIL):
        return {"guilds": {}}
    with open(DATAFIL, "r") as f:
        return json.load(f)

def gem_data(data):
    # Sikrer at mappen eksisterer
    os.makedirs(os.path.dirname(DATAFIL), exist_ok=True)
    
    with open(DATAFIL, "w") as f:
        json.dump(data, f, indent=2)


class ZommozBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data = indlaes_data()

    # Returnerer data for en given liste i en given Discord-server (guild)
    # Opretter listen hvis den ikke findes endnu
    def get_liste_data(self, guild_id, listename, ctx_author_id=None):
        # Sikrer at guild-strukturen eksisterer
        guilds = self.data.setdefault("guilds", {})
        gdata = guilds.setdefault(str(guild_id), {"lister": {}})
        lister = gdata["lister"]

        # Opret ny liste hvis ikke den findes
        if listename not in lister:
            lister[listename] = {
                "titel": f"Mythic List ({listename})",
                "besked_id": None,
                "registreringer": {},
                "ejer_id": ctx_author_id  # bruges til at styre adgang til reset
            }

        return lister[listename]

    def gem_alle_data(self):
        gem_data(self.data)

    # Henter karakterdata fra Raider.IO baseret på deres offentlige API
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
        # Brugeren skal have rollen ELLER være admin
        tilladt = any(r.name == "Mythic Organisator" for r in ctx.author.roles)
        if ctx.author.guild_permissions.administrator:
            tilladt = True

        if not tilladt:
            await ctx.send("⛔ Du skal have rollen **Mythic Organisator** eller være administrator for at bruge !zinit.")
            return

        # Fortsæt: hent eller opret liste
        guild_id = str(ctx.guild.id)
        kanal = ctx.channel
        ldata = self.get_liste_data(guild_id, listename, ctx.author.id)

        if titel:
            ldata["titel"] = titel

        # Hvis der allerede er en besked, tjek om den findes
        if ldata["besked_id"]:
            try:
                _ = await kanal.fetch_message(ldata["besked_id"])
                await ctx.send(f"🟢 Listen **{listename}** er allerede oprettet.")
                return
            except discord.NotFound:
                pass  # Fortsæt og lav ny besked

        # Opret ny besked i Discord
        content = f"**{ldata['titel']}**\n\n_Opsætning klaret..._"
        besked = await kanal.send(content)
        ldata["besked_id"] = besked.id
        self.gem_alle_data()

        await ctx.send(f"✅ Listen **{listename}** er nu klar.")

        # Slet brugerens !zinit-besked
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass

    @zinit.error
    async def zinit_error(self, ctx, error):
        if isinstance(error, MissingRole):
            await ctx.send("⛔ Du skal have rollen **Mythic Organisator** for at bruge `!zinit`.")

    @commands.command(name="ztilmeld")
    async def ztilmeld(self, ctx, listename: str, rio_link: str):
        guild_id = str(ctx.guild.id)
        ldata = self.get_liste_data(guild_id, listename)
        user_id = str(ctx.author.id)

        info = await self.hent_data_fra_rio(rio_link)
        if not info:
            await ctx.send("❌ Kunne ikke hente karakterdata fra Raider.IO-linket.")
            return

        rolle = spec_til_rolle.get(info["spec"], "dps")
        reg = ldata["registreringer"]
        if user_id not in reg:
            reg[user_id] = {}

        reg[user_id][info["name"]] = {
            "spec": info["spec"],
            "class": info["class"],
            "ilvl": info["ilvl"],
            "rio": info["rio"],
            "name": info["name"],
            "rolle": rolle
        }

        self.gem_alle_data()
        await self.opdater_besked(ctx.guild.id, listename)
        await ctx.send(f"{ctx.author.mention} tilmeldte **{info['name']}** til **{listename}**.")

        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass

    @commands.command(name="zfjern")
    async def zfjern(self, ctx, listename: str, charname: str = None):
        ldata = self.get_liste_data(str(ctx.guild.id), listename)
        reg = ldata["registreringer"]
        user_id = str(ctx.author.id)

        # Kontrol: Er bruger tilladt?
        er_admin = ctx.author.guild_permissions.administrator
        er_liste_ejer = str(ldata.get("ejer_id")) == user_id
        er_ejer_af_data = user_id in reg

        if not (er_admin or er_liste_ejer or er_ejer_af_data):
            await ctx.send("⛔ Du må kun fjerne karakterer, hvis du er administrator, liste-ejer eller ejer af registreringen.")
            return

        # Intet at fjerne
        if not er_ejer_af_data:
            await ctx.send("Du har ingen registreringer på denne liste.")
            return

        # Fjern specifik karakter
        if charname:
            charname = charname.capitalize()
            if charname in reg[user_id]:
                del reg[user_id][charname]
                if not reg[user_id]:
                    del reg[user_id]
                await ctx.send(f"{ctx.author.mention} fjernede **{charname}** fra **{listename}**.")
            else:
                await ctx.send(f"❌ Karakteren **{charname}** blev ikke fundet.")
        else:
            # Fjern alle karakterer
            del reg[user_id]
            await ctx.send(f"{ctx.author.mention} fjernede alle dine karakterer fra **{listename}**.")

        self.gem_alle_data()
        await self.opdater_besked(ctx.guild.id, listename)

        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass

            ldata = self.get_liste_data(str(ctx.guild.id), listename)
            user_id = str(ctx.author.id)
            reg = ldata["registreringer"]

            if user_id not in reg:
                await ctx.send("Du har ingen registreringer på denne liste.")
                return

            if charname:
                charname = charname.capitalize()
                if charname in reg[user_id]:
                    del reg[user_id][charname]
                    if not reg[user_id]:
                        del reg[user_id]
                    await ctx.send(f"{ctx.author.mention} fjernede **{charname}** fra **{listename}**.")
                else:
                    await ctx.send(f"❌ Karakteren **{charname}** blev ikke fundet.")
            else:
                del reg[user_id]
                await ctx.send(f"{ctx.author.mention} fjernede alle dine karakterer fra **{listename}**.")

            self.gem_alle_data()
            await self.opdater_besked(ctx.guild.id, listename)

            try:
                await ctx.message.delete()
            except discord.Forbidden:
                pass

    @commands.command(name="zvis")
    async def zvis(self, ctx, listename: str):
        ldata = self.get_liste_data(str(ctx.guild.id), listename)
        if not ldata.get("besked_id"):
            await ctx.send("Beskeden er ikke oprettet endnu. Brug `!zinit <liste>`.")
            return
        link = f"https://discord.com/channels/{ctx.guild.id}/{ctx.channel.id}/{ldata['besked_id']}"
        await ctx.send(f"Se listen **{listename}** her: {link}")

    @commands.command(name="zlister")
    async def zlister(self, ctx):
        guild_id = str(ctx.guild.id)
        gdata = self.data.get("guilds", {}).get(guild_id, {})
        lister = gdata.get("lister", {})

        if not lister:
            await ctx.send("❌ Der er ingen lister oprettet på denne server.")
            return

        beskeder = []
        for navn, data in lister.items():
            titel = data.get("titel", navn)
            beskeder.append(f"`{navn}` — **{titel}**")

        await ctx.send("📋 **Lister du kan tilmelde dig:**\n" + "\n".join(beskeder))

    @commands.command(name="zreset")
    async def zreset(self, ctx, listename: str):
        guild_id = str(ctx.guild.id)
        gdata = self.data.get("guilds", {}).get(guild_id, {})
        lister = gdata.get("lister", {})

        ldata = lister.get(listename)
        if not ldata:
            await ctx.send("❌ Listen findes ikke.")
            return

        # Tjek ejer eller administrator
        if str(ldata.get("ejer_id")) != str(ctx.author.id) and not ctx.author.guild_permissions.administrator:
            await ctx.send("⛔ Kun opretteren af listen **eller en administrator** kan slette den.")
            return

        del lister[listename]
        self.gem_alle_data()
        await ctx.send(f"🗑️ Listen **{listename}** er blevet slettet.")

    # Opdaterer beskeden med nyeste registreringer
    async def opdater_besked(self, guild_id, listename):
        ldata = self.get_liste_data(str(guild_id), listename)
        grupper = {"tank": [], "healer": [], "dps": []}

        for bruger_chars in ldata["registreringer"].values():
            for user_data in bruger_chars.values():
                tekst = f"**{user_data['name']}** - {user_data['spec']} {user_data['class']} - {user_data['ilvl']} ilvl - [Raider.IO](<{user_data['rio']}>)"
                grupper[user_data["rolle"]].append(tekst)

        titel = ldata.get("titel", f"Mythic List ({listename})")
        content = f"**{titel}**\n\n"
        if grupper["tank"]:
            content += "**🛡️ TANKS**\n" + "\n".join(grupper["tank"]) + "\n"
        if grupper["healer"]:
            content += "\n**💚 HEALERS**\n" + "\n".join(grupper["healer"]) + "\n"
        if grupper["dps"]:
            content += "\n**⚔️ DPS**\n" + "\n".join(grupper["dps"]) + "\n"

        content += "\n\u200b\n\u200b"  # tomme linjer

        besked_id = ldata.get("besked_id")
        if not besked_id:
            return

        # Find og rediger beskeden
        for kanal in self.bot.get_all_channels():
            if isinstance(kanal, discord.TextChannel):  # Sikrer kun tekstkanaler
                try:
                    besked = await kanal.fetch_message(besked_id)
                    await besked.edit(content=content)
                    return
                except (discord.NotFound, discord.Forbidden):
                    continue


# Registrer botten som cog
async def setup(bot):
    await bot.add_cog(ZommozBot(bot))
