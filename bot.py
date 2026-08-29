import os
import asyncio
import io
import re
from datetime import timedelta

import discord
from discord.ext import commands, tasks
import yt_dlp
import aiohttp


# ============================================================
# AYARLAR
# ============================================================

TOKEN = os.getenv("TOKEN")

PREFIX = "!"

# Yakup TV ID'leri
AUTOROLE_ID = 1543255674148888696
TICKET_CATEGORY_ID = 1543260300940279919
TICKET_LOG_CHANNEL_ID = 1543260370909663332
TICKET_PANEL_CHANNEL_ID = 1543257570951692413

# Kick
KICK_CHANNEL = os.getenv("KICK_CHANNEL", "yakup")
KICK_URL = f"https://kick.com/{KICK_CHANNEL}"
KICK_NOTIFY_CHANNEL_ID = int(os.getenv("KICK_NOTIFY_CHANNEL_ID", "0"))

# ============================================================
# DISCORD BOT
# ============================================================

intents = discord.Intents.all()

bot = commands.Bot(
    command_prefix=PREFIX,
    intents=intents,
    help_command=None,
    case_insensitive=True
)

kick_was_live = False


# ============================================================
# RENKLER
# ============================================================

GREEN = discord.Color.green()
RED = discord.Color.red()
BLUE = discord.Color.blue()
ORANGE = discord.Color.orange()


# ============================================================
# YARDIMCI FONKSİYONLAR
# ============================================================

