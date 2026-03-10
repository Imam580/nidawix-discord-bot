import os
import asyncio
from datetime import timedelta

import discord
from discord.ext import commands, tasks
import yt_dlp
import requests

TOKEN = os.getenv("TOKEN")

AUTOROLE_ID = int(os.getenv("AUTOROLE_ID", "0"))
KICK_CHANNEL = os.getenv("KICK_CHANNEL", "nidawix")
KICK_NOTIFY_CHANNEL_ID = int(os.getenv("KICK_NOTIFY_CHANNEL_ID", "0"))
LOG_CHANNEL_ID = int(os.getenv("TICKET_LOG_CHANNEL_ID", "0"))

PREFIX = "!"

intents = discord.Intents.all()

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

is_live = False

KICK_URL = f"https://kick.com/{KICK_CHANNEL}"

# ---------------- OTO ROL ----------------

@bot.event
async def on_member_join(member):

    role = member.guild.get_role(AUTOROLE_ID)

    if role:
        await member.add_roles(role)


# ---------------- READY ----------------

@bot.event
async def on_ready():

    bot.add_view(TicketPanel())
    bot.add_view(CloseTicket())

    if not check_kick.is_running():
        check_kick.start()

    print(f"{bot.user} aktif!")


# ---------------- KICK KOMUT ----------------

@bot.command()
async def kick(ctx):

    await ctx.send(KICK_URL)


# ---------------- MODERASYON ----------------

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="Sebep yok"):

    await member.ban(reason=reason)

    await ctx.send(f"{member} banlandı")


@bot.command()
@commands.has_permissions(moderate_members=True)
async def mute(ctx, member: discord.Member, minutes: int):

    until = discord.utils.utcnow() + timedelta(minutes=minutes)

    await member.timeout(until)

    await ctx.send(f"{member} {minutes} dakika susturuldu")


@bot.command()
async def unmute(ctx, member: discord.Member):

    await member.timeout(None)

    await ctx.send(f"{member} susturması kaldırıldı")


@bot.command()
async def sil(ctx, amount: int):

    await ctx.channel.purge(limit=amount + 1)


# ---------------- TICKET SYSTEM ----------------

class TicketSelect(discord.ui.Select):

    def __init__(self):

        options = [

            discord.SelectOption(label="Kick Ban İtiraz", emoji="🎮"),
            discord.SelectOption(label="Ekibe Katılım", emoji="👥"),
            discord.SelectOption(label="İş Birliği", emoji="🤝"),
            discord.SelectOption(label="Diğer", emoji="❓")

        ]

        super().__init__(placeholder="Ticket türünü seç", options=options)

    async def callback(self, interaction: discord.Interaction):

        guild = interaction.guild
        user = interaction.user
        reason = self.values[0]

        existing = discord.utils.get(guild.text_channels, name=f"ticket-{user.id}")

        if existing:

            await interaction.response.send_message(
                f"Zaten açık ticketın var: {existing.mention}",
                ephemeral=True
            )

            return

        overwrites = {

            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True),
            guild.me: discord.PermissionOverwrite(view_channel=True)

        }

        channel = await guild.create_text_channel(
           name=f"ticket-{user.name}".lower(),
           overwrites=overwrites
        )

        embed = discord.Embed(
            title="🎫 Ticket Açıldı",
            description=f"Konu: **{reason}**\nKullanıcı: {user.mention}"
        )

        await channel.send(embed=embed, view=CloseTicket())

        await interaction.response.send_message(
            f"Ticket oluşturuldu: {channel.mention}",
            ephemeral=True
        )


class TicketPanel(discord.ui.View):

    def __init__(self):

        super().__init__(timeout=None)

        self.add_item(TicketSelect())


class CloseTicket(discord.ui.View):

    def __init__(self):

        super().__init__(timeout=None)

    @discord.ui.button(label="Ticket Kapat", style=discord.ButtonStyle.red)

    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):

        channel = interaction.channel
        user = interaction.user

        messages = []

        async for msg in channel.history(limit=None):

            messages.append(f"{msg.author}: {msg.content}")

        messages.reverse()

        transcript = "\n".join(messages)

        log_channel = bot.get_channel(LOG_CHANNEL_ID)

        if log_channel:

            file = discord.File(
                fp=discord.File(
                    fp=bytes(transcript, "utf-8"),
                    filename=f"{channel.name}.txt"
                ).fp,
                filename=f"{channel.name}.txt"
            )

            await log_channel.send(
                f"Ticket kapatıldı\nKanal: {channel.name}\nKapatan: {user}",
                file=file
            )

        await interaction.response.send_message("Ticket kapatılıyor...", ephemeral=True)

        await asyncio.sleep(3)

        await channel.delete()


@bot.command()
async def ticketpanel(ctx):

    embed = discord.Embed(
        title="🎫 Destek Sistemi",
        description="Aşağıdan ticket türünü seç"
    )

    await ctx.send(embed=embed, view=TicketPanel())


# ---------------- MUSIC ----------------

ytdl_format_options = {
    'format': 'bestaudio/best',
    'noplaylist': 'True'
}

ffmpeg_options = {
    'options': '-vn'
}


@bot.command()
async def join(ctx):

    if not ctx.author.voice:
        await ctx.send("Önce bir ses kanalına gir.")
        return

    await ctx.author.voice.channel.connect()


@bot.command()
async def leave(ctx):

    if ctx.voice_client:
        await ctx.voice_client.disconnect()


@bot.command()
async def play(ctx, url):

    if not ctx.author.voice:
        await ctx.send("Önce ses kanalına gir.")
        return

    voice = ctx.voice_client

    if not voice:
        voice = await ctx.author.voice.channel.connect()

    with yt_dlp.YoutubeDL(ytdl_format_options) as ydl:

        info = ydl.extract_info(url, download=False)

        URL = info['url']

    source = discord.FFmpegPCMAudio(URL, **ffmpeg_options)

    voice.play(source)


@bot.command()
async def stop(ctx):

    if ctx.voice_client:
        ctx.voice_client.stop()


# ---------------- KICK LIVE ----------------

@tasks.loop(seconds=180)
async def check_kick():

    global is_live

    try:

        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        r = requests.get(
            f"https://kick.com/api/v2/channels/{KICK_CHANNEL}",
            headers=headers
        )

        data = r.json()

        channel = bot.get_channel(KICK_NOTIFY_CHANNEL_ID)

        if not channel:
            return

        if data["livestream"] != None and is_live == False:

            is_live = True

            await channel.send(
                f"@everyone Yayındayız!\n{KICK_URL}"
            )

        if data["livestream"] == None:

            is_live = False

    except Exception as e:

        print("Kick kontrol hatası:", e)


# ---------------- TOKEN ----------------

if not TOKEN:
    raise ValueError("TOKEN Railway Variables kısmında yok.")

bot.run(TOKEN)
