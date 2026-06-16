import time
import discord
from discord import app_commands
from discord.ext import commands
from utils.embeds import error as err_embed
import config


# ── Help Category Data ────────────────────────────────────────────────────────

CATEGORIES = {
    "general": {
        "emoji": "🌐",
        "label": "General",
        "description": "Basic bot commands",
        "commands": [
            ("/ping",       "Check the bot's latency"),
            ("/info",       "Show info about the bot"),
            ("/uptime",     "How long the bot has been running"),
            ("/invite",     "Get the bot's invite link"),
            ("/help",       "Show this help menu"),
        ],
    },
    "utility": {
        "emoji": "🛠️",
        "label": "Utility",
        "description": "Server & user info commands",
        "commands": [
            ("/avatar",      "Get a user's avatar"),
            ("/userinfo",    "Show info about a member"),
            ("/serverinfo",  "Show info about this server"),
            ("/roleinfo",    "Show info about a role"),
            ("/channelinfo", "Show info about a channel"),
            ("/botperms",    "Check bot permissions in this channel"),
            ("/snowflake",   "Convert a Discord ID to a timestamp"),
        ],
    },
    "moderation": {
        "emoji": "🔨",
        "label": "Moderation",
        "description": "Server moderation tools",
        "commands": [
            ("/warn",          "Warn a member"),
            ("/warnings",      "View a member's warnings"),
            ("/clearwarnings", "Clear all warnings for a member"),
            ("/kick",          "Kick a member"),
            ("/ban",           "Ban a member"),
            ("/unban",         "Unban a user by ID"),
            ("/mute",          "Mute a member using the mute role"),
            ("/unmute",        "Unmute a member"),
            ("/timeout",       "Timeout a member"),
            ("/untimeout",     "Remove a timeout"),
            ("/purge",         "Bulk delete messages"),
            ("/modlogs",       "View moderation history"),
            ("/slowmode",      "Set slowmode for a channel"),
            ("/lock",          "Lock a channel"),
            ("/unlock",        "Unlock a channel"),
        ],
    },
    "leveling": {
        "emoji": "⭐",
        "label": "Leveling",
        "description": "XP and level system",
        "commands": [
            ("/rank",            "Check your or another member's rank"),
            ("/leaderboard",     "Show the XP leaderboard"),
            ("/setxp",           "Set a member's XP (admin)"),
            ("/levelrole",       "Set a role reward for a level (admin)"),
            ("/removelevelrole", "Remove a level role reward (admin)"),
        ],
    },
    "economy": {
        "emoji": "🪙",
        "label": "Economy",
        "description": "Coins, shop & rewards",
        "commands": [
            ("/balance",    "Check your balance"),
            ("/daily",      "Claim your daily coins"),
            ("/work",       "Work to earn coins"),
            ("/deposit",    "Deposit coins to bank"),
            ("/withdraw",   "Withdraw coins from bank"),
            ("/pay",        "Pay another member"),
            ("/shop",       "Browse the server shop"),
            ("/buy",        "Buy a shop item"),
            ("/inventory",  "View your inventory"),
            ("/richlist",   "Show the richest members"),
            ("/additem",    "Add a shop item (admin)"),
            ("/removeitem", "Remove a shop item (admin)"),
            ("/givemoney",  "Give coins to a member (admin)"),
            ("/takemoney",  "Take coins from a member (admin)"),
        ],
    },
    "tickets": {
        "emoji": "🎫",
        "label": "Tickets",
        "description": "Support ticket system",
        "commands": [
            ("/ticket panel",       "Send the ticket panel (admin)"),
            ("/ticket panel_topic", "Send a panel with topic modal (admin)"),
            ("/ticket close",       "Close the current ticket"),
            ("/ticket add",         "Add a member to a ticket"),
            ("/ticket remove",      "Remove a member from a ticket"),
        ],
    },
    "roles": {
        "emoji": "🎭",
        "label": "Roles",
        "description": "Role management & reaction roles",
        "commands": [
            ("/role panel",           "Send a role selection panel (admin)"),
            ("/role reaction_add",    "Add a reaction role (admin)"),
            ("/role reaction_remove", "Remove a reaction role (admin)"),
            ("/role reaction_list",   "List all reaction roles (admin)"),
            ("/role auto_add",        "Add an auto-role (admin)"),
            ("/role auto_remove",     "Remove an auto-role (admin)"),
            ("/role auto_list",       "List auto-roles (admin)"),
            ("/role give",            "Give a role to a member (admin)"),
            ("/role take",            "Take a role from a member (admin)"),
            ("/role all",             "Give a role to all members (admin)"),
        ],
    },
    "giveaways": {
        "emoji": "🎉",
        "label": "Giveaways",
        "description": "Giveaway system",
        "commands": [
            ("/giveaway start",  "Start a giveaway (admin)"),
            ("/giveaway end",    "End a giveaway early (admin)"),
            ("/giveaway reroll", "Reroll giveaway winners (admin)"),
            ("/giveaway list",   "List active giveaways"),
        ],
    },
    "automod": {
        "emoji": "🛡️",
        "label": "Auto-Mod",
        "description": "Automatic moderation",
        "commands": [
            ("/set automod true/false",    "Enable/disable auto-mod"),
            ("/set antispam true/false",   "Enable/disable anti-spam"),
            ("/set antilinks true/false",  "Enable/disable anti-links"),
            ("/set badwords true/false",   "Enable/disable bad word filter"),
            ("/set add_badword <word>",    "Add a word to the filter"),
            ("/set remove_badword <word>", "Remove a word from the filter"),
        ],
    },
    "settings": {
        "emoji": "⚙️",
        "label": "Settings",
        "description": "Server configuration",
        "commands": [
            ("/settings",               "View all settings (dashboard)"),
            ("/set prefix",             "Change the bot prefix"),
            ("/set welcome_channel",    "Set the welcome channel"),
            ("/set leave_channel",      "Set the leave channel"),
            ("/set log_channel",        "Set the event log channel"),
            ("/set mod_log",            "Set the mod log channel"),
            ("/set mute_role",          "Set the mute role"),
            ("/set leveling",           "Enable/disable leveling"),
            ("/set economy",            "Enable/disable economy"),
            ("/set tickets",            "Enable/disable tickets"),
        ],
    },
    "customcmds": {
        "emoji": "📝",
        "label": "Custom Commands",
        "description": "Per-server custom commands",
        "commands": [
            ("/cmd add",    "Add a custom command (admin)"),
            ("/cmd edit",   "Edit a custom command (admin)"),
            ("/cmd delete", "Delete a custom command (admin)"),
            ("/cmd list",   "List all custom commands"),
            ("/cmd info",   "View command details"),
        ],
    },
}