def safe_channel_name(text: str) -> str:
    text = text.lower()

    replacements = {
        "ı": "i",
        "ğ": "g",
        "ü": "u",
        "ş": "s",
        "ö": "o",
        "ç": "c"
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")

    return text[:40] or "kullanici"


def parse_duration(duration: str):
    match = re.fullmatch(
        r"(\d+)(s|m|h|d)",
        duration.lower().strip()
    )

    if not match:
        return None

    value = int(match.group(1))
    unit = match.group(2)

    if unit == "s":
        return timedelta(seconds=value)

    if unit == "m":
        return timedelta(minutes=value)

    if unit == "h":
        return timedelta(hours=value)

    if unit == "d":
        return timedelta(days=value)

    return None


# ============================================================
# TICKET NUMARASI
# ============================================================

async def get_next_ticket_number(guild: discord.Guild):

    highest_number = 0

    # --------------------------------------------------------
    # Önce açık ticketları kontrol et
    # --------------------------------------------------------

    category = guild.get_channel(TICKET_CATEGORY_ID)

    if isinstance(category, discord.CategoryChannel):

        for channel in category.text_channels:

            match = re.match(
                r"ticket-(\d+)",
                channel.name
            )

            if match:
                number = int(match.group(1))
                highest_number = max(
                    highest_number,
                    number
                )

    # --------------------------------------------------------
    # Sonra LOG kanalını kontrol et
    # Böylece silinen ticketların numarası da unutulmaz.
    # --------------------------------------------------------

    log_channel = guild.get_channel(
        TICKET_LOG_CHANNEL_ID
    )

    if isinstance(log_channel, discord.TextChannel):

        try:

            async for message in log_channel.history(
                limit=None
            ):

                match = re.search(
                    r"Ticket #(\d+)",
                    message.content
                )

                if match:

                    number = int(match.group(1))

                    highest_number = max(
                        highest_number,
                        number
                    )

                if message.embeds:

                    for embed in message.embeds:

                        match = re.search(
                            r"Ticket #(\d+)",
                            embed.title or ""
                        )

                        if match:

                            number = int(match.group(1))

                            highest_number = max(
                                highest_number,
                                number
                            )

        except Exception as e:

            print(
                "Ticket numarası log kontrol hatası:",
                e
            )

    return highest_number + 1


# ============================================================
# TICKET AÇAN KİŞİNİN TICKETINI BUL
# ============================================================

def find_user_ticket(
    category: discord.CategoryChannel,
    user_id: int
):

    for channel in category.text_channels:

        if channel.topic == f"ticket_owner:{user_id}":
            return channel

    return None


# ============================================================
# TICKET TRANSCRIPT
# ============================================================

async def create_transcript(
    channel: discord.TextChannel
):

    lines = []

    async for message in channel.history(
        limit=None,
        oldest_first=True
    ):

        created = message.created_at.strftime(
            "%d.%m.%Y %H:%M:%S"
        )

        content = message.content or "[Mesaj içeriği yok]"

        line = (
            f"[{created}] "
            f"{message.author} "
            f"(ID: {message.author.id}): "
            f"{content}"
        )

        if message.attachments:

            attachments = ", ".join(
                attachment.url
                for attachment in message.attachments
            )

            line += f" | Ekler: {attachments}"

        lines.append(line)

    if not lines:
        return "Ticket içerisinde mesaj bulunamadı."

    return "\n".join(lines)


# ============================================================
# TICKET LOG
# ============================================================

async def send_ticket_log(
    channel: discord.TextChannel,
    closed_by: discord.Member,
    reason: str
):

    log_channel = channel.guild.get_channel(
        TICKET_LOG_CHANNEL_ID
    )

    if not isinstance(log_channel, discord.TextChannel):
        print("Ticket log kanalı bulunamadı.")
        return

    transcript = await create_transcript(channel)

    embed = discord.Embed(
        title="📁 Ticket Kapatıldı",
        color=RED
    )

    embed.add_field(
        name="Ticket",
        value=f"`{channel.name}`",
        inline=False
    )

    embed.add_field(
        name="Kapatan",
        value=f"{closed_by.mention}\n`{closed_by.id}`",
        inline=True
    )

    embed.add_field(
        name="Sebep",
        value=reason,
        inline=True
    )

    file_buffer = io.BytesIO(
        transcript.encode("utf-8")
    )

    file = discord.File(
        file_buffer,
        filename=f"{channel.name}.txt"
    )

    await log_channel.send(
        embed=embed,
        file=file
    )


# ============================================================
# TICKET KAPATMA
# ============================================================

class CloseTicketView(discord.ui.View):

    def __init__(self):

        super().__init__(timeout=None)

    # --------------------------------------------------------
    # KULLANICI KAPAT
    # --------------------------------------------------------

    @discord.ui.button(
        label="Kullanıcı Kapat",
        emoji="🔒",
        style=discord.ButtonStyle.secondary,
        custom_id="yakup_ticket_user_close"
    )
    async def user_close(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        channel = interaction.channel

        if not isinstance(
            channel,
            discord.TextChannel
        ):
            return

        if channel.topic != (
            f"ticket_owner:{interaction.user.id}"
        ):

            await interaction.response.send_message(
                "❌ Bu ticket sana ait değil.",
                ephemeral=True
            )

            return

        await interaction.response.defer(
            ephemeral=True
        )

        await channel.set_permissions(
            interaction.user,
            view_channel=False,
            send_messages=False
        )

        await interaction.followup.send(
            "🔒 Ticket senin için kapatıldı. "
            "Yetkililer ticketı görmeye devam edebilir.",
            ephemeral=True
        )

    # --------------------------------------------------------
    # YETKİLİ KAPAT
    # --------------------------------------------------------

    @discord.ui.button(
        label="Yetkili Kapat",
        emoji="🔴",
        style=discord.ButtonStyle.danger,
        custom_id="yakup_ticket_staff_close"
    )
    async def staff_close(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if not (
            interaction.user.guild_permissions.administrator
            or
            interaction.user.guild_permissions.manage_channels
        ):

            await interaction.response.send_message(
                "❌ Bu butonu sadece yetkililer kullanabilir.",
                ephemeral=True
            )

            return

        channel = interaction.channel

        if not isinstance(
            channel,
            discord.TextChannel
        ):
            return

        await interaction.response.defer(
            ephemeral=True
        )

        await send_ticket_log(
            channel,
            interaction.user,
            "Yetkili tarafından kapatıldı."
        )

        await asyncio.sleep(2)

        try:
            await channel.delete(
                reason=(
                    f"Ticket kapatıldı: "
                    f"{interaction.user}"
                )
            )

        except Exception as e:

            print(
                "Ticket silme hatası:",
                e
            )

@bot.command()
async def instagram(ctx):
    await ctx.send("📸 Instagram: https://www.instagram.com/yakuptv.034/")


@bot.command()
async def x(ctx):
    await ctx.send("𝕏 X: https://x.com/Yakuptv34")


@bot.command()
async def youtube(ctx):
    await ctx.send("▶️ YouTube: https://www.youtube.com/@YakupTV.1")


# ============================================================
# TICKET TÜRÜ SEÇME
# ============================================================

class TicketSelect(discord.ui.Select):

    def __init__(self):

        options = [

            discord.SelectOption(
                label="Kick Ban İtiraz",
                description="Kick banı hakkında itiraz oluştur",
                emoji="🎮",
                value="Kick Ban İtiraz"
            ),

            discord.SelectOption(
                label="Ekibe Katılım",
                description="Yakup TV ekibine katılmak için",
                emoji="👥",
                value="Ekibe Katılım"
            ),

            discord.SelectOption(
                label="İş Birliği",
                description="İş birliği teklifleri için",
                emoji="🤝",
                value="İş Birliği"
            ),

            discord.SelectOption(
                label="Diğer",
                description="Diğer konular için",
                emoji="❓",
                value="Diğer"
            )

        ]

        super().__init__(
            placeholder="🎫 Ticket türünü seç",
            options=options,
            custom_id="yakup_ticket_select"
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        guild = interaction.guild
        user = interaction.user

        if guild is None:

            await interaction.response.send_message(
                "Bu işlem sadece sunucuda kullanılabilir.",
                ephemeral=True
            )

            return

        category = guild.get_channel(
            TICKET_CATEGORY_ID
        )

        if not isinstance(
            category,
            discord.CategoryChannel
        ):

            await interaction.response.send_message(
                "❌ Ticket kategorisi bulunamadı.",
                ephemeral=True
            )

            return

        # ----------------------------------------------------
        # Zaten ticket var mı?
        # ----------------------------------------------------

        existing = find_user_ticket(
            category,
            user.id
        )

        if existing:

            await interaction.response.send_message(
                f"❌ Zaten açık bir ticketın var:\n"
                f"{existing.mention}",
                ephemeral=True
            )

            return

        reason = self.values[0]

        # ----------------------------------------------------
        # Ticket numarası
        # ----------------------------------------------------

        ticket_number = await get_next_ticket_number(
            guild
        )

        # ----------------------------------------------------
        # Kanal adı
        # ----------------------------------------------------

        safe_reason = safe_channel_name(
            reason
        )

        safe_user = safe_channel_name(
            user.display_name
        )

        channel_name = (
            f"ticket-{ticket_number:03d}-"
            f"{safe_reason}-"
            f"{safe_user}"
        )

        # Discord kanal isim limiti
        channel_name = channel_name[:100]

        # ----------------------------------------------------
        # Yetkiler
        # ----------------------------------------------------

        overwrites = {

            guild.default_role:
                discord.PermissionOverwrite(
                    view_channel=False
                ),

            user:
                discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    attach_files=True,
                    embed_links=True
                ),

            guild.me:
                discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_channels=True,
                    manage_messages=True,
                    attach_files=True,
                    embed_links=True
                )
        }

        # ----------------------------------------------------
        # Yönetici / Manage Channels yetkilileri
        # ticketı görebilsin
        # ----------------------------------------------------

        for member in guild.members:

            if (
                member.guild_permissions.administrator
                or
                member.guild_permissions.manage_channels
            ):

                overwrites[member] = (
                    discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True
                    )
                )

        # ----------------------------------------------------
        # Kanal oluştur
        # ----------------------------------------------------

        try:

            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                topic=f"ticket_owner:{user.id}",
                overwrites=overwrites,
                reason=(
                    f"Ticket #{ticket_number} - "
                    f"{reason}"
                )
            )

        except Exception as e:

            print(
                "Ticket oluşturma hatası:",
                e
            )

            await interaction.response.send_message(
                "❌ Ticket oluşturulamadı. "
                "Botun kanal oluşturma yetkisini kontrol et.",
                ephemeral=True
            )

            return

        # ----------------------------------------------------
        # Ticket embed
        # ----------------------------------------------------

        embed = discord.Embed(
            title=f"🎫 Ticket #{ticket_number:03d}",
            description=(
                f"**Konu:** {reason}\n"
                f"**Kullanıcı:** {user.mention}\n\n"
                "Yetkililer en kısa sürede ilgilenecektir."
            ),
            color=BLUE
        )

        embed.set_footer(
            text="Yakup TV Destek Sistemi"
        )

        await channel.send(
            content=user.mention,
            embed=embed,
            view=CloseTicketView()
        )

        # ----------------------------------------------------
        # Log - ticket açıldı
        # ----------------------------------------------------

        log_channel = guild.get_channel(
            TICKET_LOG_CHANNEL_ID
        )

        if isinstance(
            log_channel,
            discord.TextChannel
        ):

            log_embed = discord.Embed(
                title="📂 Yeni Ticket Açıldı",
                color=GREEN
            )

            log_embed.add_field(
                name="Ticket",
                value=f"`Ticket #{ticket_number:03d}`",
                inline=True
            )

            log_embed.add_field(
                name="Kullanıcı",
                value=(
                    f"{user.mention}\n"
                    f"`{user.id}`"
                ),
                inline=True
            )

            log_embed.add_field(
                name="Konu",
                value=reason,
                inline=False
            )

            await log_channel.send(
                embed=log_embed
            )

        await interaction.response.send_message(
            f"✅ Ticket oluşturuldu: {channel.mention}",
            ephemeral=True
        )


