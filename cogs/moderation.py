import discord
from discord import app_commands
from discord.ext import commands
import config


def is_mod():
    """Decorator: only members with Manage Members permission can run this."""
    return app_commands.checks.has_permissions(manage_members=True)


class Moderation(commands.Cog):
    """Server moderation commands (requires appropriate permissions)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot


    @app_commands.command(name="kick", description="Kick a member from the server.")
    @app_commands.describe(member="The member to kick", reason="Reason for the kick")
    @is_mod()
    async def kick(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str = "No reason provided",
    ):
        if member.top_role >= interaction.user.top_role:   # type: ignore[union-attr]
            await interaction.response.send_message(
                "❌ You can't kick someone with an equal or higher role.", ephemeral=True
            )
            return
        await member.kick(reason=reason)
        embed = discord.Embed(
            title="👢 Member Kicked",
            color=discord.Color.orange(),
        )
        embed.add_field(name="Member", value=member.mention)
        embed.add_field(name="Reason", value=reason)
        embed.add_field(name="Moderator", value=interaction.user.mention)
        await interaction.response.send_message(embed=embed)



@app_commands.command(name="ban", description="Ban a member from the server.")
    @app_commands.describe(member="The member to ban", reason="Reason for the ban")
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str = "No reason provided",
    ):
        if member.top_role >= interaction.user.top_role:   # type: ignore[union-attr]
            await interaction.response.send_message(
                "❌ You can't ban someone with an equal or higher role.", ephemeral=True
            )
            return
        await member.ban(reason=reason, delete_message_days=0)
        embed = discord.Embed(title="🔨 Member Banned", color=discord.Color.red())
        embed.add_field(name="Member", value=str(member))
        embed.add_field(name="Reason", value=reason)
        embed.add_field(name="Moderator", value=interaction.user.mention)
        await interaction.response.send_message(embed=embed)



    @app_commands.command(name="timeout", description="Timeout a member (in minutes).")
    @app_commands.describe(
        member="The member to time out",
        minutes="Duration in minutes (max 40320 = 28 days)",
        reason="Reason for the timeout",
    )
    @is_mod()
    async def timeout(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        minutes: app_commands.Range[int, 1, 40320],
        reason: str = "No reason provided",
    ):
        import datetime
        duration = datetime.timedelta(minutes=minutes)
        await member.timeout(duration, reason=reason)
        embed = discord.Embed(title="🔇 Member Timed Out", color=discord.Color.gold())
        embed.add_field(name="Member", value=member.mention)
        embed.add_field(name="Duration", value=f"{minutes} minute(s)")
        embed.add_field(name="Reason", value=reason)
        await interaction.response.send_message(embed=embed)


    @app_commands.command(name="purge", description="Bulk-delete messages in this channel.")
    @app_commands.describe(amount="Number of messages to delete (1–100)")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def purge(
        self,
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, 100],
    ):
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)   # type: ignore[union-attr]
        await interaction.followup.send(
            f"🗑️ Deleted **{len(deleted)}** message(s).", ephemeral=True
        )


    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "❌ You don't have permission to use this command.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ An error occurred: `{error}`", ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
