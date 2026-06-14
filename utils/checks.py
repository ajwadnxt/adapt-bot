import discord
from discord import app_commands
from discord.ext import commands
import config


def is_mod():
    """Member has kick_members permission."""
    return app_commands.checks.has_permissions(kick_members=True)

def is_admin():
    """Member has administrator permission."""
    return app_commands.checks.has_permissions(administrator=True)

def is_owner():
    """Only the bot owner can use this."""
    async def predicate(interaction: discord.Interaction) -> bool:
        return await interaction.client.is_owner(interaction.user)
    return app_commands.check(predicate)

def bot_has_permissions(**perms):
    """Check that the bot itself has the required permissions."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            raise app_commands.NoPrivateMessage()
        bot_member = interaction.guild.me
        missing = [p for p, v in perms.items() if getattr(bot_member.guild_permissions, p, False) != v]
        if missing:
            raise app_commands.BotMissingPermissions(missing)
        return True
    return app_commands.check(predicate)
