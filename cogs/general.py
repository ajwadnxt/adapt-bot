import time
import discord
from discord import app_commands
from discord.ext import commands
import config


# ── Category metadata ─────────────────────────────────────────────────────────
# Maps cog names to (emoji, short description) for the help menu.
COG_META: dict[str, tuple[str, str]] = {
    "General":        ("🌐", "General-purpose commands"),
    "Utility":        ("🛠️", "Utility & info commands"),
    "Moderation":     ("🔨", "Server moderation tools"),
    "Settings":       ("⚙️", "Server configuration"),
    "Welcome":        ("👋", "Welcome & leave messages"),
    "Logging":        ("📝", "Event logging"),
    "Leveling":       ("⭐", "XP & leveling system"),
    "Economy":        ("🪙", "Currency & economy"),
    "Tickets":        ("🎫", "Ticket support system"),
    "AutoMod":        ("🛡️", "Auto-moderation"),
    "Roles":          ("🎭", "Role management"),
    "CustomCommands": ("📝", "Custom commands"),
    "Developer":      ("👨‍💻", "Developer-only tools"),
    "Games":          ("🎮", "Fun & interactive games"),
}


def _get_cog_emoji(cog_name: str) -> str:
    return COG_META.get(cog_name, ("📦",))[0]


def _get_cog_desc(cog_name: str) -> str:
    return COG_META.get(cog_name, (None, "Miscellaneous commands"))[1]


def _collect_commands(bot: commands.Bot) -> dict[str, list[app_commands.Command | app_commands.Group]]:
    """Group all registered app commands by their cog name."""
    categories: dict[str, list] = {}

    for cmd in bot.tree.get_commands():
        # Determine cog name from the binding (cog instance)
        if hasattr(cmd, "binding") and cmd.binding is not None:
            cog_name = type(cmd.binding).__name__
        else:
            cog_name = "Uncategorized"

        categories.setdefault(cog_name, []).append(cmd)

    # Sort commands inside each category alphabetically
    for cat in categories:
        categories[cat].sort(key=lambda c: c.name)

    return categories


def _build_home_embed(bot: commands.Bot, categories: dict) -> discord.Embed:
    """Build the main overview embed showing all categories."""
    total_cmds = sum(
        (1 + len(c.commands) if isinstance(c, app_commands.Group) else 1)
        for cmds in categories.values()
        for c in cmds
    )
    latency_ms = round(bot.latency * 1000)
    guilds_count = len(bot.guilds)

    desc_lines = [
        f"👋 **Greetings!** Welcome to the **{config.BOT_NAME}** control center.",
        "I am a highly optimized, feature-rich bot designed to enhance your server experience.",
        "",
        "📊 **System Metrics**",
        "```ansi",
        f"\u001b[2;36m┌──\u001b[0m ⚡ \u001b[1;37mGateway Latency:\u001b[0m \u001b[1;32m{latency_ms}ms\u001b[0m",
        f"\u001b[2;36m├──\u001b[0m 🌐 \u001b[1;37mServer Count:   \u001b[0m \u001b[1;35m{guilds_count}\u001b[0m",
        f"\u001b[2;36m├──\u001b[0m 📁 \u001b[1;37mActive Modules: \u001b[0m \u001b[1;33m{len(categories)}\u001b[0m",
        f"\u001b[2;36m└──\u001b[0m ⚙️ \u001b[1;37mTotal Commands: \u001b[0m \u001b[1;34m{total_cmds}\u001b[0m",
        "```",
        "✨ **Browse Categories**",
        "Select a category from the dropdown menu below to view specific command details.",
        ""
    ]

    for cog_name, cmds in sorted(categories.items()):
        emoji = _get_cog_emoji(cog_name)
        count = sum(
            (1 + len(c.commands) if isinstance(c, app_commands.Group) else 1)
            for c in cmds
        )
        desc_lines.append(f"{emoji} **{cog_name}**")
        desc_lines.append(f"┕ `{count}` command{'s' if count != 1 else ''} • *{_get_cog_desc(cog_name)}*")
        desc_lines.append("")

    embed = discord.Embed(
        title=f"🔮 {config.BOT_NAME} Systems Command",
        description="\n".join(desc_lines),
        color=config.BOT_COLOR,
    )

    embed.set_footer(
        text=f"Adapt Hub v{config.BOT_VERSION} • Developed by ajwadnxt",
        icon_url=bot.user.avatar.url if bot.user and bot.user.avatar else None
    )
    return embed


