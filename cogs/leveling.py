import random
import discord
from discord import app_commands
from discord.ext import commands
from database import db
from utils.checks import is_admin
from utils.embeds import success, error, info
from utils.paginator import Paginator


def xp_for_level(level: int) -> int:
    """XP required to reach a given level. Curve gets steeper each level."""
    return int(100 * (level ** 1.5))


def level_from_xp(xp: int) -> int:
    """Calculate level from total XP."""
    level = 0
    while xp >= xp_for_level(level + 1):
        level += 1
    return level


def format_message(template: str, member: discord.Member, level: int) -> str:
    return (
        template
        .replace("{user}",   member.mention)
        .replace("{name}",   member.display_name)
        .replace("{level}",  str(level))
        .replace("{server}", member.guild.name)
    )


class Leveling(commands.Cog):
    """XP and leveling system."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        cfg = await db.get_guild(message.guild.id)
        if not cfg or not cfg["leveling_enabled"]:
            return

        # ── Cooldown check ────────────────────────────────────────────────────
        import datetime
        row = await db.get_level(message.guild.id, message.author.id)
        if row and row["last_message_at"]:
            elapsed = (datetime.datetime.now(datetime.timezone.utc) - row["last_message_at"]).total_seconds()
            if elapsed < cfg["xp_cooldown"]:
                return

        # ── Award XP ──────────────────────────────────────────────────────────
        xp_gain  = random.randint(cfg["xp_min"], cfg["xp_max"])
        updated  = await db.add_xp(message.guild.id, message.author.id, xp_gain)
        old_level = level_from_xp(updated["xp"] - xp_gain)
        new_level = level_from_xp(updated["xp"])

        if new_level <= old_level:
            return

        # ── Level up! ─────────────────────────────────────────────────────────
        await db.set_level(message.guild.id, message.author.id, new_level)
        await self._handle_level_up(message, cfg, new_level)

    async def _handle_level_up(self, message: discord.Message, cfg, new_level: int):
        member = message.author

        # ── Level role rewards ────────────────────────────────────────────────
        level_roles = await db.get_level_roles(message.guild.id)
        for lr in level_roles:
            if lr["level"] == new_level:
                role = message.guild.get_role(lr["role_id"])
                if role and role not in member.roles:
                    try:
                        await member.add_roles(role, reason=f"Level {new_level} reward")
                    except discord.Forbidden:
                        pass

        # ── Announcement ──────────────────────────────────────────────────────
        channel_id = cfg["level_up_channel_id"] or message.channel.id
        channel    = message.guild.get_channel(channel_id) or message.channel
        text       = format_message(cfg["level_up_message"], member, new_level)

        embed = discord.Embed(description=text, color=0xFFD700)
        embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
        embed.set_footer(text=f"🏆 Level {new_level} reached!")

        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            pass

    # ── /rank ─────────────────────────────────────────────────────────────────
    @app_commands.command(name="rank", description="Check your or another member's rank.")
    @app_commands.describe(member="Member to check (defaults to you)")
    async def rank(self, interaction: discord.Interaction, member: discord.Member | None = None):
        cfg = await db.get_guild(interaction.guild_id)
        if not cfg or not cfg["leveling_enabled"]:
            return await interaction.response.send_message(
                embed=error("Leveling Disabled", "Leveling is not enabled on this server."), ephemeral=True
            )

        target = member or interaction.user
        row    = await db.get_level(interaction.guild_id, target.id)

        if not row:
            return await interaction.response.send_message(
                embed=info("No Data", f"{target.mention} hasn't earned any XP yet."), ephemeral=True
            )

        xp       = row["xp"]
        level    = level_from_xp(xp)
        curr_xp  = xp - sum(xp_for_level(l) for l in range(1, level + 1))
        next_xp  = xp_for_level(level + 1)
        progress = int((curr_xp / next_xp) * 20) if next_xp else 20
        bar      = "█" * progress + "░" * (20 - progress)

        # Rank position
        lb = await db.get_leaderboard(interaction.guild_id, limit=1000)
        rank_pos = next((i + 1 for i, r in enumerate(lb) if r["user_id"] == target.id), "?")

        embed = discord.Embed(color=0xFFD700)
        embed.set_author(name=f"{target.display_name}'s Rank", icon_url=target.display_avatar.url)
        embed.add_field(name="Level",   value=f"`{level}`",            inline=True)
        embed.add_field(name="Rank",    value=f"`#{rank_pos}`",        inline=True)
        embed.add_field(name="Total XP",value=f"`{xp:,}`",            inline=True)
        embed.add_field(name="Progress",value=f"`{bar}` {curr_xp:,}/{next_xp:,} XP", inline=False)
        await interaction.response.send_message(embed=embed)

    # ── /leaderboard ──────────────────────────────────────────────────────────
    @app_commands.command(name="leaderboard", description="Show the XP leaderboard.")
    async def leaderboard(self, interaction: discord.Interaction):
        cfg = await db.get_guild(interaction.guild_id)
        if not cfg or not cfg["leveling_enabled"]:
            return await interaction.response.send_message(
                embed=error("Leveling Disabled", "Leveling is not enabled on this server."), ephemeral=True
            )

        rows = await db.get_leaderboard(interaction.guild_id, limit=50)
        if not rows:
            return await interaction.response.send_message(
                embed=info("Empty", "No one has earned XP yet."), ephemeral=True
            )

        pages  = []
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        chunks = [rows[i:i+10] for i in range(0, len(rows), 10)]

        for chunk in chunks:
            embed = discord.Embed(title="🏆 XP Leaderboard", color=0xFFD700)
            lines = []
            for i, row in enumerate(chunk, start=chunks.index(chunk) * 10 + 1):
                icon  = medals.get(i, f"`#{i}`")
                level = level_from_xp(row["xp"])
                lines.append(f"{icon} <@{row['user_id']}> — Level **{level}** • `{row['xp']:,}` XP")
            embed.description = "\n".join(lines)
            pages.append(embed)

        if len(pages) == 1:
            await interaction.response.send_message(embed=pages[0])
        else:
            await interaction.response.send_message(embed=pages[0], view=Paginator(pages, interaction.user.id))

    # ── /setxp ────────────────────────────────────────────────────────────────
    @app_commands.command(name="setxp", description="Set a member's XP (admin only).")
    @app_commands.describe(member="Member to set XP for", xp="Amount of XP to set")
    @is_admin()
    async def setxp(self, interaction: discord.Interaction, member: discord.Member, xp: app_commands.Range[int, 0, 9999999]):
        row = await db.get_level(interaction.guild_id, member.id)
        if not row:
            await db.add_xp(interaction.guild_id, member.id, 0)

        new_level = level_from_xp(xp)
        await db.get_pool().execute(
            "UPDATE levels SET xp=$3, level=$4 WHERE guild_id=$1 AND user_id=$2",
            interaction.guild_id, member.id, xp, new_level,
        )
        await interaction.response.send_message(
            embed=success("XP Set", f"{member.mention} now has `{xp:,}` XP (Level **{new_level}**)."),
            ephemeral=True,
        )

    # ── /levelrole ────────────────────────────────────────────────────────────
    @app_commands.command(name="levelrole", description="Set a role reward for reaching a level.")
    @app_commands.describe(level="Level required", role="Role to give")
    @is_admin()
    async def levelrole(self, interaction: discord.Interaction, level: app_commands.Range[int, 1, 500], role: discord.Role):
        await db.set_level_role(interaction.guild_id, level, role.id)
        await interaction.response.send_message(
            embed=success("Level Role Set", f"{role.mention} will be awarded at Level **{level}**."),
            ephemeral=True,
        )

    # ── /removelevelrole ──────────────────────────────────────────────────────
    @app_commands.command(name="removelevelrole", description="Remove a level role reward.")
    @app_commands.describe(level="Level to remove the reward from")
    @is_admin()
    async def removelevelrole(self, interaction: discord.Interaction, level: int):
        await db.remove_level_role(interaction.guild_id, level)
        await interaction.response.send_message(
            embed=success("Level Role Removed", f"Removed role reward for Level **{level}**."),
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Leveling(bot))
