import sys
import os
import subprocess
import discord
from discord import app_commands
from discord.ext import commands
from utils.checks import is_owner
from utils.embeds import success, error, info
import logging

log = logging.getLogger("bot")


class Developer(commands.Cog):
    """Developer and bot owner administrative utilities."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── Restart Command ────────────────────────────────────────────────────────
    @app_commands.command(name="restart", description="Restart the bot process.")
    @is_owner()
    async def restart(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=success(
                "Restarting", "The bot is restarting... Please wait a few seconds."
            ),
            ephemeral=True,
        )
        log.info("🔄 Bot restart initiated by owner.")
        # Spawns a new bot process
        subprocess.Popen([sys.executable] + sys.argv)
        # Exits the current process
        os._exit(0)

    # ── Reload Command ─────────────────────────────────────────────────────────
    @app_commands.command(name="reload", description="Reload a bot cog extension.")
    @app_commands.describe(
        cog_name="The name of the cog to reload (e.g. general, customcmds)"
    )
    @is_owner()
    async def reload(self, interaction: discord.Interaction, cog_name: str):
        full_cog_name = cog_name.strip()
        if not full_cog_name.startswith("cogs."):
            full_cog_name = f"cogs.{full_cog_name}"

        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.reload_extension(full_cog_name)
            log.info(f"🔄 Reloaded extension: {full_cog_name}")
            await interaction.followup.send(
                embed=success("Extension Reloaded", f"Successfully reloaded `{full_cog_name}`.")
            )
        except Exception as e:
            log.error(f"❌ Failed to reload extension {full_cog_name}: {e}")
            await interaction.followup.send(
                embed=error(
                    "Reload Failed", f"Failed to reload `{full_cog_name}`:\n```py\n{e}\n```"
                )
            )

    # ── Shutdown Command ───────────────────────────────────────────────────────
    @app_commands.command(name="shutdown", description="Safely shut down the bot.")
    @is_owner()
    async def shutdown(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=success("Shutting Down", "The bot is shutting down safely."),
            ephemeral=True,
        )
        log.info("🔌 Bot shutdown initiated by owner.")
        await self.bot.close()


async def setup(bot: commands.Bot):
    await bot.add_cog(Developer(bot))