def _build_category_embed(cog_name: str, cmds: list, bot: commands.Bot) -> discord.Embed:
    """Build an embed listing every command in a given category."""
    emoji = _get_cog_emoji(cog_name)
    
    desc_lines = [
        f"### {emoji} {cog_name} Module",
        f"*{_get_cog_desc(cog_name)}*",
        "",
        "**Available Commands:**",
        ""
    ]
    
    if not cmds:
        desc_lines.append("*No commands found in this module.*")
    else:
        for cmd in cmds:
            if isinstance(cmd, app_commands.Group):
                desc_lines.append(f"🔹 **`/{cmd.name}`** *(Command Group)*")
                sub_lines = []
                for sub in sorted(cmd.commands, key=lambda s: s.name):
                    sub_lines.append(f"  ┕ `/{cmd.name} {sub.name}` • *{sub.description or 'No description'}*")
                if sub_lines:
                    desc_lines.extend(sub_lines)
                else:
                    desc_lines.append("  ┕ *No subcommands registered*")
            else:
                desc_lines.append(f"✦ **`/{cmd.name}`**")
                desc_lines.append(f"  ┕ *{cmd.description or 'No description available'}*")
            desc_lines.append("")  # Spacer between commands

    embed = discord.Embed(
        description="\n".join(desc_lines),
        color=config.BOT_COLOR,
    )

    if bot.user and bot.user.avatar:
        embed.set_thumbnail(url=bot.user.avatar.url)

    embed.set_footer(
        text=f"Adapt Hub v{config.BOT_VERSION} • Select 'Home' in menu to go back",
        icon_url=bot.user.avatar.url if bot.user and bot.user.avatar else None
    )
    return embed


# ── Help Select Menu ──────────────────────────────────────────────────────────

class HelpSelect(discord.ui.Select):
    def __init__(self, categories: dict[str, list], bot: commands.Bot):
        self.categories = categories
        self.bot_ref = bot

        options = [
            discord.SelectOption(
                label="🏠 Home",
                value="__home__",
                description="Overview of all categories",
                emoji="📖",
            )
        ]
        for cog_name in sorted(categories):
            emoji = _get_cog_emoji(cog_name)
            count = sum(
                (1 + len(c.commands) if isinstance(c, app_commands.Group) else 1)
                for c in categories[cog_name]
            )
            options.append(
                discord.SelectOption(
                    label=cog_name,
                    value=cog_name,
                    description=f"{count} command{'s' if count != 1 else ''} — {_get_cog_desc(cog_name)}",
                    emoji=emoji,
                )
            )

        super().__init__(
            placeholder="Select a category…",
            options=options[:25],  # Discord limit
        )

    async def callback(self, interaction: discord.Interaction):
        value = self.values[0]
        if value == "__home__":
            embed = _build_home_embed(self.bot_ref, self.categories)
        else:
            embed = _build_category_embed(value, self.categories[value], self.bot_ref)
        await interaction.response.edit_message(embed=embed)


class HelpView(discord.ui.View):
    def __init__(self, categories: dict[str, list], bot: commands.Bot, author_id: int):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.add_item(HelpSelect(categories, bot))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ This help menu isn't yours! Use `/help` to open your own.",
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


# ── Cog ───────────────────────────────────────────────────────────────────────

