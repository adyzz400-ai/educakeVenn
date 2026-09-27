import asyncio
import os
import time
import discord
from discord import app_commands, ui
from discord.ext import commands
from aiohttp import web

from config import DISCORD_TOKEN, BOT_NAME, BOT_VERSION
from embeds import menu_embed, homework_embed, assignment_embed, progress_embed, completed_embed

# Lazy Import to prevent boot crash
try:
    from voboai.educake import (
        login, save_storage_state, fetch_assignments, open_assignment, 
        extract_questions, CloudflareChallenge, EducakeLoginError
    )
    from voboai.solver import solve_question
    EDUC_AVAILABLE = True
except Exception as e:
    print(f"[DeepHat] Module Error: {e}")
    EDUC_AVAILABLE = False

sessions = {}
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# --- HEALTH SERVER ---
async def health(request): return web.Response(text="VoboAi Online")
async def start_health_server():
    app = web.Application()
    app.router.add_get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

# --- UI COMPONENTS ---

class EducakeLoginModal(ui.Modal):
    def __init__(self):
        super().__init__(title="Educake Login")
        self.username = ui.TextInput(label="Username", required=True)
        self.password = ui.TextInput(label="Password", style=discord.TextStyle.short, required=True)
        self.add_item(self.username)
        self.add_item(self.password)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        status_msg = await interaction.followup.send("🔐 **Connecting to Educake...**", ephemeral=True)
        
        loop = asyncio.get_running_loop()
        try:
            # Logic execution
            pw, browser, context, page = await loop.run_in_executor(None, lambda: login(self.username.value, self.password.value))
            
            # Store session
            storage_state = await loop.run_in_executor(None, lambda: save_storage_state(context))
            assignments = await loop.run_in_executor(None, lambda: fetch_assignments(page))

            sessions[interaction.user.id] = {
                "username": self.username.value,
                "password": self.password.value,
                "storage_state": storage_state,
                "assignments": assignments
            }

            await status_msg.edit(content="✅ **Connected!** Loading assignments...")
            # Trigger the menu update here
        except Exception as e:
            await status_msg.edit(content=f"❌ **Error:** `{str(e)[:100]}`")

class MenuView(ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @ui.button(label="Login", emoji="🔐", style=discord.ButtonStyle.primary)
    async def login_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(EducakeLoginModal())

    @ui.button(label="Homework", emoji="📚", style=discord.ButtonStyle.secondary)
    async def homework_btn(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id not in sessions:
            return await interaction.response.send_message("Please login first.", ephemeral=True)
        # Show homework selection logic here
        await interaction.response.send_message("Fetching assignments...", ephemeral=True)

# --- MAIN COMMANDS ---

@bot.tree.command(name="menu", description="Open the VoboAi menu.")
async def menu(interaction: discord.Interaction):
    if not EDUC_AVAILABLE:
        return await interaction.response.send_message("System error: Module not loaded.", ephemeral=True)
    
    connected = interaction.user.id in sessions
    await interaction.response.send_message(embed=menu_embed(connected), view=MenuView(), ephemeral=True)

async def main():
    await start_health_server()
    async with bot:
        await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
