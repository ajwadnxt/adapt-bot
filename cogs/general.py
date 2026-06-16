import time
import discord
from discord import app_commands
from discord.ext import commands
from utils.embeds import error as err_embed
import config


class General(commands.Cog):
    """General-purpose commands available to everyone."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._start_time = time.time()

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
        embed.add_field(name="Gateway",  value=f"`{latency_ms}ms`")
        embed.add_field(name="Quality",  value=quality)
        await interaction.response.send_message(embed=embed)

    # ── /info ─────────────────────────────────────────────────────────────────
    @app_commands.command(name="info", description="Show info about the bot.")
    async def info(self, interaction: discord.Interaction):
        embed = discord.Embed(title=f"ℹ️ About {config.BOT_NAME}", color=config.BOT_COLOR)
        embed.add_field(name="Version",    value=f"`{config.BOT_VERSION}`")
        embed.add_field(name="Servers",    value=f"`{len(self.bot.guilds)}`")
        embed.add_field(name="Prefix",     value=f"`{config.PREFIX}`")
        embed.add_field(name="Library",    value=f"`discord.py {discord.__version__}`")
        embed.add_field(name="Commands",   value=f"`{len(self.bot.tree.get_commands())}`")
        embed.add_field(name="Latency",    value=f"`{round(self.bot.latency * 1000)}ms`")
        if self.bot.user and self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)
        await interaction.response.send_message(embed=embed)

    # ── /uptime ───────────────────────────────────────────────────────────────
    @app_commands.command(name="uptime", description="How long has the bot been running?")
    async def uptime(self, interaction: discord.Interaction):
        elapsed  = int(time.time() - self._start_time)
        days,    remainder  = divmod(elapsed, 86400)
        hours,   remainder  = divmod(remainder, 3600)
        minutes, seconds    = divmod(remainder, 60)

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
        embed.set_footer(text=f"Started {discord.utils.format_dt(discord.utils.utcnow().__class__.fromtimestamp(self._start_time), 'R')}")
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
