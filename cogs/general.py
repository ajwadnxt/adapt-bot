import time
import discord
from discord import app_commands
from discord.ext import commands
import config


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
        embed = discord.Embed(
            title=f"📖 {config.BOT_NAME} Help",
            description="Here's what I can do:",
            color=config.BOT_COLOR,
        )
        embed.add_field(
            name="🌐 General",
            value="`/ping` `/help` `/info` `/uptime`",
            inline=False,
        )
        embed.add_field(
            name="🔨 Moderation",
            value="`/kick` `/ban` `/timeout` `/purge`",
            inline=False,
        )
        embed.add_field(
            name="🛠️ Utility",
            value="`/avatar` `/serverinfo` `/userinfo`",
            inline=False,
        )
        embed.set_footer(text=f"v{config.BOT_VERSION}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

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


async def setup(bot: commands.Bot):
    await bot.add_cog(General(bot))
