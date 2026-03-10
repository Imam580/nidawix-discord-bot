import os
import asyncio
from datetime import timedelta

import discord
from discord.ext import commands, tasks
import yt_dlp
import requests

TOKEN = os.getenv("TOKEN")

PREFIX = "!"

AUTOROLE_ID = int(os.getenv("AUTOROLE_ID", "1143085017006866477"))
KICK_CHANNEL = os.getenv("KICK_CHANNEL", "nidawix")
KICK_NOTIFY_CHANNEL_ID = int(os.getenv("KICK_NOTIFY_CHANNEL_ID", "0"))

KICK_URL = f"https://kick.com/{KICK_CHANNEL}"

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

is_live = False


# ---------------- OTO ROL ----------------

@bot.event
async def on_member_join(member):

    role = member.guild.get_role(AUTOROLE_ID)

    if role:
        await member.add_roles(role)


# ---------------- BOT READY ----------------

@bot.event
async def on_ready():

    if not check_kick.is_running():
        check_kick.start()

    print(f"{bot.user} aktif!")


# ---------------- KICK KOMUTU ----------------

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
@commands.has_permissions(moderate_members=True)
async def unmute(ctx, member: discord.Member):

    await member.timeout(None)

    await ctx.send(f"{member} susturması kaldırıldı")


@bot.command()
@commands.has_permissions(manage_messages=True)
async def sil(ctx, amount: int):

    await ctx.channel.purge(limit=amount + 1)


# ---------------- TICKET ----------------

class TicketView(discord.ui.View):

    @discord.ui.button(label="Ticket Aç", style=discord.ButtonStyle.green)

    async def ticket(self, interaction: discord.Interaction, button: discord.ui.Button):

        guild = interaction.guild
        user = interaction.user

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True),
            guild.me: discord.PermissionOverwrite(view_channel=True)
        }

        channel = await guild.create_text_channel(
            name=f"ticket-{user.name}",
            overwrites=overwrites
        )

        await channel.send(f"{user.mention} destek talebi oluşturdu")

        await interaction.response.send_message(
            f"Ticket açıldı: {channel.mention}", ephemeral=True
        )


@bot.command()
async def ticketpanel(ctx):

    await ctx.send("Destek almak için butona bas", view=TicketView())


# ---------------- MÜZİK ----------------

ytdl_format_options = {
    'format': 'bestaudio/best',
    'noplaylist': 'True'
}

ffmpeg_options = {
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)


@bot.command()
async def join(ctx):

    if not ctx.author.voice:
        await ctx.send("Önce bir ses kanalına gir.")
        return

    channel = ctx.author.voice.channel

    await channel.connect()


@bot.command()
async def leave(ctx):

    if ctx.voice_client:
        await ctx.voice_client.disconnect()


@bot.command()
async def play(ctx, url):

    if not ctx.author.voice:
        await ctx.send("Önce bir ses kanalına gir.")
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


# ---------------- KICK YAYIN BİLDİRİM ----------------

@tasks.loop(seconds=60)
async def check_kick():

    global is_live

    try:

        r = requests.get(f"https://kick.com/api/v2/channels/{KICK_CHANNEL}")

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


# ---------------- TOKEN KONTROL ----------------

if not TOKEN:
    raise ValueError("TOKEN Railway Variables kısmında yok.")


bot.run(TOKEN)
