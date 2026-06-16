import asyncio
import datetime
import random
import discord
from discord import app_commands
from discord.ext import commands, tasks
from database.db import get_pool
from utils.checks import is_admin
from utils.embeds import success, error, info
import config


# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_duration(text: str) -> int | None:
    """Convert e.g. '1h30m', '2d', '45s' to total seconds. Returns None if invalid."""
    import re
    pattern = re.findall(r"(\d+)([smhd])", text.lower())
    if not pattern:
        return None
    units   = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return sum(int(v) * units[u] for v, u in pattern)


def format_duration(seconds: int) -> str:
    d, r = divmod(seconds, 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    if s or not parts: parts.append(f"{s}s")
    return " ".join(parts)


def giveaway_embed(
    prize: str,
    host: discord.Member,
    winner_count: int,
    ends_at: datetime.datetime,
    required_role: discord.Role | None = None,
    ended: bool = False,
    winners: list[discord.Member] = None,
) -> discord.Embed:
    color = discord.Color.green() if not ended else discord.Color.greyple()
    embed = discord.Embed(
        title=f"🎉 {prize}",
        color=color,
    )
    if not ended:
        embed.description = (
            f"Click the 🎉 button below to enter!\n\n"
            f"**Ends:** {discord.utils.format_dt(ends_at, 'R')} ({discord.utils.format_dt(ends_at, 'f')})\n"
            f"**Winners:** {winner_count}\n"
            f"**Hosted by:** {host.mention}"
        )
        if required_role:
            embed.description += f"\n**Required Role:** {required_role.mention}"
    else:
        if winners:
            winner_mentions = " ".join(w.mention for w in winners)
            embed.description = (
                f"**Prize:** {prize}\n"
                f"**Winner(s):** {winner_mentions}\n"
                f"**Hosted by:** {host.mention}\n\n"
                f"Congratulations! 🎊"
            )
        else:
            embed.description = (
                f"**Prize:** {prize}\n"
                f"**No valid entrants** — no winners could be drawn.\n"
                f"**Hosted by:** {host.mention}"
            )
    embed.set_footer(text=f"{'Giveaway ended' if ended else 'Giveaway'} • {winner_count} winner(s)")
    embed.timestamp = ends_at
    return embed


# ── Entry Button View ─────────────────────────────────────────────────────────

class GiveawayView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Enter Giveaway", emoji="🎉", style=discord.ButtonStyle.green, custom_id="giveaway:enter")
    async def enter(self, interaction: discord.Interaction, button: discord.ui.Button):
        pool = get_pool()
        row  = await pool.fetchrow(
            "SELECT * FROM giveaways WHERE message_id=$1", interaction.message.id
        )
        if not row:
            return await interaction.response.send_message(
                embed=error("Not Found", "This giveaway no longer exists."), ephemeral=True
            )
        if row["ended"]:
            return await interaction.response.send_message(
                embed=error("Ended", "This giveaway has already ended."), ephemeral=True
            )
        if row["ends_at"].replace(tzinfo=datetime.timezone.utc) < datetime.datetime.now(datetime.timezone.utc):
            return await interaction.response.send_message(
                embed=error("Ended", "This giveaway has already ended."), ephemeral=True
            )

        # Required role check
        if row["required_role_id"]:
            role = interaction.guild.get_role(row["required_role_id"])
            if role and role not in interaction.user.roles:
                return await interaction.response.send_message(
                    embed=error("Missing Role", f"You need {role.mention} to enter this giveaway."),
                    ephemeral=True,
                )

        # Check if already entered
        existing = await pool.fetchrow(
            "SELECT 1 FROM giveaway_entries WHERE giveaway_id=$1 AND user_id=$2",
            row["id"], interaction.user.id
        )
        if existing:
            # Allow leaving
            await pool.execute(
                "DELETE FROM giveaway_entries WHERE giveaway_id=$1 AND user_id=$2",
                row["id"], interaction.user.id
            )
            count = await pool.fetchval("SELECT COUNT(*) FROM giveaway_entries WHERE giveaway_id=$1", row["id"])
            button.label = f"Enter Giveaway ({count})"
            return await interaction.response.send_message(
                embed=info("Left Giveaway", "You have left this giveaway."), ephemeral=True
            )

        # Enter
        await pool.execute(
            "INSERT INTO giveaway_entries (giveaway_id, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            row["id"], interaction.user.id
        )
        count = await pool.fetchval("SELECT COUNT(*) FROM giveaway_entries WHERE giveaway_id=$1", row["id"])

        # Update button label with entry count
        view = GiveawayView()
        view.enter.label = f"Enter Giveaway ({count})"
        try:
            await interaction.message.edit(view=view)
        except discord.HTTPException:
            pass

        await interaction.response.send_message(
            embed=success("Entered!", f"You entered the **{row['prize']}** giveaway! Good luck 🍀\n{count} total entries."),
            ephemeral=True,
        )


# ── Cog ───────────────────────────────────────────────────────────────────────

class Giveaway(commands.Cog):
    """Full giveaway system with persistent buttons and auto-end."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.add_view(GiveawayView())  # Register persistent view
        self.check_giveaways.start()

    def cog_unload(self):
        self.check_giveaways.cancel()

    # ── Background task: auto-end expired giveaways ───────────────────────────
    @tasks.loop(seconds=30)
    async def check_giveaways(self):
        try:
            pool = get_pool()
            now  = datetime.datetime.now(datetime.timezone.utc)
            rows = await pool.fetch(
                "SELECT * FROM giveaways WHERE ended=FALSE AND ends_at <= $1", now
            )
            for row in rows:
                await self._end_giveaway(row["id"])
        except Exception as e:
            pass  # Pool may not be ready yet on startup

    @check_giveaways.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    # ── Core end logic ────────────────────────────────────────────────────────
    async def _end_giveaway(self, giveaway_id: int) -> list[int]:
        """End a giveaway, pick winners, update message. Returns list of winner IDs."""
        pool = get_pool()
        row  = await pool.fetchrow("SELECT * FROM giveaways WHERE id=$1", giveaway_id)
        if not row or row["ended"]:
            return []

        # Mark as ended
        await pool.execute("UPDATE giveaways SET ended=TRUE WHERE id=$1", giveaway_id)

        # Fetch entries
        entries = await pool.fetch(
            "SELECT user_id FROM giveaway_entries WHERE giveaway_id=$1", giveaway_id
        )
        entry_ids = [e["user_id"] for e in entries]

        guild   = self.bot.get_guild(row["guild_id"])
        if not guild:
            return []

        # Filter valid members
        valid = []
        for uid in entry_ids:
            member = guild.get_member(uid)
            if member and not member.bot:
                valid.append(member)

        # Pick winners
        count   = min(row["winner_count"], len(valid))
        winners = random.sample(valid, count) if valid else []
        winner_ids = [w.id for w in winners]

        # Save winners
        await pool.execute(
            "UPDATE giveaways SET winner_ids=$1 WHERE id=$2",
            winner_ids, giveaway_id,
        )

        # Update the giveaway message
        channel = guild.get_channel(row["channel_id"])
        if channel and row["message_id"]:
            try:
                message = await channel.fetch_message(row["message_id"])
                host    = guild.get_member(row["host_id"]) or await self.bot.fetch_user(row["host_id"])

                ended_embed = giveaway_embed(
                    prize=row["prize"],
                    host=host,
                    winner_count=row["winner_count"],
                    ends_at=row["ends_at"],
                    ended=True,
                    winners=winners,
                )

                # Disable the button
                view = GiveawayView()
                view.enter.disabled = True
                view.enter.label    = "Giveaway Ended"
                view.enter.style    = discord.ButtonStyle.secondary
                await message.edit(embed=ended_embed, view=view)

                # Announce winners
                if winners:
                    winner_mentions = " ".join(w.mention for w in winners)
                    await channel.send(
                        f"🎉 Congratulations {winner_mentions}! You won **{row['prize']}**!\n"
                        f"Hosted by <@{row['host_id']}>."
                    )
                else:
                    await channel.send(
                        f"😔 The giveaway for **{row['prize']}** ended with no valid entrants."
                    )
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass

        return winner_ids

    # ── /giveaway group ───────────────────────────────────────────────────────
    giveaway_group = app_commands.Group(name="giveaway", description="Giveaway commands.")

    # ── /giveaway start ───────────────────────────────────────────────────────
    @giveaway_group.command(name="start", description="Start a giveaway.")
    @app_commands.describe(
        duration="Duration e.g. 1h, 30m, 2d, 1h30m",
        prize="What are you giving away?",
        winners="Number of winners (default 1)",
        channel="Channel to post in (defaults to current)",
        required_role="Role required to enter (optional)",
    )
    @is_admin()
    async def giveaway_start(
        self,
        interaction: discord.Interaction,
        duration: str,
        prize: str,
        winners: app_commands.Range[int, 1, 20] = 1,
        channel: discord.TextChannel | None = None,
        required_role: discord.Role | None = None,
    ):
        seconds = parse_duration(duration)
        if not seconds or seconds < 10:
            return await interaction.response.send_message(
                embed=error("Invalid Duration", "Use formats like `30m`, `1h`, `2d`, `1h30m`. Minimum 10 seconds."),
                ephemeral=True,
            )
        if seconds > 86400 * 30:
            return await interaction.response.send_message(
                embed=error("Too Long", "Maximum giveaway duration is 30 days."), ephemeral=True
            )

        target  = channel or interaction.channel
        ends_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=seconds)

        # Insert to DB first (without message_id)
        pool = get_pool()
        giveaway_id = await pool.fetchval(
            """INSERT INTO giveaways (guild_id, channel_id, host_id, prize, winner_count, required_role_id, ends_at)
               VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id""",
            interaction.guild_id, target.id, interaction.user.id,
            prize, winners, required_role.id if required_role else None, ends_at,
        )

        embed = giveaway_embed(
            prize=prize,
            host=interaction.user,
            winner_count=winners,
            ends_at=ends_at,
            required_role=required_role,
        )

        view = GiveawayView()
        msg  = await target.send(embed=embed, view=view)

        # Save message_id
        await pool.execute("UPDATE giveaways SET message_id=$1 WHERE id=$2", msg.id, giveaway_id)

        # Create entries table if not exists (safety)
        await pool.execute("""
            CREATE TABLE IF NOT EXISTS giveaway_entries (
                giveaway_id BIGINT NOT NULL,
                user_id     BIGINT NOT NULL,
                PRIMARY KEY (giveaway_id, user_id)
            )
        """)

        await interaction.response.send_message(
            embed=success(
                "Giveaway Started!",
                f"Giveaway for **{prize}** posted in {target.mention}.\n"
                f"**Duration:** {format_duration(seconds)}\n"
                f"**Winners:** {winners}\n"
                f"**ID:** `#{giveaway_id}`"
            ),
            ephemeral=True,
        )

    # ── /giveaway end ─────────────────────────────────────────────────────────
    @giveaway_group.command(name="end", description="End a giveaway early.")
    @app_commands.describe(giveaway_id="The giveaway ID (from /giveaway list)")
    @is_admin()
    async def giveaway_end(self, interaction: discord.Interaction, giveaway_id: int):
        pool = get_pool()
        row  = await pool.fetchrow(
            "SELECT * FROM giveaways WHERE id=$1 AND guild_id=$2", giveaway_id, interaction.guild_id
        )
        if not row:
            return await interaction.response.send_message(
                embed=error("Not Found", f"No giveaway with ID `#{giveaway_id}` found."), ephemeral=True
            )
        if row["ended"]:
            return await interaction.response.send_message(
                embed=error("Already Ended", "This giveaway has already ended."), ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)
        winner_ids = await self._end_giveaway(giveaway_id)

        if winner_ids:
            mentions = " ".join(f"<@{uid}>" for uid in winner_ids)
            await interaction.followup.send(
                embed=success("Giveaway Ended", f"Winners: {mentions}"), ephemeral=True
            )
        else:
            await interaction.followup.send(
                embed=info("Giveaway Ended", "No valid entrants — no winners drawn."), ephemeral=True
            )

    # ── /giveaway reroll ──────────────────────────────────────────────────────
    @giveaway_group.command(name="reroll", description="Reroll winners for an ended giveaway.")
    @app_commands.describe(giveaway_id="The giveaway ID", count="Number of new winners to pick")
    @is_admin()
    async def giveaway_reroll(
        self,
        interaction: discord.Interaction,
        giveaway_id: int,
        count: app_commands.Range[int, 1, 20] = 1,
    ):
        pool = get_pool()
        row  = await pool.fetchrow(
            "SELECT * FROM giveaways WHERE id=$1 AND guild_id=$2", giveaway_id, interaction.guild_id
        )
        if not row:
            return await interaction.response.send_message(
                embed=error("Not Found", f"No giveaway with ID `#{giveaway_id}` found."), ephemeral=True
            )
        if not row["ended"]:
            return await interaction.response.send_message(
                embed=error("Not Ended", "End the giveaway first before rerolling."), ephemeral=True
            )

        entries = await pool.fetch(
            "SELECT user_id FROM giveaway_entries WHERE giveaway_id=$1", giveaway_id
        )
        valid = [
            m for e in entries
            if (m := interaction.guild.get_member(e["user_id"])) and not m.bot
        ]

        if not valid:
            return await interaction.response.send_message(
                embed=error("No Entrants", "No valid entrants to reroll from."), ephemeral=True
            )

        new_winners = random.sample(valid, min(count, len(valid)))
        mentions    = " ".join(w.mention for w in new_winners)

        # Announce in original channel
        channel = interaction.guild.get_channel(row["channel_id"])
        if channel:
            await channel.send(
                f"🎉 **Reroll!** New winner(s) for **{row['prize']}**: {mentions}! Congratulations!"
            )

        await interaction.response.send_message(
            embed=success("Rerolled!", f"New winner(s): {mentions}"), ephemeral=True
        )

    # ── /giveaway list ────────────────────────────────────────────────────────
    @giveaway_group.command(name="list", description="List active giveaways in this server.")
    async def giveaway_list(self, interaction: discord.Interaction):
        pool = get_pool()
        rows = await pool.fetch(
            "SELECT * FROM giveaways WHERE guild_id=$1 AND ended=FALSE ORDER BY ends_at ASC",
            interaction.guild_id,
        )
        if not rows:
            return await interaction.response.send_message(
                embed=info("No Active Giveaways", "There are no active giveaways right now."), ephemeral=True
            )

        embed = discord.Embed(title="🎉 Active Giveaways", color=config.BOT_COLOR)
        for row in rows[:10]:
            entries = await pool.fetchval(
                "SELECT COUNT(*) FROM giveaway_entries WHERE giveaway_id=$1", row["id"]
            )
            embed.add_field(
                name=f"#{row['id']} — {row['prize']}",
                value=(
                    f"**Ends:** {discord.utils.format_dt(row['ends_at'], 'R')}\n"
                    f"**Channel:** <#{row['channel_id']}>\n"
                    f"**Winners:** {row['winner_count']} • **Entries:** {entries}"
                ),
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /giveaway cancel ──────────────────────────────────────────────────────
    @giveaway_group.command(name="cancel", description="Cancel a giveaway without picking winners.")
    @app_commands.describe(giveaway_id="The giveaway ID to cancel")
    @is_admin()
    async def giveaway_cancel(self, interaction: discord.Interaction, giveaway_id: int):
        pool = get_pool()
        row  = await pool.fetchrow(
            "SELECT * FROM giveaways WHERE id=$1 AND guild_id=$2", giveaway_id, interaction.guild_id
        )
        if not row:
            return await interaction.response.send_message(
                embed=error("Not Found", f"No giveaway with ID `#{giveaway_id}` found."), ephemeral=True
            )
        if row["ended"]:
            return await interaction.response.send_message(
                embed=error("Already Ended", "This giveaway has already ended."), ephemeral=True
            )

        await pool.execute("UPDATE giveaways SET ended=TRUE WHERE id=$1", giveaway_id)

        # Edit the message to show cancelled
        channel = interaction.guild.get_channel(row["channel_id"])
        if channel and row["message_id"]:
            try:
                message = await channel.fetch_message(row["message_id"])
                embed   = discord.Embed(
                    title=f"🚫 {row['prize']} — Cancelled",
                    description="This giveaway was cancelled by a moderator.",
                    color=discord.Color.red(),
                )
                view         = GiveawayView()
                view.enter.disabled = True
                view.enter.label    = "Cancelled"
                view.enter.style    = discord.ButtonStyle.danger
                await message.edit(embed=embed, view=view)
            except (discord.NotFound, discord.Forbidden):
                pass

        await interaction.response.send_message(
            embed=success("Cancelled", f"Giveaway `#{giveaway_id}` for **{row['prize']}** has been cancelled."),
            ephemeral=True,
        )

    # ── Error handler ─────────────────────────────────────────────────────────
    async def cog_app_command_error(self, interaction: discord.Interaction, err: app_commands.AppCommandError):
        msg = "You need Administrator permission." if isinstance(err, app_commands.MissingPermissions) else f"`{err}`"
        if interaction.response.is_done():
            await interaction.followup.send(embed=error("Error", msg), ephemeral=True)
        else:
            await interaction.response.send_message(embed=error("Error", msg), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Giveaway(bot))
