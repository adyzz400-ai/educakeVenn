import asyncio
import os
import time

import discord
from discord import app_commands, ui
from discord.ext import commands
from aiohttp import web

from config import (
    DISCORD_TOKEN,
    BOT_NAME,
    BOT_VERSION,
)

from embeds import (
    menu_embed,
    homework_embed,
    assignment_embed,
    progress_embed,
    completed_embed,
)

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


# ---------------------------------------------------------
# MEMORY SESSION STORE
# ---------------------------------------------------------

sessions = {}

# {
#   discord_user_id: {
#       "username": "...",
#       "password": "...",
#       "storage_state": {...},
#       "assignments": [...]
#   }
# }


# ---------------------------------------------------------
# DISCORD BOT
# ---------------------------------------------------------

intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
)


# ---------------------------------------------------------
# HEALTH SERVER FOR RENDER
# ---------------------------------------------------------

async def health(request):
    return web.Response(
        text="VoboAi Educake is online."
    )


async def start_health_server():
    app = web.Application()

    app.router.add_get(
        "/",
        health,
    )

    runner = web.AppRunner(app)

    await runner.setup()

    port = int(
        os.getenv("PORT", "10000")
    )

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        port,
    )

    await site.start()


# ---------------------------------------------------------
# LOGIN MODAL
# ---------------------------------------------------------

class EducakeLoginModal(ui.Modal):

    def __init__(self):
        super().__init__(
            title="Educake Login"
        )

        self.username = ui.TextInput(
            label="Educake Username",
            placeholder="Enter your Educake username",
            required=True,
            max_length=100,
        )

        self.password = ui.TextInput(
            label="Educake Password",
            placeholder="Enter your password",
            required=True,
            style=discord.TextStyle.short,
            max_length=200,
        )

        self.add_item(self.username)
        self.add_item(self.password)

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ):

        await interaction.response.defer(
            ephemeral=True
        )

        username = self.username.value
        password = self.password.value

        loop = asyncio.get_running_loop()

        # -------------------------------------------------
        # LOGIN STATUS
        # -------------------------------------------------

        status_message = await interaction.followup.send(
            "🔐 **Trying to log into your Educake account...**\n"
            "Please wait while I securely connect to Educake.",
            ephemeral=True,
            wait=True,
        )

        try:

            # -------------------------------------------------
            # LOGIN
            # -------------------------------------------------

            (
                pw,
                browser,
                context,
                page,
            ) = await loop.run_in_executor(
                None,
                lambda: login(
                    username,
                    password,
                ),
            )

            # -------------------------------------------------
            # LOGIN SUCCESS
            # -------------------------------------------------

            await status_message.edit(
                content=(
                    "✅ **Educake login successful!**\n"
                    "📚 **Loading your assigned homework...**"
                )
            )

            # -------------------------------------------------
            # SAVE SESSION
            # -------------------------------------------------

            storage_state = await loop.run_in_executor(
                None,
                lambda: save_storage_state(
                    context
                ),
            )

            # -------------------------------------------------
            # LOAD HOMEWORK
            # -------------------------------------------------

            assignments = await loop.run_in_executor(
                None,
                lambda: fetch_assignments(
                    page
                ),
            )

            # -------------------------------------------------
            # SAVE SESSION DATA
            # -------------------------------------------------

            sessions[
                interaction.user.id
            ] = {
                "username": username,
                "password": password,
                "storage_state": storage_state,
                "assignments": assignments,
            }

            browser.close()
            pw.stop()

            # -------------------------------------------------
            # FINAL STATUS
            # -------------------------------------------------

            await status_message.edit(
                content=(
                    "✅ **Educake account connected successfully!**\n"
                    f"📚 **{len(assignments)} homework assignment(s) loaded.**"
                )
            )

        # -----------------------------------------------------
        # CLOUDFLARE
        # -----------------------------------------------------

        except CloudflareChallenge:

            await status_message.edit(
                content=(
                    "⚠️ **Educake browser verification appeared.**\n"
                    "VoboAi stopped the login instead of bypassing "
                    "the verification challenge."
                )
            )

        # -----------------------------------------------------
        # LOGIN ERROR
        # -----------------------------------------------------

        except EducakeLoginError as e:

            await status_message.edit(
                content=(
                    "❌ **Educake login failed.**\n"
                    f"`{str(e)[:500]}`"
                )
            )

        # -----------------------------------------------------
        # GENERAL ERROR
        # -----------------------------------------------------

        except Exception as e:

            error_text = str(e)

            if (
                "Executable doesn't exist"
                in error_text
                or
                "playwright install"
                in error_text.lower()
            ):

                error_text = (
                    "The Playwright browser is not installed "
                    "on the Render service.\n\n"
                    "Check your existing Render build command "
                    "and redeploy with a clean build cache."
                )

            await status_message.edit(
                content=(
                    "❌ **Unexpected error**\n"
                    f"`{error_text[:500]}`"
                )
            )


