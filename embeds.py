import discord


def menu_embed(account_connected=False):
    embed = discord.Embed(
        title="📚 VoboAi",
        description=(
            "**Educake Homework Assistant**\n\n"
            "Manage your Educake account, view assigned "
            "homework and start a real assignment."
        ),
        color=discord.Color.blurple(),
    )

    status = (
        "🟢 Connected"
        if account_connected
        else "🔴 Not connected"
    )

    embed.add_field(
        name="🔐 Account",
        value=status,
        inline=True,
    )

    embed.add_field(
        name="📚 Platform",
        value="Educake",
        inline=True,
    )

    embed.add_field(
        name="⚡ Status",
        value="Ready",
        inline=True,
    )

    embed.set_footer(
        text="VoboAi • Educake"
    )

    return embed


def homework_embed(assignments):
    embed = discord.Embed(
        title="📚 Your Educake Homework",
        description=(
            "Select an assignment from the dropdown below."
        ),
        color=discord.Color.blurple(),
    )

    if not assignments:
        embed.description = (
            "No assigned Educake homework was found."
        )

    for assignment in assignments[:10]:
        embed.add_field(
            name=f"📝 {assignment.title}",
            value=(
                f"**Subject:** {assignment.subject}\n"
                f"**Teacher:** {assignment.teacher}\n"
                f"**Due:** {assignment.due}"
            ),
            inline=False,
        )

    return embed


def assignment_embed(assignment):
    embed = discord.Embed(
        title=f"📝 {assignment.title}",
        color=discord.Color.blurple(),
    )

    embed.add_field(
        name="Subject",
        value=assignment.subject,
        inline=True,
    )

    embed.add_field(
        name="Teacher",
        value=assignment.teacher,
        inline=True,
    )

    embed.add_field(
        name="Due",
        value=assignment.due,
        inline=True,
    )

    embed.set_footer(
        text="VoboAi • Educake"
    )

    return embed


def progress_embed(
    assignment,
    completed,
    total,
    elapsed,
    accuracy="Calculating...",
):
    percentage = 0

    if total:
        percentage = int(
            completed / total * 100
        )

    embed = discord.Embed(
        title=f"⚡ {assignment.title}",
        description=(
            f"**Status:** Processing\n"
            f"**Progress:** {percentage}%"
        ),
        color=discord.Color.blurple(),
    )

    embed.add_field(
        name="Questions Completed",
        value=f"{completed}/{total}",
        inline=True,
    )

    embed.add_field(
        name="Time Spent",
        value=elapsed,
        inline=True,
    )

    embed.add_field(
        name="Accuracy",
        value=str(accuracy),
        inline=True,
    )

    embed.add_field(
        name="Progress",
        value=f"`{percentage}%`",
        inline=False,
    )

    return embed


def completed_embed(
    assignment,
    completed,
    total,
    elapsed,
):
    embed = discord.Embed(
        title="✅ Homework Processing Complete",
        description=(
            f"**{assignment.title}**\n\n"
            "The assignment has finished processing."
        ),
        color=discord.Color.green(),
    )

    embed.add_field(
        name="Questions",
        value=f"{completed}/{total}",
        inline=True,
    )

    embed.add_field(
        name="Time",
        value=elapsed,
        inline=True,
    )

    embed.set_footer(
        text="VoboAi • Educake"
    )

    return embed
