import asyncio
import os
import time
import traceback

import discord
from discord import app_commands, ui
from discord.ext import commands
from aiohttp import web

from config import (
    DISCORD_TOKEN,
    BOT_NAME,
    BOT_VERSION,
)

# Import embeds with error handling
try:
    from embeds import (
        menu_embed,
        homework_embed,
        assignment_embed,
        progress_embed,
        completed_embed,
    )
except Exception as e:
    print(f"[DeepHat] Embeds failed to load: {e}")

# LAZY IMPORT: This prevents the bot from crashing on boot if voboai is broken
try:
    from voboai.educake import (
        login,
        save_storage_state,
        fetch_assignments,
        open_assignment,
        extract_questions,
        CloudflareChallenge,
        EducakeLoginError,
        EducakeError,
    )
    from voboai.solver import solve_question

    EDUC_AVAILABLE = True
    print("[DeepHat] Educake module loaded successfully.")

except Exception as e:
    print("[DeepHat] CRITICAL: Educake module failed to load!")
    print(f"[DeepHat] Traceback: {traceback.format_exc()}")

    EDUC_AVAILABLE = False


sessions = {}

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


# =========================================================
# HEALTH SERVER
# =========================================================

async def health(request):
    return web.Response(text="VoboAi Educake is online.")


async def start_health_server():
    app = web.Application()
    app.router.add_get("/", health)

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.getenv("PORT", "10000"))

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        port,
    )

    await site.start()

    print(f"[DeepHat] Health server active on port {port}")


# =========================================================
# UI COMPONENTS
# =========================================================

class EducakeLoginModal(ui.Modal):

    def __init__(self):
        super().__init__(title="Educake Login")

        self.username = ui.TextInput(
            label="Educake Username",
            placeholder="Enter your Educake username",
            required=True,
            max_length=100,
        )

        self.password = ui.TextInput(
            label="Educake Password",
            placeholder="Enter your Educake password",
            required=True,
            style=discord.TextStyle.short,
            max_length=200,
        )

        self.add_item(self.username)
        self.add_item(self.password)

    async def on_submit(self, interaction: discord.Interaction):

        # Educake is only required when actually logging in.
        if not EDUC_AVAILABLE:
            return await interaction.response.send_message(
                "❌ **Educake system is currently unavailable.**\n"
                "Please check the bot logs.",
                ephemeral=True,
            )

        await interaction.response.defer(ephemeral=True)

        username = self.username.value
        password = self.password.value
        user_id = interaction.user.id

        status_message = await interaction.followup.send(
            "🔐 **Trying to log into your Educake account...**\n"
            "Please wait while I securely connect.",
            ephemeral=True,
        )

        loop = asyncio.get_running_loop()

        try:

            # Run blocking Playwright code in executor
            (pw, browser, context, page) = await loop.run_in_executor(
                None,
                lambda: login(username, password),
            )

            await status_message.edit(
                content=
                "✅ **Educake login successful!**\n"
                "📚 **Loading assignments...**"
            )

            # Save session state
            storage_state = await loop.run_in_executor(
                None,
                lambda: save_storage_state(context),
            )

            assignments = await loop.run_in_executor(
                None,
                lambda: fetch_assignments(page),
            )

            sessions[user_id] = {
                "username": username,
                "password": password,
                "storage_state": storage_state,
                "assignments": assignments,
            }

            browser.close()
            pw.stop()

            await status_message.edit(
                content=
                f"✅ **Account connected!**\n"
                f"📚 **{len(assignments)} assignment(s) found.**"
            )

        except CloudflareChallenge:

            await status_message.edit(
                content=
                "⚠️ **Verification required.**\n"
                "Cloudflare blocked the login."
            )

        except EducakeLoginError as e:

            await status_message.edit(
                content=
                f"❌ **Login failed.**\n"
                f"`{str(e)[:200]}`"
            )

        except Exception as e:

            print(
                f"[DeepHat] Login Error Traceback:\n"
                f"{traceback.format_exc()}"
            )

            await status_message.edit(
                content=
                f"❌ **Unexpected error**\n"
                f"`{str(e)[:200]}`"
            )


# =========================================================
# MENU VIEW
# =========================================================

class MenuView(ui.View):

    def __init__(self):
        super().__init__(timeout=300)

    @ui.button(
        label="Login",
        emoji="🔐",
        style=discord.ButtonStyle.primary,
    )
    async def login_button(
        self,
        interaction: discord.Interaction,
        button: ui.Button,
    ):

        await interaction.response.send_modal(
            EducakeLoginModal()
        )

    @ui.button(
        label="Homework",
        emoji="📚",
        style=discord.ButtonStyle.secondary,
    )
    async def homework_button(
        self,
        interaction: discord.Interaction,
        button: ui.Button,
    ):

        if not EDUC_AVAILABLE:
            return await interaction.response.send_message(
                "❌ **Educake module is unavailable.**\n"
                "Please check the bot logs.",
                ephemeral=True,
            )

        if interaction.user.id not in sessions:
            return await interaction.response.send_message(
                "🔐 **Please login first.**",
                ephemeral=True,
            )

        await interaction.response.defer(
            ephemeral=True
        )

        await interaction.followup.send(
            "📚 **Fetching your homework list...**",
            ephemeral=True,
        )

    @ui.button(
        label="Settings",
        emoji="⚙️",
        style=discord.ButtonStyle.secondary,
    )
    async def settings_button(
        self,
        interaction: discord.Interaction,
        button: ui.Button,
    ):

        connected = interaction.user.id in sessions

        text = (
            "🟢 **Connected**"
            if connected
            else
            "🔴 **Not connected**"
        )

        await interaction.response.send_message(
            text,
            ephemeral=True,
        )


# =========================================================
# BOT COMMANDS
# =========================================================

@bot.tree.command(
    name="menu",
    description="Open the VoboAi Educake menu.",
)
async def menu(interaction: discord.Interaction):

    # IMPORTANT:
    # /menu does NOT require the Educake module to load.
    # The Login/Homework buttons handle that check instead.

    connected = interaction.user.id in sessions

    try:

        embed = menu_embed(connected)

        await interaction.response.send_message(
            embed=embed,
            view=MenuView(),
            ephemeral=True,
        )

    except Exception as e:

        print(
            f"[DeepHat] Menu Error:\n"
            f"{traceback.format_exc()}"
        )

        await interaction.response.send_message(
            "❌ **Error loading menu.**",
            ephemeral=True,
        )


# =========================================================
# READY
# =========================================================

@bot.event
async def on_ready():

    try:

        await bot.tree.sync()

        print(f"Logged in as {bot.user}")
        print(
            f"{BOT_NAME} v{BOT_VERSION} system online."
        )

    except Exception as e:

        print(
            f"[DeepHat] Tree Sync Error: {e}"
        )


# =========================================================
# MAIN
# =========================================================

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

        print(
            f"[DeepHat] Fatal error in main loop: {e}"
        )

        print(
            traceback.format_exc()
        )
