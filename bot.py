from __future__ import annotations

import os
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import discord
from discord.ext import commands

import embeds
from config import (
    BOT_NAME,
    BOT_TAGLINE,
    BOT_VERSION,
    DISCORD_TOKEN,
    MAX_CONCURRENT_JOBS,
)
from voboai.educake import (
    login_and_get_assignments,
    open_assignment,
    extract_visible_questions,
)
from voboai.solver import solve_question


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header(
            "Content-Type",
            "text/plain; charset=utf-8",
        )
        self.end_headers()
        self.wfile.write(b"VoboAi is running")

    def log_message(self, *_):
        pass


def health_server():
    port = int(os.getenv("PORT", "10000"))

    ThreadingHTTPServer(
        ("0.0.0.0", port),
        HealthHandler,
    ).serve_forever()


class Session:
    def __init__(
        self,
        username: str,
        password: str,
        assignments: list[dict],
    ):
        self.username = username
        self.password = password
        self.assignments = assignments


sessions: dict[int, Session] = {}


class JobQueue:
    def __init__(self, max_workers: int):
        self.max_workers = max_workers

        self.executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="educake",
        )

        self.pending = deque()
        self.running = 0
        self.lock = threading.Lock()

    def add(self, job):
        with self.lock:
            self.pending.append(job)

            position = len(self.pending)

            self._dispatch_locked()

            if job["started"]:
                return 0

            return position

    def cancel_user(self, user_id: int) -> bool:
        with self.lock:
            for job in list(self.pending):
                if job["user_id"] == user_id:
                    self.pending.remove(job)
                    return True

        return False

    def snapshot(self, user_id: int):
        with self.lock:
            for i, job in enumerate(self.pending, 1):
                if job["user_id"] == user_id:
                    return (
                        i,
                        self.running,
                        len(self.pending),
                    )

        return None

    def _dispatch_locked(self):
        while (
            self.running < self.max_workers
            and self.pending
        ):
            job = self.pending.popleft()

            self.running += 1
            job["started"] = True

            self.executor.submit(
                self._run,
                job,
            )

    def _run(self, job):
        try:
            job["run"]()
        finally:
            with self.lock:
                self.running -= 1
                self._dispatch_locked()


queue = JobQueue(MAX_CONCURRENT_JOBS)


def fmt_time(seconds):
    seconds = int(seconds)

    minutes, seconds = divmod(
        seconds,
        60,
    )

    hours, minutes = divmod(
        minutes,
        60,
    )

    if hours:
        return f"{hours}h {minutes}m {seconds}s"

    return f"{minutes}m {seconds}s"


class LoginModal(
    discord.ui.Modal,
    title="Educake Login",
):
    username = discord.ui.TextInput(
        label="Username or Email",
        placeholder="Enter your Educake username or email",
        max_length=150,
    )

    password = discord.ui.TextInput(
        label="Password",
        placeholder="Enter your Educake password",
        style=discord.TextStyle.short,
        max_length=150,
    )

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ):
        await interaction.response.defer(
            ephemeral=True
        )

        await interaction.followup.send(
            "🔐 Connecting to Educake...",
            ephemeral=True,
        )

        user_id = interaction.user.id

        def work():
            try:
                (
                    pw,
                    browser,
                    page,
                    assignments,
                ) = login_and_get_assignments(
                    self.username.value,
                    self.password.value,
                )

                browser.close()
                pw.stop()

                sessions[user_id] = Session(
                    self.username.value,
                    self.password.value,
                    assignments,
                )

                view = HomeworkView(
                    user_id,
                    assignments,
                )

                bot.loop.create_task(
                    interaction.user.send(
                        embed=embeds.homework_list(
                            assignments
                        ),
                        view=view,
                    )
                )

            except Exception as exc:
                bot.loop.create_task(
                    interaction.followup.send(
                        f"❌ Educake login failed: {exc}",
                        ephemeral=True,
                    )
                )

        threading.Thread(
            target=work,
            daemon=True,
        ).start()


class LoginView(discord.ui.View):
    def __init__(self):
        super().__init__(
            timeout=None
        )

    @discord.ui.button(
        label="🔐 Login",
        style=discord.ButtonStyle.primary,
    )
    async def login(
        self,
        interaction: discord.Interaction,
        _,
    ):
        await interaction.response.send_modal(
            LoginModal()
        )


class HomeView(discord.ui.View):
    def __init__(self):
        super().__init__(
            timeout=None
        )

    @discord.ui.button(
        label="🔐 Login",
        style=discord.ButtonStyle.primary,
    )
    async def login(
        self,
        interaction: discord.Interaction,
        _,
    ):
        await interaction.response.send_modal(
            LoginModal()
        )

    @discord.ui.button(
        label="📚 Homework",
        style=discord.ButtonStyle.secondary,
    )
    async def homework(
        self,
        interaction: discord.Interaction,
        _,
    ):
        session = sessions.get(
            interaction.user.id
        )

        if not session:
            await interaction.response.send_message(
                "🔐 Please login first.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=embeds.homework_list(
                session.assignments
            ),
            view=HomeworkView(
                interaction.user.id,
                session.assignments,
            ),
            ephemeral=True,
        )

    @discord.ui.button(
        label="🕐 Queue",
        style=discord.ButtonStyle.secondary,
    )
    async def queue_status(
        self,
        interaction: discord.Interaction,
        _,
    ):
        snap = queue.snapshot(
            interaction.user.id
        )

        if not snap:
            await interaction.response.send_message(
                "🟢 You are not currently waiting in the queue.",
                ephemeral=True,
            )
            return

        pos, running, total = snap

        await interaction.response.send_message(
            embed=embeds.queue_embed(
                pos,
                running,
                total,
            ),
            ephemeral=True,
        )


