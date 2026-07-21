import discord
from discord import app_commands
from discord.ext import commands
from database.db import get_pool
from utils.embeds import error, info
from utils.paginator import Paginator
import config


def xp_to_level(xp: int) -> int:
    level = 0
    while xp >= int(100 * ((level + 1) ** 1.5)):
        level += 1
    return level


class Leaderboard(commands.Cog):
    """Combined server leaderboard dashboard."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── /lb group ─────────────────────────────────────────────────────────────
    lb_group = app_commands.Group(name="lb", description="Leaderboard commands.")

    # ── /lb xp ────────────────────────────────────────────────────────────────
    @lb_group.command(name="xp", description="Show the XP leaderboard.")
    async def lb_xp(self, interaction: discord.Interaction):
        pool = get_pool()
        rows = await pool.fetch(
            "SELECT * FROM levels WHERE guild_id=$1 ORDER BY xp DESC LIMIT 50",
            interaction.guild_id,
        )
        if not rows:
            return await interaction.response.send_message(
                embed=info("Empty", "No XP data yet."), ephemeral=True
            )

        pages  = []
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        chunks = [rows[i:i+10] for i in range(0, len(rows), 10)]
        for chunk in chunks:
            embed = discord.Embed(title="⭐ XP Leaderboard", color=config.BOT_COLOR)
            lines = []
            for i, row in enumerate(chunk, start=chunks.index(chunk) * 10 + 1):
                icon   = medals.get(i, f"`#{i}`")
                member = interaction.guild.get_member(row["user_id"])
                name   = member.display_name if member else f"`{row['user_id']}`"
                level  = xp_to_level(row["xp"])
                lines.append(f"{icon} **{name}** — Level `{level}` • `{row['xp']:,}` XP")
            embed.description = "\n".join(lines)
            pages.append(embed)

        if len(pages) == 1:
            await interaction.response.send_message(embed=pages[0])
        else:
            await interaction.response.send_message(embed=pages[0], view=Paginator(pages, interaction.user.id))

    # ── /lb economy ───────────────────────────────────────────────────────────
    @lb_group.command(name="economy", description="Show the richest members.")
    async def lb_economy(self, interaction: discord.Interaction):
        pool = get_pool()
        cfg  = await pool.fetchrow("SELECT currency_name, currency_emoji FROM guild_settings WHERE guild_id=$1", interaction.guild_id)
        name  = cfg["currency_name"]  if cfg else "coins"
        emoji = cfg["currency_emoji"] if cfg else "🪙"

        rows = await pool.fetch(
            "SELECT * FROM economy WHERE guild_id=$1 ORDER BY balance+bank DESC LIMIT 50",
            interaction.guild_id,
        )
        if not rows:
            return await interaction.response.send_message(
                embed=info("Empty", "No economy data yet."), ephemeral=True
            )

        pages  = []
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        chunks = [rows[i:i+10] for i in range(0, len(rows), 10)]
        for chunk in chunks:
            embed = discord.Embed(title=f"{emoji} Economy Leaderboard", color=config.BOT_COLOR)
            lines = []
            for i, row in enumerate(chunk, start=chunks.index(chunk) * 10 + 1):
                icon   = medals.get(i, f"`#{i}`")
                member = interaction.guild.get_member(row["user_id"])
                mname  = member.display_name if member else f"`{row['user_id']}`"
                total  = row["balance"] + row["bank"]
                lines.append(f"{icon} **{mname}** — `{total:,}` {name}")
            embed.description = "\n".join(lines)
            pages.append(embed)

        if len(pages) == 1:
            await interaction.response.send_message(embed=pages[0])
        else:
            await interaction.response.send_message(embed=pages[0], view=Paginator(pages, interaction.user.id))

    # ── /lb invites ───────────────────────────────────────────────────────────
    @lb_group.command(name="invites", description="Show the top inviters.")
    async def lb_invites(self, interaction: discord.Interaction):
        pool = get_pool()
        rows = await pool.fetch(
            """SELECT inviter_id, COUNT(*) FILTER (WHERE left IS NOT TRUE) AS active, COUNT(*) AS total
               FROM invite_tracker WHERE guild_id=$1
               GROUP BY inviter_id ORDER BY active DESC LIMIT 30""",
            interaction.guild_id,
        )
        if not rows:
            return await interaction.response.send_message(
                embed=info("Empty", "No invite data yet."), ephemeral=True
            )

        embed  = discord.Embed(title="🔗 Invite Leaderboard", color=config.BOT_COLOR)
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        lines  = []
        for i, row in enumerate(rows[:10], start=1):
            icon   = medals.get(i, f"`#{i}`")
            member = interaction.guild.get_member(row["inviter_id"])
            mname  = member.display_name if member else f"`{row['inviter_id']}`"
            lines.append(f"{icon} **{mname}** — `{row['active']}` active (`{row['total']}` total)")
        embed.description = "\n".join(lines)
        await interaction.response.send_message(embed=embed)

    # ── /lb combined ──────────────────────────────────────────────────────────
    @lb_group.command(name="combined", description="Show a combined score leaderboard (XP + economy).")
    async def lb_combined(self, interaction: discord.Interaction):
        pool = get_pool()
        xp_rows  = await pool.fetch("SELECT user_id, xp FROM levels   WHERE guild_id=$1", interaction.guild_id)
        eco_rows = await pool.fetch("SELECT user_id, balance+bank AS total FROM economy WHERE guild_id=$1", interaction.guild_id)

        # Merge scores
        scores: dict[int, dict] = {}
        for row in xp_rows:
            scores.setdefault(row["user_id"], {"xp": 0, "coins": 0})["xp"] = row["xp"]
        for row in eco_rows:
            scores.setdefault(row["user_id"], {"xp": 0, "coins": 0})["coins"] = row["total"]

        if not scores:
            return await interaction.response.send_message(
                embed=info("Empty", "No data yet."), ephemeral=True
            )

        # Combined score: level * 1000 + coins (normalised)
        ranked = sorted(
            scores.items(),
            key=lambda x: xp_to_level(x[1]["xp"]) * 1000 + x[1]["coins"] // 100,
            reverse=True,
        )[:30]

        pages  = []
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        chunks = [ranked[i:i+10] for i in range(0, len(ranked), 10)]
        for chunk in chunks:
            embed = discord.Embed(title="🏆 Combined Leaderboard", color=config.BOT_COLOR)
            embed.description = "*Score = Level × 1000 + Coins ÷ 100*"
            lines = []
            for i, (uid, data) in enumerate(chunk, start=chunks.index(chunk) * 10 + 1):
                icon   = medals.get(i, f"`#{i}`")
                member = interaction.guild.get_member(uid)
                mname  = member.display_name if member else f"`{uid}`"
                level  = xp_to_level(data["xp"])
                score  = level * 1000 + data["coins"] // 100
                lines.append(f"{icon} **{mname}** — Score `{score:,}` (Lv.{level} • {data['coins']:,} coins)")
            embed.description += "\n\n" + "\n".join(lines)
            pages.append(embed)

        if len(pages) == 1:
            await interaction.response.send_message(embed=pages[0])
        else:
            await interaction.response.send_message(embed=pages[0], view=Paginator(pages, interaction.user.id))

    # ── /lb server ────────────────────────────────────────────────────────────
    @lb_group.command(name="server", description="Show a full server stats overview.")
    async def lb_server(self, interaction: discord.Interaction):
        pool  = get_pool()
        guild = interaction.guild

        total_xp     = await pool.fetchval("SELECT COALESCE(SUM(xp),0)          FROM levels       WHERE guild_id=$1", guild.id) or 0
        total_coins  = await pool.fetchval("SELECT COALESCE(SUM(balance+bank),0) FROM economy      WHERE guild_id=$1", guild.id) or 0
        total_warns  = await pool.fetchval("SELECT COUNT(*)                       FROM warnings     WHERE guild_id=$1", guild.id) or 0
        total_mod    = await pool.fetchval("SELECT COUNT(*)                       FROM mod_logs     WHERE guild_id=$1", guild.id) or 0
        total_ticket = await pool.fetchval("SELECT COUNT(*)                       FROM tickets      WHERE guild_id=$1", guild.id) or 0
        total_cmds   = await pool.fetchval("SELECT COUNT(*)                       FROM custom_commands WHERE guild_id=$1", guild.id) or 0
        total_inv    = await pool.fetchval("SELECT COUNT(*)                       FROM invite_tracker  WHERE guild_id=$1", guild.id) or 0

        cfg   = await pool.fetchrow("SELECT currency_name, currency_emoji FROM guild_settings WHERE guild_id=$1", guild.id)
        cname = cfg["currency_name"]  if cfg else "coins"
        cemoj = cfg["currency_emoji"] if cfg else "🪙"

        embed = discord.Embed(
            title=f"🏆 {guild.name} — Server Overview",
            color=config.BOT_COLOR,
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(name="👥 Members",      value=f"`{guild.member_count}`")
        embed.add_field(name="🤖 Bots",         value=f"`{sum(1 for m in guild.members if m.bot)}`")
        embed.add_field(name="📢 Channels",     value=f"`{len(guild.channels)}`")
        embed.add_field(name="⭐ Total XP",     value=f"`{total_xp:,}`")
        embed.add_field(name=f"{cemoj} {cname.title()}", value=f"`{total_coins:,}`")
        embed.add_field(name="⚠️ Warnings",    value=f"`{total_warns}`")
        embed.add_field(name="🔨 Mod Actions",  value=f"`{total_mod}`")
        embed.add_field(name="🎫 Tickets",      value=f"`{total_ticket}`")
        embed.add_field(name="🔗 Invites",      value=f"`{total_inv}`")
        embed.add_field(name="📝 Custom Cmds",  value=f"`{total_cmds}`")
        embed.add_field(name="✨ Boosts",       value=f"`{guild.premium_subscription_count}` (Tier {guild.premium_tier})")
        embed.set_footer(text=f"Server ID: {guild.id}")
        await interaction.response.send_message(embed=embed)

    async def cog_app_command_error(self, interaction: discord.Interaction, err: app_commands.AppCommandError):
        msg = f"`{err}`"
        if interaction.response.is_done():
            await interaction.followup.send(embed=error("Error", msg), ephemeral=True)
        else:
            await interaction.response.send_message(embed=error("Error", msg), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Leaderboard(bot))
