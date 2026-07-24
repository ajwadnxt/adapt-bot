import discord
from discord import app_commands
from discord.ext import commands
from database.db import get_pool
from utils.checks import is_admin
from utils.embeds import success, error, info
from utils.paginator import Paginator
import config


class Invites(commands.Cog):
    """Invite tracking — who invited who, leaderboard."""

    def __init__(self, bot: commands.Bot):
        self.bot          = bot
        self._cache: dict[int, dict[str, discord.Invite]] = {}

    async def cog_load(self):
        self.bot.loop.create_task(self._build_cache())

    async def _build_cache(self):
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            await self._cache_guild(guild)

    async def _cache_guild(self, guild: discord.Guild):
        try:
            invites = await guild.invites()
            self._cache[guild.id] = {inv.code: inv for inv in invites}
        except (discord.Forbidden, discord.HTTPException):
            self._cache[guild.id] = {}

    # ── Events ────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        await self._cache_guild(guild)

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        if invite.guild.id not in self._cache:
            self._cache[invite.guild.id] = {}
        self._cache[invite.guild.id][invite.code] = invite

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        if invite.guild.id in self._cache:
            self._cache[invite.guild.id].pop(invite.code, None)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return

        guild      = member.guild
        old_cache  = self._cache.get(guild.id, {})
        inviter_id = None
        used_code  = None

        try:
            new_invites = await guild.invites()
            new_cache   = {inv.code: inv for inv in new_invites}

            for code, inv in new_cache.items():
                old = old_cache.get(code)
                if old and inv.uses > old.uses and inv.inviter:
                    inviter_id = inv.inviter.id
                    used_code  = code
                    break

            self._cache[guild.id] = new_cache
        except (discord.Forbidden, discord.HTTPException):
            return

        if inviter_id:
            pool = get_pool()
            await pool.execute(
                """INSERT INTO invite_tracker (guild_id, inviter_id, invitee_id, invite_code)
                   VALUES ($1,$2,$3,$4)
                   ON CONFLICT (guild_id, invitee_id) DO UPDATE
                   SET inviter_id=$2, invite_code=$4""",
                guild.id, inviter_id, member.id, used_code,
            )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Track when an invited member leaves (for accurate invite counts)."""
        pool = get_pool()
        await pool.execute(
            "UPDATE invite_tracker SET is_left=TRUE WHERE guild_id=$1 AND invitee_id=$2",
            member.guild.id, member.id,
        )

    # ── /invite group ─────────────────────────────────────────────────────────
    invite_group = app_commands.Group(name="invites", description="Invite tracking commands.")

    @invite_group.command(name="check", description="Check who invited a member.")
    @app_commands.describe(member="Member to check")
    async def invite_check(self, interaction: discord.Interaction, member: discord.Member):
        pool = get_pool()
        row  = await pool.fetchrow(
            "SELECT * FROM invite_tracker WHERE guild_id=$1 AND invitee_id=$2",
            interaction.guild_id, member.id,
        )
        if not row:
            return await interaction.response.send_message(
                embed=info("Unknown", f"No invite data found for {member.mention}."), ephemeral=True
            )

        inviter = interaction.guild.get_member(row["inviter_id"])
        embed   = discord.Embed(title="🔗 Invite Info", color=config.BOT_COLOR)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Member",      value=member.mention)
        embed.add_field(name="Invited by",  value=inviter.mention if inviter else f"`{row['inviter_id']}`")
        embed.add_field(name="Invite Code", value=f"`{row['invite_code']}`")
        embed.add_field(name="Joined",      value=discord.utils.format_dt(member.joined_at, "R") if member.joined_at else "Unknown")
        await interaction.response.send_message(embed=embed)

    @invite_group.command(name="stats", description="Check your or another member's invite stats.")
    @app_commands.describe(member="Member to check (defaults to you)")
    async def invite_stats(self, interaction: discord.Interaction, member: discord.Member | None = None):
        target = member or interaction.user
        pool   = get_pool()

        total = await pool.fetchval(
            "SELECT COUNT(*) FROM invite_tracker WHERE guild_id=$1 AND inviter_id=$2",
            interaction.guild_id, target.id,
        ) or 0
        left = await pool.fetchval(
            "SELECT COUNT(*) FROM invite_tracker WHERE guild_id=$1 AND inviter_id=$2 AND left=TRUE",
            interaction.guild_id, target.id,
        ) or 0
        active = total - left

        # Get current Discord invite uses
        try:
            guild_invites = await interaction.guild.invites()
            discord_uses  = sum(inv.uses or 0 for inv in guild_invites if inv.inviter and inv.inviter.id == target.id)
        except discord.Forbidden:
            discord_uses = 0

        embed = discord.Embed(title=f"🔗 Invite Stats — {target.display_name}", color=config.BOT_COLOR)
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Total Invited", value=f"`{total}`")
        embed.add_field(name="Still Here",    value=f"`{active}`")
        embed.add_field(name="Left",          value=f"`{left}`")
        embed.add_field(name="Discord Uses",  value=f"`{discord_uses}`")
        await interaction.response.send_message(embed=embed)

    @invite_group.command(name="leaderboard", description="Show the top inviters in this server.")
    async def invite_leaderboard(self, interaction: discord.Interaction):
        pool = get_pool()
        rows = await pool.fetch(
            """SELECT inviter_id,
                      COUNT(*) FILTER (WHERE left IS NOT TRUE) AS active,
                      COUNT(*) AS total
               FROM invite_tracker
               WHERE guild_id=$1
               GROUP BY inviter_id
               ORDER BY active DESC
               LIMIT 30""",
            interaction.guild_id,
        )
        if not rows:
            return await interaction.response.send_message(
                embed=info("Empty", "No invite data yet."), ephemeral=True
            )

        pages  = []
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        chunks = [rows[i:i+10] for i in range(0, len(rows), 10)]
        for chunk in chunks:
            embed = discord.Embed(title="🔗 Invite Leaderboard", color=config.BOT_COLOR)
            lines = []
            for i, row in enumerate(chunk, start=chunks.index(chunk) * 10 + 1):
                icon   = medals.get(i, f"`#{i}`")
                member = interaction.guild.get_member(row["inviter_id"])
                name   = member.display_name if member else f"`{row['inviter_id']}`"
                lines.append(f"{icon} **{name}** — `{row['active']}` active (`{row['total']}` total)")
            embed.description = "\n".join(lines)
            pages.append(embed)

        if len(pages) == 1:
            await interaction.response.send_message(embed=pages[0])
        else:
            await interaction.response.send_message(embed=pages[0], view=Paginator(pages, interaction.user.id))

    @invite_group.command(name="list", description="List all active invite codes in this server.")
    @is_admin()
    async def invite_list(self, interaction: discord.Interaction):
        try:
            invites = await interaction.guild.invites()
        except discord.Forbidden:
            return await interaction.response.send_message(
                embed=error("Missing Permission", "I need Manage Guild permission to view invites."), ephemeral=True
            )

        if not invites:
            return await interaction.response.send_message(
                embed=info("No Invites", "No active invite codes."), ephemeral=True
            )

        pages  = []
        chunks = [invites[i:i+10] for i in range(0, len(invites), 10)]
        for chunk in chunks:
            embed = discord.Embed(title="🔗 Server Invites", color=config.BOT_COLOR)
            for inv in chunk:
                embed.add_field(
                    name=f"`{inv.code}`",
                    value=(
                        f"**By:** {inv.inviter.mention if inv.inviter else 'Unknown'}\n"
                        f"**Uses:** `{inv.uses}`\n"
                        f"**Channel:** {inv.channel.mention if inv.channel else 'Unknown'}\n"
                        f"**Expires:** {discord.utils.format_dt(inv.expires_at, 'R') if inv.expires_at else 'Never'}"
                    ),
                    inline=True,
                )
            pages.append(embed)

        if len(pages) == 1:
            await interaction.response.send_message(embed=pages[0], ephemeral=True)
        else:
            await interaction.response.send_message(embed=pages[0], view=Paginator(pages, interaction.user.id), ephemeral=True)

    @invite_group.command(name="reset", description="Reset invite data for a member.")
    @app_commands.describe(member="Member to reset invite data for")
    @is_admin()
    async def invite_reset(self, interaction: discord.Interaction, member: discord.Member):
        pool = get_pool()
        await pool.execute(
            "DELETE FROM invite_tracker WHERE guild_id=$1 AND inviter_id=$2",
            interaction.guild_id, member.id,
        )
        await interaction.response.send_message(
            embed=success("Reset", f"Invite data for {member.mention} has been cleared."), ephemeral=True
        )

    async def cog_app_command_error(self, interaction: discord.Interaction, err: app_commands.AppCommandError):
        msg = "You need Administrator permission." if isinstance(err, app_commands.MissingPermissions) else f"`{err}`"
        if interaction.response.is_done():
            await interaction.followup.send(embed=error("Error", msg), ephemeral=True)
        else:
            await interaction.response.send_message(embed=error("Error", msg), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Invites(bot))