class HomeworkSelect(
    discord.ui.Select
):
    def __init__(
        self,
        user_id: int,
        assignments: list[dict],
    ):
        options = []

        for i, assignment in enumerate(
            assignments[:25]
        ):
            title = (
                assignment.get("title")
                or f"Assignment {i + 1}"
            )[:100]

            description = (
                f"{assignment.get('subject', 'Educake')}"
                f" • Due "
                f"{assignment.get('due', 'not shown')}"
            )[:100]

            options.append(
                discord.SelectOption(
                    label=title,
                    description=description,
                    value=str(i),
                )
            )

        if not options:
            options = [
                discord.SelectOption(
                    label="No active homework found",
                    value="none",
                )
            ]

        super().__init__(
            placeholder="Select your active homework...",
            options=options,
        )

        self.user_id = user_id
        self.assignments = assignments

    async def callback(
        self,
        interaction: discord.Interaction,
    ):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This homework menu belongs to another user.",
                ephemeral=True,
            )
            return

        if self.values[0] == "none":
            await interaction.response.send_message(
                "Educake did not expose any active assignment links on the dashboard.",
                ephemeral=True,
            )
            return

        assignment = self.assignments[
            int(self.values[0])
        ]

        await interaction.response.send_message(
            embed=embeds.assignment_details(
                assignment
            ),
            view=StartView(
                self.user_id,
                assignment,
            ),
            ephemeral=True,
        )


class HomeworkView(
    discord.ui.View
):
    def __init__(
        self,
        user_id: int,
        assignments: list[dict],
    ):
        super().__init__(
            timeout=900
        )

        self.add_item(
            HomeworkSelect(
                user_id,
                assignments,
            )
        )


class StartView(
    discord.ui.View
):
    def __init__(
        self,
        user_id: int,
        assignment: dict,
    ):
        super().__init__(
            timeout=600
        )

        self.user_id = user_id
        self.assignment = assignment

    @discord.ui.button(
        label="▶️ Start",
        style=discord.ButtonStyle.success,
    )
    async def start(
        self,
        interaction: discord.Interaction,
        _,
    ):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This control belongs to another user.",
                ephemeral=True,
            )
            return

        session = sessions.get(
            self.user_id
        )

        if not session:
            await interaction.response.send_message(
                "Your Educake session has expired. Login again.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(
            ephemeral=True
        )

        job = {
            "user_id": self.user_id,
            "user": interaction.user,
            "assignment": self.assignment,
            "session": session,
            "started": False,
            "run": lambda: process_job(
                interaction.user,
                self.assignment,
                session,
            ),
        }

        position = queue.add(job)

        if position == 0:
            await interaction.followup.send(
                "🚀 Your homework has started. "
                "Check your DMs for live progress.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                embed=embeds.queue_embed(
                    position,
                    queue.running,
                    len(queue.pending),
                ),
                ephemeral=True,
            )


class VoboAiBot(
    commands.Bot
):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=discord.Intents.default(),
        )

    async def setup_hook(self):
        await self.tree.sync()

        print(
            "Slash commands synced."
        )


bot = VoboAiBot()


@bot.event
async def on_ready():
    print(
        f"{BOT_NAME} online as {bot.user} | "
        f"v{BOT_VERSION} | {BOT_TAGLINE}"
    )


def process_job(
    user: discord.User,
    assignment: dict,
    session: Session,
):
    started = time.time()

    try:
        (
            pw,
            browser,
            page,
            _,
        ) = login_and_get_assignments(
            session.username,
            session.password,
        )

        try:
            open_assignment(
                page,
                assignment,
            )

            questions = extract_visible_questions(
                page
            )

            total = len(questions)

            if total == 0:
                bot.loop.create_task(
                    user.send(
                        "⚠️ Educake opened the assignment, "
                        "but no question blocks were exposed "
                        "in the page DOM. No fake questions "
                        "were created."
                    )
                )
                return

            bot.loop.create_task(
                user.send(
                    embed=embeds.progress(
                        assignment["title"],
                        0,
                        total,
                        "Reading assignment",
                        fmt_time(
                            time.time() - started
                        ),
                    )
                )
            )

            for i, question in enumerate(
                questions,
                1,
            ):
                status = "Analysing question"

                try:
                    answer = solve_question(
                        question["text"]
                    )
                except Exception as exc:
                    answer = (
                        f"Solver error: {exc}"
                    )

                bot.loop.create_task(
                    user.send(
                        embed=embeds.progress(
                            assignment["title"],
                            i,
                            total,
                            status,
                            fmt_time(
                                time.time()
                                - started
                            ),
                            answer,
                        )
                    )
                )

            bot.loop.create_task(
                user.send(
                    embed=embeds.complete(
                        assignment["title"],
                        total,
                        fmt_time(
                            time.time()
                            - started
                        ),
                    )
                )
            )

        finally:
            browser.close()
            pw.stop()

    except Exception as exc:
        bot.loop.create_task(
            user.send(
                f"❌ Homework processing failed: {exc}"
            )
        )


@bot.tree.command(
    name="homework",
    description="Open the Educake homework dashboard",
)
async def homework_command(
    interaction: discord.Interaction,
):
    session = sessions.get(
        interaction.user.id
    )

    count = (
        len(session.assignments)
        if session
        else 0
    )

    await interaction.response.send_message(
        embed=embeds.dashboard(
            count,
            len(queue.pending),
        ),
        view=HomeView(),
        ephemeral=True,
    )


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise SystemExit(
            "DISCORD_TOKEN is not configured."
        )

    threading.Thread(
        target=health_server,
        daemon=True,
    ).start()

    bot.run(
        DISCORD_TOKEN
    )
