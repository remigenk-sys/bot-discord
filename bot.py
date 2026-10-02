import discord
import json
import os
import asyncio
import io
import aiohttp
import yt_dlp
import spotipy
import psycopg2
from spotipy.oauth2 import SpotifyClientCredentials
from easy_pil import Editor, Canvas, Font, load_image_async

# ===== INTENTS CONFIGURATION =====
intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # PENTING: Wajib aktif agar event member join terbaca!

client = discord.Client(intents=intents)

# ===== SPOTIFY CREDENTIALS =====
sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
    client_id="YOUR_SPOTIFY_CLIENT_ID", 
    client_secret="YOUR_SPOTIFY_CLIENT_SECRET"
))

# ===== DATABASE =====
DATABASE_URL = os.environ["DATABASE_URL"]

def get_db():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS xp_data (
            user_id TEXT PRIMARY KEY,
            xp INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

def get_xp(user_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT xp FROM xp_data WHERE user_id = %s", (user_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row[0] if row else 0

def set_xp(user_id, xp):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO xp_data (user_id, xp) VALUES (%s, %s)
        ON CONFLICT (user_id) DO UPDATE SET xp = %s
    """, (user_id, xp, xp))
    conn.commit()
    cur.close()
    conn.close()

def get_level(xp):
    level = 0
    required = 100
    while xp >= required:
        xp -= required
        level += 1
        required += 50
    return level

init_db()

LEVEL_UNLOCK = 5
ROLE_NAME = "Level5"

# ===== MUSIC SYSTEM =====
music_queue = []
is_playing = False

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'default_search': 'scsearch', 
    'nocheckcertificate': True,
    'ext': 'mp3',
    'ignoreerrors': True,
    'http_headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

def get_spotify_track_info(url):
    try:
        if "track" in url:
            track = sp.track(url)
            return f"{track['name']} {track['artists'][0]['name']}"
        elif "playlist" in url:
            playlist = sp.playlist_tracks(url, limit=1)
            if playlist['items']:
                track = playlist['items'][0]['track']
                return f"{track['name']} {track['artists'][0]['name']}"
    except Exception as e:
        print(f"Spotify API Error: {e}")
    return None

async def play_next(voice_client):
    global is_playing
    if len(music_queue) > 0:
        is_playing = True
        query = music_queue.pop(0)

        if "spotify.com" in query:
            track_info = get_spotify_track_info(query)
            if track_info:
                query = f"scsearch1:{track_info}"
            else:
                print("Gagal mengambil data dari Spotify.")
                is_playing = False
                await play_next(voice_client)
                return
        elif not query.startswith("http") and not query.startswith("scsearch"):
            query = f"scsearch1:{query}"

        try:
            with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
                info = ydl.extract_info(query, download=False)
                if 'entries' in info:
                    if info['entries'] and len(info['entries']) > 0:
                        info = info['entries'][0]
                    else:
                        print("Lagu tidak ditemukan.")
                        is_playing = False
                        await play_next(voice_client)
                        return
                audio_url = info['url']
            source = discord.FFmpegPCMAudio(audio_url, **FFMPEG_OPTIONS)
            voice_client.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(voice_client), client.loop))
        except Exception as e:
            print(f"Eror saat memutar audio: {e}")
            is_playing = False
            await play_next(voice_client)
    else:
        is_playing = False

# ===== EVENT HANDLERS =====

@client.event
async def on_ready():
    print(f"Bot online: {client.user}")

@client.event
async def on_member_join(member):
    welcome_channel_id = 1472551428798152875 
    channel = client.get_channel(welcome_channel_id)
    if not channel:
        return

    try:
        # Load avatar member
        avatar_image = await load_image_async(str(member.display_avatar.url))
        
        # Load Direct GIF Background
        bg_url = "https://media.giphy.com/media/HSCZMUa1ao17h7l5mg/giphy.gif"
        bg_image = await load_image_async(bg_url)

        # Buat Card Welcome
        background = Editor(bg_image).resize((800, 450))
        
        # PERBAIKAN: .circleify() dipanggil sebelum .resize() agar tidak throw AttributeError
        avatar = Editor(avatar_image).resize((160, 160)).circle_image()

        # Tempelkan Avatar ke Background
        background.paste(avatar, (60, 145))
        
        # Font & Teks
        font_title = Font.poppins(size=35, bold=True)
        font_sub = Font.poppins(size=25, bold=False)

        background.text((250, 170), f"Welcome {member.name}", color="white", font=font_title)
        background.text((250, 220), f"to {member.guild.name}", color="white", font=font_title)
        background.text((250, 270), f"Member #{member.guild.member_count}", color="#a0a0a0", font=font_sub)

        # Simpan ke buffer dan kirim
        file = discord.File(fp=background.image_bytes, filename="welcome.gif")
        await channel.send(content=f"Selamat datang {member.mention}!", file=file)

    except Exception as e:
        print(f"Error saat membuat welcome card: {e}")

@client.event
async def on_message(message):
    global is_playing

    if message.author.bot:
        return

    # ===== XP SYSTEM =====
    user_id = str(message.author.id)
    old_xp = get_xp(user_id)
    old_level = get_level(old_xp)
    new_xp = old_xp + 15
    set_xp(user_id, new_xp)
    new_level = get_level(new_xp)

    if new_level > old_level:
        await message.channel.send(f"🎉 {message.author.mention} naik ke **Level {new_level}**!")
        if new_level >= LEVEL_UNLOCK:
            guild = message.guild
            role = discord.utils.get(guild.roles, name=ROLE_NAME)
            if role and role not in message.author.roles:
                await message.author.add_roles(role)
                await message.channel.send(f"🔓 {message.author.mention} unlock channel secret!")

    # ===== MUSIC COMMANDS =====
    if message.content.startswith("vplay"):
        if not message.author.voice:
            await message.channel.send("❌ Kamu harus masuk voice channel dulu!")
            return

        query = message.content[5:].strip()
        if not query:
            await message.channel.send("❌ Tulis nama lagu atau Link Spotify! Contoh: `vplay Coldplay` atau `vplay [Link Spotify]`")
            return

        voice_channel = message.author.voice.channel
        if message.guild.voice_client is None:
            await voice_channel.connect()

        vc = message.guild.voice_client
        music_queue.append(query)

        if "spotify.com" in query:
            await message.channel.send(f"🟢 **Spotify Link** berhasil ditambahkan ke antrian!")
        else:
            await message.channel.send(f"🎵 **{query}** berhasil ditambahkan ke antrian!")

        if not is_playing:
            await play_next(vc)

    elif message.content.startswith("vskip"):
        if message.guild.voice_client and message.guild.voice_client.is_playing():
            message.guild.voice_client.stop()
            await message.channel.send("⏭ Lagu diskip!")
        else:
            await message.channel.send("❌ Tidak ada lagu yang sedang diputar!")

    elif message.content.startswith("vstop"):
        if message.guild.voice_client:
            music_queue.clear()
            message.guild.voice_client.stop()
            await message.guild.voice_client.disconnect()
            await message.channel.send("⏹️ Musik dihentikan dan bot keluar dari voice channel!")
        else:
            await message.channel.send("❌ Bot tidak ada di voice channel!")

    elif message.content.startswith("vxp"):
        xp = get_xp(user_id)
        level = get_level(xp)
        await message.channel.send(f"⭐ {message.author.mention} | **Level {level}** | **XP: {xp}**")

    elif message.content.startswith("vqueue"):
        if len(music_queue) == 0:
            await message.channel.send("📭 Antrian kosong!")
        else:
            q = "\n".join([f"{i+1}. {url}" for i, url in enumerate(music_queue)])
            await message.channel.send(f"📋 **Antrian:**\n{q}")

    elif message.content.startswith("vhelp"):
        await message.channel.send("""
🎵 **Music Commands:**
`vplay [nama/link spotify]` — Mainkan lagu (Teks biasa / Link Spotify)
`vskip` — Skip lagu sekarang
`vstop` — Stop musik & keluar voice channel
`vqueue` — Lihat antrian lagu

⭐ **Level Commands:**
`vxp` — Cek XP & level kamu
Chat aktif = dapat XP otomatis!
Level 5 = unlock channel secret!
        """)

client.run(os.environ["TOKEN"])