# ── Help Select Menu ──────────────────────────────────────────────────────────

class HelpSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=data["label"],
                value=key,
                emoji=data["emoji"],
                description=data["description"],
            )
            for key, data in CATEGORIES.items()
        ]
        super().__init__(placeholder="📖 Select a category...", options=options)

    async def callback(self, interaction: discord.Interaction):
        await self.view.show_category(interaction, self.values[0])


class HelpView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.add_item(HelpSelect())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This isn't your help menu.", ephemeral=True)
            return False
        return True

    async def show_category(self, interaction: discord.Interaction, key: str):
        data = CATEGORIES[key]
        embed = discord.Embed(
            title=f"{data['emoji']} {data['label']} Commands",
            description=data["description"],
            color=config.BOT_COLOR,
        )
        for name, desc in data["commands"]:
            embed.add_field(name=name, value=desc, inline=False)
        embed.set_footer(text=f"{config.BOT_NAME} v{config.BOT_VERSION} • {len(data['commands'])} commands")
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


# ── Cog ───────────────────────────────────────────────────────────────────────

class General(commands.Cog):
    """General-purpose commands available to everyone."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._start_time = time.time()

    # ── /help ─────────────────────────────────────────────────────────────────
    @app_commands.command(name="help", description="Browse all bot commands by category.")
    async def help(self, interaction: discord.Interaction):
        total = sum(len(v["commands"]) for v in CATEGORIES.values())
        embed = discord.Embed(
            title=f"📖 {config.BOT_NAME} Help",
            description=(
                f"**{total} commands** across **{len(CATEGORIES)} categories**.\n"
                f"Select a category from the dropdown below to browse commands.\n\n"
                f"**Prefix:** `{config.PREFIX}` • **Slash:** `/`"
            ),
            color=config.BOT_COLOR,
        )
        # Quick overview
        for key, data in CATEGORIES.items():
            embed.add_field(
                name=f"{data['emoji']} {data['label']}",
                value=f"`{len(data['commands'])}` commands",
                inline=True,
            )
        if self.bot.user and self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)
        embed.set_footer(text=f"v{config.BOT_VERSION} • Use the dropdown to explore")

        view = HelpView(interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # ── /ping ─────────────────────────────────────────────────────────────────
    @app_commands.command(name="ping", description="Check the bot's latency.")
    async def ping(self, interaction: discord.Interaction):
        latency_ms = round(self.bot.latency * 1000)
        color = (
            discord.Color.green()  if latency_ms < 100 else
            discord.Color.yellow() if latency_ms < 200 else
            discord.Color.red()
        )
        quality = "Excellent 🟢" if latency_ms < 100 else "Good 🟡" if latency_ms < 200 else "Poor 🔴"
        embed = discord.Embed(title="🏓 Pong!", color=color)
        embed.add_field(name="Gateway", value=f"`{latency_ms}ms`")
        embed.add_field(name="Quality", value=quality)
        await interaction.response.send_message(embed=embed)

    # ── /info ─────────────────────────────────────────────────────────────────
    @app_commands.command(name="info", description="Show info about the bot.")
    async def info(self, interaction: discord.Interaction):
        embed = discord.Embed(title=f"ℹ️ About {config.BOT_NAME}", color=config.BOT_COLOR)
        embed.add_field(name="Version",  value=f"`{config.BOT_VERSION}`")
        embed.add_field(name="Servers",  value=f"`{len(self.bot.guilds)}`")
        embed.add_field(name="Prefix",   value=f"`{config.PREFIX}`")
        embed.add_field(name="Library",  value=f"`discord.py {discord.__version__}`")
        embed.add_field(name="Commands", value=f"`{sum(len(v['commands']) for v in CATEGORIES.values())}`")
        embed.add_field(name="Latency",  value=f"`{round(self.bot.latency * 1000)}ms`")
        if self.bot.user and self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)
        await interaction.response.send_message(embed=embed)

    # ── /uptime ───────────────────────────────────────────────────────────────
    @app_commands.command(name="uptime", description="How long has the bot been running?")
    async def uptime(self, interaction: discord.Interaction):
        elapsed          = int(time.time() - self._start_time)
        days, remainder  = divmod(elapsed, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)

        parts = []
        if days:    parts.append(f"{days}d")
        if hours:   parts.append(f"{hours}h")
        if minutes: parts.append(f"{minutes}m")
        parts.append(f"{seconds}s")

        embed = discord.Embed(
            title="⏱️ Uptime",
            description=f"**{' '.join(parts)}**",
            color=config.BOT_COLOR,
        )
        await interaction.response.send_message(embed=embed)

    # ── /invite ───────────────────────────────────────────────────────────────
    @app_commands.command(name="invite", description="Get the bot's invite link.")
    async def invite(self, interaction: discord.Interaction):
        perms = discord.Permissions(
            kick_members=True, ban_members=True, manage_channels=True,
            manage_roles=True, manage_messages=True, read_messages=True,
            send_messages=True, embed_links=True, attach_files=True,
            read_message_history=True, add_reactions=True, moderate_members=True,
        )
        url = discord.utils.oauth_url(self.bot.user.id, permissions=perms)
        embed = discord.Embed(
            title=f"➕ Invite {config.BOT_NAME}",
            description=f"[Click here to invite me!]({url})",
            color=config.BOT_COLOR,
        )
        await interaction.response.send_message(embed=embed)

    # ── Error handler ─────────────────────────────────────────────────────────
    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        msg = f"`{error}`"
        if interaction.response.is_done():
            await interaction.followup.send(embed=err_embed("Error", msg), ephemeral=True)
        else:
            await interaction.response.send_message(embed=err_embed("Error", msg), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(General(bot))
