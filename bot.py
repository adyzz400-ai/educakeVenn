import asyncio
import os
import time
import discord
from discord.ext import commands
from aiohttp import web

from config import DISCORD_TOKEN, BOT_NAME, BOT_VERSION
from embeds import menu_embed

# We move the heavy imports inside the commands or use a try/except 
# to prevent the bot from crashing on boot if voboai is broken.
try:
    from voboai.educake import login, save_storage_state, fetch_assignments, open_assignment, extract_questions, CloudflareChallenge, EducakeLoginError, EducakeError
    from voboai.solver import solve_question
    EDUC_AVAILABLE = True
except Exception as e:
    print(f"[DeepHat] Warning: Educake module failed to load: {e}")
    EDUC_AVAILABLE = False

sessions = {}
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# --- HEALTH SERVER (Keep it lightweight) ---
async def health(request):
    return web.Response(text="VoboAi Educake is online.")

async def start_health_server():
    app = web.Application()
    app.router.add_get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"[DeepHat] Health server started on port {port}")

# --- BOT COMMANDS ---

@bot.event
async def on_ready():
    try:
        await bot.tree.sync()
        print(f"Logged in as {bot.user}")
        print(f"{BOT_NAME} v{BOT_VERSION} online.")
    except Exception as e:
        print(f"Error syncing tree: {e}")

@bot.tree.command(name="menu", description="Open the VoboAi Educake menu.")
async def menu(interaction: discord.Interaction):
    if not EDUC_AVAILABLE:
        await interaction.response.send_message("⚠️ System error: Educake module not loaded.", ephemeral=True)
        return

    connected = interaction.user.id in sessions
    # Use a fallback if the embed fails
    try:
        from embeds import menu_embed
        embed = menu_embed(connected)
    except:
        embed = discord.Embed(title="VoboAi", description="Menu loading...", color=discord.Color.blurple())

    # This is where we will re-implement the MenuView after stability is reached
    await interaction.response.send_message(embed=embed, ephemeral=True)

async def main():
    # 1. Start Health Server
    await start_health_server()
    
    # 2. Start Discord Bot
    async with bot:
        await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"[DeepHat] Fatal error in main loop: {e}")