# ============================================================
# TICKET PANEL
# ============================================================

class TicketPanelView(discord.ui.View):

    def __init__(self):

        super().__init__(timeout=None)

        self.add_item(
            TicketSelect()
        )


# ============================================================
# OTOMATİK TICKET PANEL
# ============================================================

async def ensure_ticket_panel():

    channel = bot.get_channel(
        TICKET_PANEL_CHANNEL_ID
    )

    if not isinstance(
        channel,
        discord.TextChannel
    ):

        print(
            "❌ Ticket panel kanalı bulunamadı."
        )

        return

    try:

        async for message in channel.history(
            limit=50
        ):

            if (
                message.author == bot.user
                and message.components
            ):

                print(
                    "✅ Ticket panel zaten mevcut."
                )

                return

        embed = discord.Embed(
            title="🎫 Yakup TV Destek Sistemi",
            description=(
                "Destek almak için aşağıdaki menüden "
                "ilgili ticket türünü seç.\n\n"
                "🎮 **Kick Ban İtiraz**\n"
                "👥 **Ekibe Katılım**\n"
                "🤝 **İş Birliği**\n"
                "❓ **Diğer**"
            ),
            color=BLUE
        )

        embed.set_footer(
            text="Yakup TV • Destek Sistemi"
        )

        await channel.send(
            embed=embed,
            view=TicketPanelView()
        )

        print(
            "✅ Ticket panel otomatik oluşturuldu."
        )

    except Exception as e:

        print(
            "❌ Ticket panel hatası:",
            e
        )