class General(commands.Cog):
    """General-purpose commands available to everyone."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._start_time = time.time()

    @app_commands.command(name="ping", description="Check the bot's latency.")
    async def ping(self, interaction: discord.Interaction):
        latency_ms = round(self.bot.latency * 1000)
        color = (
            discord.Color.green() if latency_ms < 100
            else discord.Color.yellow() if latency_ms < 200
            else discord.Color.red()
        )
        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"Gateway latency: **{latency_ms}ms**",
            color=color,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="help", description="Show all available commands.")
    async def help(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        categories = _collect_commands(self.bot)
        embed = _build_home_embed(self.bot, categories)
        view = HelpView(categories, self.bot, interaction.user.id)
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="info", description="Show info about the bot.")
    async def info(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=f"ℹ️ About {config.BOT_NAME}",
            color=config.BOT_COLOR,
        )
        embed.add_field(name="Version", value=config.BOT_VERSION, inline=True)
        embed.add_field(name="Servers", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name="Prefix", value=f"`{config.PREFIX}`", inline=True)
        embed.add_field(
            name="Library",
            value=f"discord.py {discord.__version__}",
            inline=True,
        )
        if self.bot.user and self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="uptime", description="How long has the bot been running?")
    async def uptime(self, interaction: discord.Interaction):
        elapsed = int(time.time() - self._start_time)
        hours, remainder = divmod(elapsed, 3600)
        minutes, seconds = divmod(remainder, 60)
        embed = discord.Embed(
            title="⏱️ Uptime",
            description=f"**{hours}h {minutes}m {seconds}s**",
            color=config.BOT_COLOR,
        )
        await interaction.response.send_message(embed=embed)

    # ── /botprofile (owner-only) ──────────────────────────────────────────
    botprofile = app_commands.Group(
        name="botprofile",
        description="Change the bot's profile (owner only).",
    )

    @botprofile.command(name="avatar", description="Change the bot's avatar.")
    @app_commands.describe(image="Upload an image to use as the new avatar")
    async def bp_avatar(self, interaction: discord.Interaction, image: discord.Attachment):
        if not await self.bot.is_owner(interaction.user):
            return await interaction.response.send_message("❌ Only the bot owner can use this.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        if not image.content_type or not image.content_type.startswith("image/"):
            return await interaction.followup.send(
                embed=discord.Embed(title="❌ Invalid File", description="Please upload a valid image (PNG, JPG, GIF).", color=discord.Color.red())
            )

        try:
            avatar_bytes = await image.read()
            await self.bot.user.edit(avatar=avatar_bytes)
            embed = discord.Embed(
                title="✅ Avatar Updated",
                description="The bot's avatar has been changed!",
                color=discord.Color.green(),
            )
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
            await interaction.followup.send(embed=embed)
        except discord.HTTPException as e:
            await interaction.followup.send(
                embed=discord.Embed(title="❌ Failed", description=f"Could not update avatar: `{e}`", color=discord.Color.red())
            )

    @botprofile.command(name="username", description="Change the bot's username.")
    @app_commands.describe(name="The new username for the bot")
    async def bp_username(self, interaction: discord.Interaction, name: str):
        if not await self.bot.is_owner(interaction.user):
            return await interaction.response.send_message("❌ Only the bot owner can use this.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        if len(name) < 2 or len(name) > 32:
            return await interaction.followup.send(
                embed=discord.Embed(title="❌ Invalid Name", description="Username must be 2–32 characters.", color=discord.Color.red())
            )

        try:
            await self.bot.user.edit(username=name)
            embed = discord.Embed(
                title="✅ Username Updated",
                description=f"Bot username changed to **{name}**",
                color=discord.Color.green(),
            )
            await interaction.followup.send(embed=embed)
        except discord.HTTPException as e:
            await interaction.followup.send(
                embed=discord.Embed(title="❌ Failed", description=f"Could not update username: `{e}`\n\n> **Note:** Discord limits username changes to 2 per hour.", color=discord.Color.red())
            )

    @botprofile.command(name="status", description="Change the bot's status message.")
    @app_commands.describe(
        text="The status text to display",
        activity_type="The type of activity",
    )
    @app_commands.choices(activity_type=[
        app_commands.Choice(name="Playing", value=0),
        app_commands.Choice(name="Streaming", value=1),
        app_commands.Choice(name="Listening", value=2),
        app_commands.Choice(name="Watching", value=3),
        app_commands.Choice(name="Competing", value=5),
    ])
    async def bp_status(
        self,
        interaction: discord.Interaction,
        text: str,
        activity_type: app_commands.Choice[int] = None,
    ):
        if not await self.bot.is_owner(interaction.user):
            return await interaction.response.send_message("❌ Only the bot owner can use this.", ephemeral=True)

        atype = discord.ActivityType(activity_type.value if activity_type else 3)
        activity = discord.Activity(type=atype, name=text)
        await self.bot.change_presence(activity=activity)

        type_name = activity_type.name if activity_type else "Watching"
        embed = discord.Embed(
            title="✅ Status Updated",
            description=f"**{type_name}** {text}",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @botprofile.command(name="banner", description="Change the bot's banner (requires Nitro).")
    @app_commands.describe(image="Upload an image to use as the new banner")
    async def bp_banner(self, interaction: discord.Interaction, image: discord.Attachment):
        if not await self.bot.is_owner(interaction.user):
            return await interaction.response.send_message("❌ Only the bot owner can use this.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        if not image.content_type or not image.content_type.startswith("image/"):
            return await interaction.followup.send(
                embed=discord.Embed(title="❌ Invalid File", description="Please upload a valid image (PNG, JPG).", color=discord.Color.red())
            )

        try:
            banner_bytes = await image.read()
            await self.bot.user.edit(banner=banner_bytes)
            embed = discord.Embed(
                title="✅ Banner Updated",
                description="The bot's banner has been changed!",
                color=discord.Color.green(),
            )
            await interaction.followup.send(embed=embed)
        except discord.HTTPException as e:
            await interaction.followup.send(
                embed=discord.Embed(title="❌ Failed", description=f"Could not update banner: `{e}`", color=discord.Color.red())
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(General(bot))
