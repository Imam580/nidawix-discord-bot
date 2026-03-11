import os
import asyncio
import io
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
TICKET_PANEL_CHANNEL_ID = int(os.getenv("TICKET_PANEL_CHANNEL_ID", "0"))
TICKET_CATEGORY_ID = 1479805090390081646

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

async def ensure_ticket_panel():

    channel = bot.get_channel(TICKET_PANEL_CHANNEL_ID)

    if not channel:
        print("Ticket panel kanalı bulunamadı")
        return

    async for msg in channel.history(limit=20):

        if msg.author == bot.user and msg.components:
            return

    embed = discord.Embed(
        title="🎫 Destek Sistemi",
        description="Aşağıdan ticket türünü seç"
    )

    await channel.send(embed=embed, view=TicketPanel())

    print("Ticket panel otomatik oluşturuldu")

@bot.event
async def on_ready():

    bot.add_view(TicketPanel())
    bot.add_view(CloseTicket())

    if not check_kick.is_running():
        check_kick.start()

    await ensure_ticket_panel()

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

async def get_next_ticket_number(guild):

    category = guild.get_channel(TICKET_CATEGORY_ID)

    if not category:
        return 1

    tickets = [c for c in category.text_channels if c.name.startswith("ticket-")]

    numbers = []

    for channel in tickets:
        try:
            num = int(channel.name.split("-")[1])
            numbers.append(num)
        except:
            pass

    if not numbers:
        return 1

    return max(numbers) + 1

class TicketSelect(discord.ui.Select):

    def __init__(self):

        options = [

            discord.SelectOption(label="Kick Ban İtiraz", emoji="🎮"),
            discord.SelectOption(label="Ekibe Katılım", emoji="👥"),
            discord.SelectOption(label="İş Birliği", emoji="🤝"),
            discord.SelectOption(label="Diğer", emoji="❓")

        ]

       super().__init__(
    placeholder="Ticket türünü seç",
    options=options,
    custom_id="ticket_select_menu"
)

    async def callback(self, interaction: discord.Interaction):

        guild = interaction.guild
        user = interaction.user
        reason = self.values[0]

        # Kullanıcı zaten ticket açmış mı
        for channel in guild.text_channels:
            if str(user.id) in channel.topic if channel.topic else False:
                await interaction.response.send_message(
                    "Zaten açık ticketın var.",
                    ephemeral=True
                )
                return

        overwrites = {

            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True),
            guild.me: discord.PermissionOverwrite(view_channel=True)

        }

        # Ticket kanal adı
        safe_reason = reason.lower().replace(" ", "-")
        safe_name = user.name.lower()

        ticket_number = await get_next_ticket_number(guild)

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

   class CloseTicket(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Kullanıcı Kapat",
        style=discord.ButtonStyle.gray,
        custom_id="ticket_user_close"
    )
    async def user_close(self, interaction: discord.Interaction, button: discord.ui.Button):

        await interaction.response.defer(ephemeral=True)

        channel = interaction.channel
        user = interaction.user

        await channel.set_permissions(user, view_channel=False)

        await interaction.followup.send(
            "Ticket senin için kapatıldı. Yetkililer inceleyebilir.",
            ephemeral=True
        )

    @discord.ui.button(
        label="Yetkili Kapat",
        style=discord.ButtonStyle.red,
        custom_id="ticket_staff_close"
    )
    async def staff_close(self, interaction: discord.Interaction, button: discord.ui.Button):

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "Bunu sadece yöneticiler yapabilir.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        channel = interaction.channel
        user = interaction.user
    async def staff_close(self, interaction: discord.Interaction, button: discord.ui.Button):

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "Bunu sadece yöneticiler yapabilir.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        channel = interaction.channel
        user = interaction.user

        messages = []

        try:
            async for msg in channel.history(limit=None, oldest_first=True):
                content = msg.content or ""
                attachments = ", ".join(a.url for a in msg.attachments) if msg.attachments else ""
                line = f"{msg.author}: {content}"
                if attachments:
                    line += f" [Ekler: {attachments}]"
                messages.append(line)

            transcript = "\n".join(messages) if messages else "Mesaj yok."

            log_channel = bot.get_channel(LOG_CHANNEL_ID)

            if log_channel:
                file_buffer = io.BytesIO(transcript.encode("utf-8"))
                discord_file = discord.File(file_buffer, filename=f"{channel.name}.txt")

                await log_channel.send(
                    f"Ticket kapatıldı\nKanal: {channel.name}\nKapatan: {user}",
                    file=discord_file
                )

        except Exception as e:
            print("Ticket kapatma/log hatası:", e)

        await asyncio.sleep(2)
        await channel.delete()


@bot.command()
@commands.has_permissions(administrator=True)
async def ticketpanel(ctx):

    async for msg in ctx.channel.history(limit=30):
        if msg.author == bot.user and msg.components:
            try:
                await msg.delete()
            except:
                pass

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
            print("Kick duyuru kanalı bulunamadı")
            return

        livestream = data.get("livestream")

        if livestream and not is_live:

            is_live = True

            await channel.send(
                f"@everyone 🔴 **Yayındayız!**\n{KICK_URL}"
            )

        if not livestream:

            is_live = False

    except Exception as e:

        print("Kick kontrol hatası:", e)


# ---------------- TOKEN ----------------

if not TOKEN:
    raise ValueError("TOKEN Railway Variables kısmında yok.")

bot.run(TOKEN)