# ============================================================
# BOT READY
# ============================================================

@bot.event
async def on_ready():

    print(
        f"✅ {bot.user} aktif!"
    )

    # Persistent sistemler
    try:

        bot.add_view(
            TicketPanelView()
        )

        bot.add_view(
            CloseTicketView()
        )

    except Exception as e:

        print(
            "Persistent View hatası:",
            e
        )

    if not check_kick.is_running():

        check_kick.start()

    await ensure_ticket_panel()


# ============================================================
# OTO ROL
# ============================================================

@bot.event
async def on_member_join(
    member: discord.Member
):

    role = member.guild.get_role(
        AUTOROLE_ID
    )

    if not role:

        print(
            "❌ Oto rol bulunamadı."
        )

        return

    try:

        await member.add_roles(
            role,
            reason="Otomatik rol sistemi"
        )

        print(
            f"🎭 Oto rol verildi: {member}"
        )

    except Exception as e:

        print(
            "Oto rol hatası:",
            e
        )


# ============================================================
# KICK KOMUTU
# ============================================================

@bot.command()
async def kick(ctx):

    await ctx.send(
        f"🔴 Kick: {KICK_URL}"
    )


# ============================================================
# YARDIM
# ============================================================

@bot.command()
async def yardim(ctx):

    embed = discord.Embed(
        title="🤖 Yakup TV Bot",
        description="Kullanabileceğin komutlar:",
        color=BLUE
    )

    embed.add_field(
        name="🔨 Moderasyon",
        value=(
            "`!ban @üye sebep`\n"
            "`!mute @üye 10m`\n"
            "`!unmute @üye`\n"
            "`!sil 10`"
        ),
        inline=False
    )

    embed.add_field(
        name="🎵 Müzik",
        value=(
            "`!play şarkı/link`\n"
            "`!stop`\n"
            "`!leave`"
        ),
        inline=False
    )

    embed.add_field(
        name="🔗 Diğer",
        value="`!kick`",
        inline=False
    )

    await ctx.send(
        embed=embed
    )


