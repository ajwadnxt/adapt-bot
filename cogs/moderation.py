import discord
from discord import app_commands
from discord.ext import commands
import config
from database import db


def is_mod():
    return app_commands.checks.has_permissions(manage_members=True)


class Moderation(commands.Cog):
    """Server moderation commands (requires appropriate permissions)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    #kick
    @app_commands.command(name="kick", description="Kick a member from the server.")
    @app_commands.describe(member="The member to kick", reason="Reason for the kick")
    @is_mod()
    async def kick(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str = "No reason provided",
    ):
        if member.top_role >= interaction.user.top_role:  # type: ignore[union-attr]
            await interaction.response.send_message(
                "❌ You can't kick someone with an equal or higher role.", ephemeral=True
            )
            return

        await member.kick(reason=reason)

        await db.add_mod_log(
            interaction.guild_id, member.id, interaction.user.id, "kick", reason
        )

        embed = discord.Embed(title="👢 Member Kicked", color=discord.Color.orange())
        embed.add_field(name="Member", value=member.mention)
        embed.add_field(name="Reason", value=reason)
        embed.add_field(name="Moderator", value=interaction.user.mention)
        await interaction.response.send_message(embed=embed)

    #ban
    @app_commands.command(name="ban", description="Ban a member from the server.")
    @app_commands.describe(member="The member to ban", reason="Reason for the ban")
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str = "No reason provided",
    ):
        if member.top_role >= interaction.user.top_role:  # type: ignore[union-attr]
            await interaction.response.send_message(
                "❌ You can't ban someone with an equal or higher role.", ephemeral=True
            )
            return

        await member.ban(reason=reason, delete_message_days=0)

        await db.add_mod_log(
            interaction.guild_id, member.id, interaction.user.id, "ban", reason
        )

        embed = discord.Embed(title="🔨 Member Banned", color=discord.Color.red())
        embed.add_field(name="Member", value=str(member))
        embed.add_field(name="Reason", value=reason)
        embed.add_field(name="Moderator", value=interaction.user.mention)
        await interaction.response.send_message(embed=embed)

    #timeout
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

        await db.add_mod_log(
            interaction.guild_id, member.id, interaction.user.id,
            "timeout", reason, duration=minutes
        )

        embed = discord.Embed(title="🔇 Member Timed Out", color=discord.Color.gold())
        embed.add_field(name="Member", value=member.mention)
        embed.add_field(name="Duration", value=f"{minutes} minute(s)")
        embed.add_field(name="Reason", value=reason)
        await interaction.response.send_message(embed=embed)

    #purge
    @app_commands.command(name="purge", description="Bulk-delete messages in this channel.")
    @app_commands.describe(amount="Number of messages to delete (1–100)")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def purge(
        self,
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, 100],
    ):
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)  # type: ignore[union-attr]
        await interaction.followup.send(
            f"🗑️ Deleted **{len(deleted)}** message(s).", ephemeral=True
        )

    #warn
    @app_commands.command(name="warn", description="Warn a member.")
    @app_commands.describe(member="The member to warn", reason="Reason for the warning")
    @is_mod()
    async def warn(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str,
    ):
        warn_id = await db.add_warning(
            interaction.guild_id, member.id, interaction.user.id, reason
        )
        warnings = await db.get_warnings(interaction.guild_id, member.id)

        embed = discord.Embed(title="⚠️ Member Warned", color=discord.Color.yellow())
        embed.add_field(name="Member", value=member.mention)
        embed.add_field(name="Reason", value=reason)
        embed.add_field(name="Moderator", value=interaction.user.mention)
        embed.set_footer(text=f"Warning #{warn_id} • {len(warnings)} total warning(s)")
        await interaction.response.send_message(embed=embed)

    #warnings
    @app_commands.command(name="warnings", description="View a member's warnings.")
    @app_commands.describe(member="The member to check")
    @is_mod()
    async def warnings(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ):
        rows = await db.get_warnings(interaction.guild_id, member.id)

        embed = discord.Embed(
            title=f"⚠️ Warnings for {member}",
            color=discord.Color.yellow(),
        )
        if not rows:
            embed.description = "This member has no warnings."
        else:
            for row in rows[:10]:  # Cap at 10 to avoid huge embeds
                embed.add_field(
                    name=f"#{row['id']} — {row['created_at'].strftime('%Y-%m-%d')}",
                    value=row["reason"],
                    inline=False,
                )
            if len(rows) > 10:
                embed.set_footer(text=f"Showing 10 of {len(rows)} warnings")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    #clearwarnings
    @app_commands.command(name="clearwarnings", description="Clear all warnings for a member.")
    @app_commands.describe(member="The member to clear warnings for")
    @app_commands.checks.has_permissions(administrator=True)
    async def clearwarnings(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ):
        count = await db.clear_warnings(interaction.guild_id, member.id)
        await interaction.response.send_message(
            f"🗑️ Cleared **{count}** warning(s) for {member.mention}.", ephemeral=True
        )

    #modlogs
    @app_commands.command(name="modlogs", description="View moderation history for a member.")
    @app_commands.describe(member="The member to check")
    @is_mod()
    async def modlogs(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ):
        rows = await db.get_mod_logs(interaction.guild_id, member.id)

        embed = discord.Embed(
            title=f"📋 Mod Logs for {member}",
            color=config.BOT_COLOR,
        )
        if not rows:
            embed.description = "No moderation history found."
        else:
            for row in rows[:10]:
                value = row["reason"] or "No reason"
                if row["duration"]:
                    value += f" *(duration: {row['duration']}m)*"
                embed.add_field(
                    name=f"{row['action'].upper()} — {row['created_at'].strftime('%Y-%m-%d')}",
                    value=value,
                    inline=False,
                )
            if len(rows) > 10:
                embed.set_footer(text=f"Showing 10 of {len(rows)} entries")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    #Errorhandler
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