# ---------------------------------------------------------
# HOME MENU
# ---------------------------------------------------------

class MenuView(ui.View):

    def __init__(self):
        super().__init__(
            timeout=300
        )

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

        await show_homework(
            interaction
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

        connected = (
            interaction.user.id
            in sessions
        )

        text = (
            "🟢 Educake account connected."
            if connected
            else
            "🔴 No Educake account connected."
        )

        await interaction.response.send_message(
            text,
            ephemeral=True,
        )


# ---------------------------------------------------------
# HOMEWORK DROPDOWN
# ---------------------------------------------------------

class HomeworkSelect(ui.Select):

    def __init__(self, assignments):

        self.assignments = assignments

        options = []

        for index, assignment in enumerate(
            assignments[:25]
        ):

            options.append(
                discord.SelectOption(
                    label=assignment.title[:100],

                    description=(
                        f"{assignment.subject} • "
                        f"Due: {assignment.due}"
                    )[:100],

                    value=str(index),

                    emoji="📝",
                )
            )

        super().__init__(
            placeholder="Select your Educake homework...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ):

        index = int(
            self.values[0]
        )

        assignment = self.assignments[index]

        await interaction.response.edit_message(
            embed=assignment_embed(
                assignment
            ),
            view=StartAssignmentView(
                assignment
            ),
        )


class HomeworkSelectView(ui.View):

    def __init__(self, assignments):

        super().__init__(
            timeout=300
        )

        self.add_item(
            HomeworkSelect(
                assignments
            )
        )

        self.add_item(
            BackButton()
        )


# ---------------------------------------------------------
# START ASSIGNMENT
# ---------------------------------------------------------

class StartAssignmentView(ui.View):

    def __init__(self, assignment):

        super().__init__(
            timeout=300
        )

        self.assignment = assignment

    @ui.button(
        label="Start",
        emoji="▶️",
        style=discord.ButtonStyle.success,
    )
    async def start(
        self,
        interaction: discord.Interaction,
        button: ui.Button,
    ):

        await interaction.response.defer()

        asyncio.create_task(
            process_assignment(
                interaction,
                self.assignment,
            )
        )

    @ui.button(
        label="Back",
        emoji="◀️",
        style=discord.ButtonStyle.secondary,
    )
    async def back(
        self,
        interaction: discord.Interaction,
        button: ui.Button,
    ):

        await show_homework(
            interaction
        )


# ---------------------------------------------------------
# BACK BUTTON
# ---------------------------------------------------------

class BackButton(
    ui.Button
):

    def __init__(self):

        super().__init__(
            label="Back",
            emoji="◀️",
            style=discord.ButtonStyle.secondary,
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ):

        await interaction.response.edit_message(
            embed=menu_embed(
                interaction.user.id in sessions
            ),
            view=MenuView(),
        )


# ---------------------------------------------------------
# HOMEWORK SCREEN
# ---------------------------------------------------------

async def show_homework(
    interaction: discord.Interaction,
):

    session = sessions.get(
        interaction.user.id
    )

    if not session:

        await interaction.response.send_message(
            "🔐 You need to connect your Educake account first.",
            ephemeral=True,
        )

        return

    await interaction.response.defer(
        ephemeral=True
    )

    loop = asyncio.get_running_loop()

    try:

        (
            pw,
            browser,
            context,
            page,
        ) = await loop.run_in_executor(
            None,
            lambda: login(
                session["username"],
                session["password"],
                session["storage_state"],
            ),
        )

        assignments = await loop.run_in_executor(
            None,
            lambda: fetch_assignments(
                page
            ),
        )

        new_state = await loop.run_in_executor(
            None,
            lambda: save_storage_state(
                context
            ),
        )

        session["storage_state"] = new_state
        session["assignments"] = assignments

        browser.close()
        pw.stop()

        await interaction.followup.send(
            embed=homework_embed(
                assignments
            ),
            view=HomeworkSelectView(
                assignments
            ),
            ephemeral=True,
        )

    except CloudflareChallenge:

        await interaction.followup.send(
            "⚠️ Educake presented a browser verification "
            "challenge. The saved session cannot bypass it.",
            ephemeral=True,
        )

    except Exception as e:

        await interaction.followup.send(
            f"❌ Could not load Educake homework:\n"
            f"`{str(e)[:500]}`",
            ephemeral=True,
        )


# ---------------------------------------------------------
# PROCESS REAL ASSIGNMENT
# ---------------------------------------------------------

async def process_assignment(
    interaction,
    assignment,
):

    session = sessions.get(
        interaction.user.id
    )

    if not session:

        await interaction.followup.send(
            "❌ Your Educake session has expired.",
            ephemeral=True,
        )

        return

    start_time = time.time()

    loop = asyncio.get_running_loop()

    try:

        (
            pw,
            browser,
            context,
            page,
        ) = await loop.run_in_executor(
            None,
            lambda: login(
                session["username"],
                session["password"],
                session["storage_state"],
            ),
        )

        await loop.run_in_executor(
            None,
            lambda: open_assignment(
                page,
                assignment,
            ),
        )

        questions = await loop.run_in_executor(
            None,
            lambda: extract_questions(
                page
            ),
        )

        if not questions:

            browser.close()
            pw.stop()

            await interaction.followup.send(
                "⚠️ I opened the real Educake assignment, "
                "but no readable questions were detected.",
                ephemeral=True,
            )

            return

        progress_message = await interaction.followup.send(
            embed=progress_embed(
                assignment,
                0,
                len(questions),
                "00:00",
            ),
            ephemeral=True,
            wait=True,
        )

        completed = 0

        for question in questions:

            await loop.run_in_executor(
                None,
                lambda q=question:
                    solve_question(q),
            )

            completed += 1

            elapsed_seconds = int(
                time.time() - start_time
            )

            minutes = elapsed_seconds // 60
            seconds = elapsed_seconds % 60

            elapsed = (
                f"{minutes:02d}:{seconds:02d}"
            )

            try:

                await progress_message.edit(
                    embed=progress_embed(
                        assignment,
                        completed,
                        len(questions),
                        elapsed,
                    )
                )

            except Exception:
                pass

        elapsed_seconds = int(
            time.time() - start_time
        )

        minutes = elapsed_seconds // 60
        seconds = elapsed_seconds % 60

        elapsed = (
            f"{minutes:02d}:{seconds:02d}"
        )

        await progress_message.edit(
            embed=completed_embed(
                assignment,
                completed,
                len(questions),
                elapsed,
            )
        )

        browser.close()
        pw.stop()

    except CloudflareChallenge:

        await interaction.followup.send(
            "⚠️ Educake/Cloudflare presented a verification "
            "challenge. VoboAi stopped instead of bypassing it.",
            ephemeral=True,
        )

    except Exception as e:

        await interaction.followup.send(
            f"❌ Assignment processing failed:\n"
            f"`{str(e)[:500]}`",
            ephemeral=True,
        )


# ---------------------------------------------------------
# /menu
# ---------------------------------------------------------

@bot.tree.command(
    name="menu",
    description="Open the VoboAi Educake menu.",
)
async def menu(
    interaction: discord.Interaction,
):

    connected = (
        interaction.user.id
        in sessions
    )

    await interaction.response.send_message(
        embed=menu_embed(
            connected
        ),
        view=MenuView(),
    )


# ---------------------------------------------------------
# READY
# ---------------------------------------------------------

@bot.event
async def on_ready():

    await bot.tree.sync()

    print(
        f"Logged in as {bot.user}"
    )

    print(
        f"{BOT_NAME} v{BOT_VERSION} "
        "Educake system online."
    )


# ---------------------------------------------------------
# START
# ---------------------------------------------------------

async def main():

    await start_health_server()

    await bot.start(
        DISCORD_TOKEN
    )


if __name__ == "__main__":

    asyncio.run(
        main()
    )