# ============================================================
# BAN
# ============================================================

@bot.command()
@commands.has_permissions(
    ban_members=True
)
async def ban(
    ctx,
    member: discord.Member,
    *,
    reason="Sebep belirtilmedi"
):

    try:

        await member.ban(
            reason=reason
        )

        await ctx.send(
            f"🔨 {member.mention} banlandı.\n"
            f"Sebep: **{reason}**"
        )

    except Exception as e:

        await ctx.send(
            "❌ Bu üyeyi banlayamadım."
        )

        print(
            "Ban hatası:",
            e
        )


# ============================================================
# MUTE
# ============================================================

@bot.command()
@commands.has_permissions(
    moderate_members=True
)
async def mute(
    ctx,
    member: discord.Member,
    duration: str
):

    td = parse_duration(
        duration
    )

    if not td:

        await ctx.send(
            "❌ Süre hatalı.\n"
            "Örnek: `10m`, `2h`, `1d`"
        )

        return

    try:

        await member.timeout(
            td,
            reason=f"{ctx.author} tarafından mute"
        )

        await ctx.send(
            f"🔇 {member.mention} "
            f"`{duration}` süreyle susturuldu."
        )

    except Exception as e:

        await ctx.send(
            "❌ Kullanıcı susturulamadı."
        )

        print(
            "Mute hatası:",
            e
        )


# ============================================================
# UNMUTE
# ============================================================

@bot.command()
@commands.has_permissions(
    moderate_members=True
)
async def unmute(
    ctx,
    member: discord.Member
):

    try:

        await member.timeout(
            None,
            reason=f"{ctx.author} tarafından unmute"
        )

        await ctx.send(
            f"🔊 {member.mention} "
            "susturması kaldırıldı."
        )

    except Exception as e:

        await ctx.send(
            "❌ Susturma kaldırılamadı."
        )

        print(
            "Unmute hatası:",
            e
        )


# ============================================================
# MESAJ SİL
# ============================================================

@bot.command()
@commands.has_permissions(
    manage_messages=True
)
async def sil(
    ctx,
    amount: int
):

    if amount < 1:

        await ctx.send(
            "❌ En az 1 mesaj silmelisin."
        )

        return

    try:

        await ctx.channel.purge(
            limit=amount + 1
        )

    except Exception as e:

        await ctx.send(
            "❌ Mesajlar silinemedi."
        )

        print(
            "Silme hatası:",
            e
        )


# ============================================================
# MANUEL TICKET PANEL
# ============================================================

@bot.command()
@commands.has_permissions(
    administrator=True
)
async def ticketpanel(ctx):

    embed = discord.Embed(
        title="🎫 Yakup TV Destek Sistemi",
        description=(
            "Aşağıdaki menüden ticket türünü seç."
        ),
        color=BLUE
    )

    await ctx.send(
        embed=embed,
        view=TicketPanelView()
    )


# ============================================================
# MÜZİK
# ============================================================

ytdl_options = {
    "format": "bestaudio/best",
    "quiet": True,
    "noplaylist": True,
    "default_search": "ytsearch1",
    "extractor_args": {
        "youtube": {
            "player_client": [
                "android"
            ]
        }
    }
}

ffmpeg_options = {
    "before_options": (
        "-reconnect 1 "
        "-reconnect_streamed 1 "
        "-reconnect_delay_max 5"
    ),
    "options": "-vn"
}


@bot.command()
async def play(
    ctx,
    *,
    query
):

    if not ctx.author.voice:

        await ctx.send(
            "🔊 Önce bir ses kanalına gir."
        )

        return

    try:

        if not ctx.voice_client:

            await ctx.author.voice.channel.connect()

        voice = ctx.voice_client

        def get_audio():

            with yt_dlp.YoutubeDL(
                ytdl_options
            ) as ydl:

                info = ydl.extract_info(
                    query,
                    download=False
                )

                if "entries" in info:

                    info = info["entries"][0]

                return (
                    info["url"],
                    info["title"]
                )

        url, title = await asyncio.to_thread(
            get_audio
        )

        source = discord.FFmpegPCMAudio(
            url,
            executable="ffmpeg",
            **ffmpeg_options
        )

        if voice.is_playing():

            voice.stop()

        voice.play(
            source
        )

        await ctx.send(
            f"🎵 Çalıyor: **{title}**"
        )

    except Exception as e:

        await ctx.send(
            "❌ Müzik açılırken hata oluştu."
        )

        print(
            "Müzik hatası:",
            e
        )


