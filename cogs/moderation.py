import datetime
import discord
from discord import app_commands
from discord.ext import commands
from database import db
from utils.checks import is_mod, is_admin
from utils.embeds import mod_action, error, success, info
from utils.paginator import Paginator


async def send_mod_log(guild: discord.Guild, embed: discord.Embed):
    """Send an embed to the mod log channel if configured."""
    cfg = await db.get_guild(guild.id)
    if not cfg or not cfg["mod_log_channel_id"]:
        return
    channel = guild.get_channel(cfg["mod_log_channel_id"])
    if channel:
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            pass


async def try_dm(member: discord.Member, embed: discord.Embed):
    """Try to DM a member, silently fail if DMs are closed."""
    try:
        await member.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException):
        pass


class Moderation(commands.Cog):
    """Full moderation suite with logging."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── /warn ─────────────────────────────────────────────────────────────────
    @app_commands.command(name="warn", description="Warn a member.")
    @app_commands.describe(member="Member to warn", reason="Reason for the warning")
    @is_mod()
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        if member.bot:
            return await interaction.response.send_message(embed=error("Can't warn bots."), ephemeral=True)
        if member == interaction.user:
            return await interaction.response.send_message(embed=error("You can't warn yourself."), ephemeral=True)

        warn_id  = await db.add_warning(interaction.guild_id, member.id, interaction.user.id, reason)
        warnings = await db.get_warnings(interaction.guild_id, member.id)
        await db.add_mod_log(interaction.guild_id, member.id, interaction.user.id, "warn", reason)

        embed = mod_action("warn", member, interaction.user, reason)
        embed.set_footer(text=f"Warning #{warn_id} • {len(warnings)} total")
        await interaction.response.send_message(embed=embed)

        dm_embed = discord.Embed(
            title=f"⚠️ You were warned in {interaction.guild.name}",
            description=f"**Reason:** {reason}",
            color=discord.Color.yellow(),
        )
        dm_embed.set_footer(text=f"Warning #{warn_id} • {len(warnings)} total warning(s)")
        await try_dm(member, dm_embed)
        await send_mod_log(interaction.guild, embed)

    # ── /warnings ─────────────────────────────────────────────────────────────
    @app_commands.command(name="warnings", description="View a member's warnings.")
    @app_commands.describe(member="Member to check")
    @is_mod()
    async def warnings(self, interaction: discord.Interaction, member: discord.Member):
        rows = await db.get_warnings(interaction.guild_id, member.id)
        if not rows:
            return await interaction.response.send_message(
                embed=info("No Warnings", f"{member.mention} has no warnings."), ephemeral=True
            )

        pages = []
        chunk_size = 5
        chunks = [rows[i:i+chunk_size] for i in range(0, len(rows), chunk_size)]
        for chunk in chunks:
            embed = discord.Embed(title=f"⚠️ Warnings for {member}", color=discord.Color.yellow())
            embed.set_thumbnail(url=member.display_avatar.url)
            for row in chunk:
                embed.add_field(
                    name=f"#{row['id']} — {row['created_at'].strftime('%Y-%m-%d')}",
                    value=f"**Reason:** {row['reason']}\n**By:** <@{row['moderator_id']}>",
                    inline=False,
                )
            pages.append(embed)

        if len(pages) == 1:
            await interaction.response.send_message(embed=pages[0], ephemeral=True)
        else:
            await interaction.response.send_message(embed=pages[0], view=Paginator(pages, interaction.user.id), ephemeral=True)

    # ── /clearwarnings ────────────────────────────────────────────────────────
    @app_commands.command(name="clearwarnings", description="Clear all warnings for a member.")
    @app_commands.describe(member="Member to clear warnings for")
    @is_admin()
    async def clearwarnings(self, interaction: discord.Interaction, member: discord.Member):
        count = await db.clear_warnings(interaction.guild_id, member.id)
        await interaction.response.send_message(
            embed=success("Warnings Cleared", f"Cleared **{count}** warning(s) for {member.mention}."),
            ephemeral=True,
        )

    # ── /kick ─────────────────────────────────────────────────────────────────
    @app_commands.command(name="kick", description="Kick a member from the server.")
    @app_commands.describe(member="Member to kick", reason="Reason for the kick")
    @is_mod()
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        if not await self._can_action(interaction, member):
            return
        await db.add_mod_log(interaction.guild_id, member.id, interaction.user.id, "kick", reason)

        dm_embed = discord.Embed(
            title=f"👢 You were kicked from {interaction.guild.name}",
            description=f"**Reason:** {reason}",
            color=discord.Color.orange(),
        )
        await try_dm(member, dm_embed)
        await member.kick(reason=reason)

        embed = mod_action("kick", member, interaction.user, reason)
        await interaction.response.send_message(embed=embed)
        await send_mod_log(interaction.guild, embed)

    # ── /ban ──────────────────────────────────────────────────────────────────
    @app_commands.command(name="ban", description="Ban a member from the server.")
    @app_commands.describe(member="Member to ban", reason="Reason", delete_days="Days of messages to delete (0-7)")
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str = "No reason provided",
        delete_days: app_commands.Range[int, 0, 7] = 0,
    ):
        if not await self._can_action(interaction, member):
            return
        await db.add_mod_log(interaction.guild_id, member.id, interaction.user.id, "ban", reason)

        dm_embed = discord.Embed(
            title=f"🔨 You were banned from {interaction.guild.name}",
            description=f"**Reason:** {reason}",
            color=discord.Color.red(),
        )
        await try_dm(member, dm_embed)
        await member.ban(reason=reason, delete_message_days=delete_days)

        embed = mod_action("ban", member, interaction.user, reason)
        await interaction.response.send_message(embed=embed)
        await send_mod_log(interaction.guild, embed)

    # ── /unban ────────────────────────────────────────────────────────────────
    @app_commands.command(name="unban", description="Unban a user by ID.")
    @app_commands.describe(user_id="The user's Discord ID", reason="Reason for unban")
    @app_commands.checks.has_permissions(ban_members=True)
    async def unban(self, interaction: discord.Interaction, user_id: str, reason: str = "No reason provided"):
        await interaction.response.defer()
        try:
            user = await self.bot.fetch_user(int(user_id))
        except (ValueError, discord.NotFound):
            return await interaction.followup.send(embed=error("User Not Found", f"No user found with ID `{user_id}`."))

        try:
            await interaction.guild.unban(user, reason=reason)
        except discord.NotFound:
            return await interaction.followup.send(embed=error("Not Banned", f"`{user}` is not banned."))

        await db.add_mod_log(interaction.guild_id, user.id, interaction.user.id, "unban", reason)
        embed = discord.Embed(title="✅ User Unbanned", color=discord.Color.green())
        embed.add_field(name="User",      value=f"`{user}`")
        embed.add_field(name="Moderator", value=interaction.user.mention)
        embed.add_field(name="Reason",    value=reason, inline=False)
        await interaction.followup.send(embed=embed)
        await send_mod_log(interaction.guild, embed)

    # ── /mute ─────────────────────────────────────────────────────────────────
    @app_commands.command(name="mute", description="Mute a member using the mute role.")
    @app_commands.describe(member="Member to mute", reason="Reason")
    @is_mod()
    async def mute(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        if not await self._can_action(interaction, member):
            return

        cfg = await db.get_guild(interaction.guild_id)
        if not cfg or not cfg["mute_role_id"]:
            return await interaction.response.send_message(
                embed=error("No Mute Role", "Set a mute role first with `/set mute_role`."), ephemeral=True
            )

        mute_role = interaction.guild.get_role(cfg["mute_role_id"])
        if not mute_role:
            return await interaction.response.send_message(
                embed=error("Mute Role Not Found", "The configured mute role no longer exists."), ephemeral=True
            )

        if mute_role in member.roles:
            return await interaction.response.send_message(
                embed=error("Already Muted", f"{member.mention} is already muted."), ephemeral=True
            )

        await member.add_roles(mute_role, reason=reason)
        await db.add_mod_log(interaction.guild_id, member.id, interaction.user.id, "mute", reason)

        dm_embed = discord.Embed(
            title=f"🔇 You were muted in {interaction.guild.name}",
            description=f"**Reason:** {reason}",
            color=discord.Color.gold(),
        )
        await try_dm(member, dm_embed)

        embed = mod_action("mute", member, interaction.user, reason)
        await interaction.response.send_message(embed=embed)
        await send_mod_log(interaction.guild, embed)

    # ── /unmute ───────────────────────────────────────────────────────────────
    @app_commands.command(name="unmute", description="Unmute a member.")
    @app_commands.describe(member="Member to unmute", reason="Reason")
    @is_mod()
    async def unmute(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        cfg = await db.get_guild(interaction.guild_id)
        if not cfg or not cfg["mute_role_id"]:
            return await interaction.response.send_message(
                embed=error("No Mute Role", "Set a mute role first with `/set mute_role`."), ephemeral=True
            )

        mute_role = interaction.guild.get_role(cfg["mute_role_id"])
        if not mute_role or mute_role not in member.roles:
            return await interaction.response.send_message(
                embed=error("Not Muted", f"{member.mention} is not muted."), ephemeral=True
            )

        await member.remove_roles(mute_role, reason=reason)
        await db.add_mod_log(interaction.guild_id, member.id, interaction.user.id, "unmute", reason)

        embed = success("Member Unmuted", f"{member.mention} has been unmuted.")
        await interaction.response.send_message(embed=embed)
        await send_mod_log(interaction.guild, discord.Embed(
            title="🔊 Member Unmuted",
            description=f"{member.mention} was unmuted by {interaction.user.mention}\n**Reason:** {reason}",
            color=discord.Color.green(),
        ))

    # ── /timeout ──────────────────────────────────────────────────────────────
    @app_commands.command(name="timeout", description="Timeout a member.")
    @app_commands.describe(member="Member to timeout", minutes="Duration in minutes (max 40320)", reason="Reason")
    @is_mod()
    async def timeout(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        minutes: app_commands.Range[int, 1, 40320],
        reason: str = "No reason provided",
    ):
        if not await self._can_action(interaction, member):
            return

        duration = datetime.timedelta(minutes=minutes)
        await member.timeout(duration, reason=reason)
        await db.add_mod_log(interaction.guild_id, member.id, interaction.user.id, "timeout", reason, duration=minutes)

        dm_embed = discord.Embed(
            title=f"⏱️ You were timed out in {interaction.guild.name}",
            description=f"**Duration:** {minutes} minute(s)\n**Reason:** {reason}",
            color=discord.Color.gold(),
        )
        await try_dm(member, dm_embed)

        embed = mod_action("timeout", member, interaction.user, reason, Duration=f"{minutes} minute(s)")
        await interaction.response.send_message(embed=embed)
        await send_mod_log(interaction.guild, embed)

    # ── /untimeout ────────────────────────────────────────────────────────────
    @app_commands.command(name="untimeout", description="Remove a timeout from a member.")
    @app_commands.describe(member="Member to untimeout")
    @is_mod()
    async def untimeout(self, interaction: discord.Interaction, member: discord.Member):
        if not member.is_timed_out():
            return await interaction.response.send_message(
                embed=error("Not Timed Out", f"{member.mention} is not timed out."), ephemeral=True
            )
        await member.timeout(None)
        embed = success("Timeout Removed", f"{member.mention}'s timeout has been removed.")
        await interaction.response.send_message(embed=embed)

    # ── /purge ────────────────────────────────────────────────────────────────
    @app_commands.command(name="purge", description="Bulk delete messages.")
    @app_commands.describe(amount="Number of messages to delete (1–100)", member="Only delete messages from this member")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def purge(
        self,
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, 100],
        member: discord.Member | None = None,
    ):
        await interaction.response.defer(ephemeral=True)
        check = (lambda m: m.author == member) if member else None
        deleted = await interaction.channel.purge(limit=amount, check=check)
        await interaction.followup.send(
            embed=success("Purge Complete", f"Deleted **{len(deleted)}** message(s)."),
            ephemeral=True,
        )

    # ── /modlogs ──────────────────────────────────────────────────────────────
    @app_commands.command(name="modlogs", description="View moderation history for a member.")
    @app_commands.describe(member="Member to check")
    @is_mod()
    async def modlogs(self, interaction: discord.Interaction, member: discord.Member):
        rows = await db.get_mod_logs(interaction.guild_id, member.id)
        if not rows:
            return await interaction.response.send_message(
                embed=info("No History", f"{member.mention} has no moderation history."), ephemeral=True
            )

        pages = []
        chunks = [rows[i:i+5] for i in range(0, len(rows), 5)]
        for chunk in chunks:
            embed = discord.Embed(title=f"📋 Mod Logs — {member}", color=discord.Color.blurple())
            embed.set_thumbnail(url=member.display_avatar.url)
            for row in chunk:
                value = f"**Reason:** {row['reason'] or 'None'}\n**By:** <@{row['moderator_id']}>"
                if row["duration"]:
                    value += f"\n**Duration:** {row['duration']}m"
                embed.add_field(
                    name=f"{row['action'].upper()} — {row['created_at'].strftime('%Y-%m-%d %H:%M')}",
                    value=value,
                    inline=False,
                )
            pages.append(embed)

        if len(pages) == 1:
            await interaction.response.send_message(embed=pages[0], ephemeral=True)
        else:
            await interaction.response.send_message(embed=pages[0], view=Paginator(pages, interaction.user.id), ephemeral=True)

    # ── /slowmode ─────────────────────────────────────────────────────────────
    @app_commands.command(name="slowmode", description="Set slowmode for a channel.")
    @app_commands.describe(seconds="Slowmode in seconds (0 to disable)", channel="Channel to apply slowmode to")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def slowmode(
        self,
        interaction: discord.Interaction,
        seconds: app_commands.Range[int, 0, 21600],
        channel: discord.TextChannel | None = None,
    ):
        target = channel or interaction.channel
        await target.edit(slowmode_delay=seconds)
        msg = f"Slowmode {'disabled' if seconds == 0 else f'set to **{seconds}s**'} in {target.mention}."
        await interaction.response.send_message(embed=success("Slowmode Updated", msg))

    # ── /lock / /unlock ───────────────────────────────────────────────────────
    @app_commands.command(name="lock", description="Lock a channel so members can't send messages.")
    @app_commands.describe(channel="Channel to lock (defaults to current)")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def lock(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None):
        target = channel or interaction.channel
        overwrite = target.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = False
        await target.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        await interaction.response.send_message(embed=success("Channel Locked", f"🔒 {target.mention} is now locked."))

    @app_commands.command(name="unlock", description="Unlock a channel.")
    @app_commands.describe(channel="Channel to unlock (defaults to current)")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def unlock(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None):
        target = channel or interaction.channel
        overwrite = target.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = None
        await target.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        await interaction.response.send_message(embed=success("Channel Unlocked", f"🔓 {target.mention} is now unlocked."))

    # ── Helper ────────────────────────────────────────────────────────────────
    async def _can_action(self, interaction: discord.Interaction, member: discord.Member) -> bool:
        """Check role hierarchy before taking a mod action."""
        if member.bot:
            await interaction.response.send_message(embed=error("Can't action bots."), ephemeral=True)
            return False
        if member == interaction.user:
            await interaction.response.send_message(embed=error("You can't action yourself."), ephemeral=True)
            return False
        if member.top_role >= interaction.user.top_role:  # type: ignore[union-attr]
            await interaction.response.send_message(
                embed=error("Insufficient Role", "You can't action someone with an equal or higher role."),
                ephemeral=True,
            )
            return False
        if member.top_role >= interaction.guild.me.top_role:
            await interaction.response.send_message(
                embed=error("Bot Insufficient Role", "My role is too low to action this member."),
                ephemeral=True,
            )
            return False
        return True

    # ── Error handler ─────────────────────────────────────────────────────────
    async def cog_app_command_error(self, interaction: discord.Interaction, err: app_commands.AppCommandError):
        msg = "You don't have permission to use this command." if isinstance(err, app_commands.MissingPermissions) else f"`{err}`"
        if interaction.response.is_done():
            await interaction.followup.send(embed=error("Error", msg), ephemeral=True)
        else:
            await interaction.response.send_message(embed=error("Error", msg), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