@bot.command()
async def stop(ctx):

    if ctx.voice_client:

        ctx.voice_client.stop()

        await ctx.send(
            "⏹️ Müzik durduruldu."
        )


@bot.command()
async def leave(ctx):

    if ctx.voice_client:

        await ctx.voice_client.disconnect()

        await ctx.send(
            "👋 Ses kanalından çıktım."
        )


# ============================================================
# KICK CANLI YAYIN KONTROLÜ
# ============================================================

async def fetch_kick_channel():

    url = (
        f"https://kick.com/api/v2/channels/"
        f"{KICK_CHANNEL}"
    )

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64)"
        ),
        "Accept": "application/json"
    }

    timeout = aiohttp.ClientTimeout(
        total=15
    )

    async with aiohttp.ClientSession(
        timeout=timeout
    ) as session:

        async with session.get(
            url,
            headers=headers
        ) as response:

            if response.status != 200:

                print(
                    f"Kick HTTP {response.status}"
                )

                return None

            return await response.json()


@tasks.loop(minutes=3)
async def check_kick():

    global kick_was_live

    if not KICK_NOTIFY_CHANNEL_ID:

        return

    try:

        data = await fetch_kick_channel()

        if not data:

            return

        livestream = data.get(
            "livestream"
        )

        discord_channel = bot.get_channel(
            KICK_NOTIFY_CHANNEL_ID
        )

        if not isinstance(
            discord_channel,
            discord.TextChannel
        ):

            print(
                "❌ Kick duyuru kanalı bulunamadı."
            )

            return

        # ----------------------------------------------------
        # YAYIN BAŞLADI
        # ----------------------------------------------------

        if livestream and not kick_was_live:

            kick_was_live = True

            title = livestream.get(
                "session_title",
                "Yakup TV canlı yayında!"
            )

            viewers = livestream.get(
                "viewer_count",
                0
            )

            embed = discord.Embed(
                title="🔴 YAYINDAYIZ!",
                description=(
                    f"**{KICK_CHANNEL}** "
                    "şu anda canlı yayında!\n\n"
                    f"🔗 {KICK_URL}"
                ),
                color=RED
            )

            embed.add_field(
                name="Yayın",
                value=title,
                inline=False
            )

            embed.add_field(
                name="İzleyici",
                value=str(viewers),
                inline=True
            )

            await discord_channel.send(
                content="@everyone",
                embed=embed,
                allowed_mentions=discord.AllowedMentions(
                    everyone=True
                )
            )

            print(
                "🔴 Kick yayın duyurusu gönderildi."
            )

        # ----------------------------------------------------
        # YAYIN BİTTİ
        # ----------------------------------------------------

        elif not livestream:

            kick_was_live = False

    except Exception as e:

        print(
            "Kick kontrol hatası:",
            e
        )


@check_kick.before_loop
async def before_kick():

    await bot.wait_until_ready()


# ============================================================
# KOMUT HATALARI
# ============================================================

@bot.event
async def on_command_error(
    ctx,
    error
):

    if isinstance(
        error,
        commands.CommandNotFound
    ):
        return

    if isinstance(
        error,
        commands.MissingPermissions
    ):

        await ctx.send(
            "❌ Bu komutu kullanmak için yetkin yok."
        )

        return

    if isinstance(
        error,
        commands.MissingRequiredArgument
    ):

        await ctx.send(
            "❌ Eksik bilgi girdin."
        )

        return

    if isinstance(
        error,
        commands.MemberNotFound
    ):

        await ctx.send(
            "❌ Üye bulunamadı."
        )

        return

    if isinstance(
        error,
        commands.BadArgument
    ):

        await ctx.send(
            "❌ Hatalı kullanım."
        )

        return

    print(
        "Komut hatası:",
        error
    )


# ============================================================
# TOKEN
# ============================================================

if not TOKEN:

    raise ValueError(
        "TOKEN bulunamadı. Railway Variables kısmına TOKEN ekle."
    )


# ============================================================
# BOTU BAŞLAT
# ============================================================

bot.run(TOKEN)
