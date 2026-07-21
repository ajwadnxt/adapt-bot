import discord
from discord import app_commands
from discord.ext import commands, tasks
from database.db import get_pool
from utils.checks import is_admin
from utils.embeds import success, error, info
import config


STAT_TYPES = {
    "members":  {"default": "👥 Members: {value}",  "description": "Total member count"},
    "humans":   {"default": "🧑 Humans: {value}",   "description": "Non-bot member count"},
    "bots":     {"default": "🤖 Bots: {value}",     "description": "Bot count"},
    "channels": {"default": "📢 Channels: {value}", "description": "Total channel count"},
    "roles":    {"default": "🎭 Roles: {value}",    "description": "Total role count"},
    "online":   {"default": "🟢 Online: {value}",   "description": "Online member count"},
    "boosts":   {"default": "✨ Boosts: {value}",   "description": "Server boost count"},
}


def get_stat_value(guild: discord.Guild, stat_type: str) -> int:
    if stat_type == "members":  return guild.member_count
    if stat_type == "humans":   return sum(1 for m in guild.members if not m.bot)
    if stat_type == "bots":     return sum(1 for m in guild.members if m.bot)
    if stat_type == "channels": return len(guild.channels)
    if stat_type == "roles":    return len(guild.roles)
    if stat_type == "online":   return sum(1 for m in guild.members if m.status != discord.Status.offline)
    if stat_type == "boosts":   return guild.premium_subscription_count
    return 0


class Stats(commands.Cog):
    """Auto-updating server stats voice channels."""

    def __init__(self, bot: commands.Bot):
        self.bot  = bot
        self.update_stats.start()

    def cog_unload(self):
        self.update_stats.cancel()

    # ── Background task ───────────────────────────────────────────────────────
    @tasks.loop(minutes=10)
    async def update_stats(self):
        pool = get_pool()
        rows = await pool.fetch("SELECT * FROM stat_channels")
        for row in rows:
            guild = self.bot.get_guild(row["guild_id"])
            if not guild:
                continue
            channel = guild.get_channel(row["channel_id"])
            if not isinstance(channel, discord.VoiceChannel):
                continue
            value    = get_stat_value(guild, row["type"])
            template = row["custom_name"] or STAT_TYPES.get(row["type"], {}).get("default", "{value}")
            name     = template.replace("{value}", str(value))
            try:
                await channel.edit(name=name, reason="Stats update")
            except (discord.Forbidden, discord.HTTPException):
                pass

    @update_stats.before_loop
    async def before_update(self):
        await self.bot.wait_until_ready()

    # ── Listeners for instant update on join/leave ────────────────────────────
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await self._update_guild(member.guild, ["members", "humans", "bots", "online"])

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        await self._update_guild(member.guild, ["members", "humans", "bots"])

    async def _update_guild(self, guild: discord.Guild, types: list[str]):
        pool = get_pool()
        rows = await pool.fetch(
            "SELECT * FROM stat_channels WHERE guild_id=$1 AND type=ANY($2)",
            guild.id, types,
        )
        for row in rows:
            channel = guild.get_channel(row["channel_id"])
            if not isinstance(channel, discord.VoiceChannel):
                continue
            value    = get_stat_value(guild, row["type"])
            template = row["custom_name"] or STAT_TYPES.get(row["type"], {}).get("default", "{value}")
            name     = template.replace("{value}", str(value))
            try:
                await channel.edit(name=name, reason="Stats update")
            except (discord.Forbidden, discord.HTTPException):
                pass

    # ── /stats group ──────────────────────────────────────────────────────────
    stats_group = app_commands.Group(name="stats", description="Server stats channel commands.")

    @stats_group.command(name="add", description="Add a stats channel.")
    @app_commands.describe(
        stat_type="Type of stat to display",
        channel="Voice channel to use",
        custom_name="Custom name template — use {value} for the number",
    )
    @app_commands.choices(stat_type=[
        app_commands.Choice(name=v["description"], value=k)
        for k, v in STAT_TYPES.items()
    ])
    @is_admin()
    async def stats_add(
        self,
        interaction: discord.Interaction,
        stat_type: str,
        channel: discord.VoiceChannel,
        custom_name: str | None = None,
    ):
        pool = get_pool()
        await pool.execute(
            """INSERT INTO stat_channels (guild_id, type, channel_id, custom_name)
               VALUES ($1,$2,$3,$4)
               ON CONFLICT (guild_id, type) DO UPDATE
               SET channel_id=$3, custom_name=$4""",
            interaction.guild_id, stat_type, channel.id, custom_name,
        )

        # Immediately update the channel
        value    = get_stat_value(interaction.guild, stat_type)
        template = custom_name or STAT_TYPES[stat_type]["default"]
        name     = template.replace("{value}", str(value))
        try:
            await channel.edit(name=name)
        except discord.Forbidden:
            pass

        await interaction.response.send_message(
            embed=success(
                "Stats Channel Added",
                f"{channel.mention} will now show **{STAT_TYPES[stat_type]['description']}**.\n"
                f"Updates every 10 minutes."
            ),
            ephemeral=True,
        )

    @stats_group.command(name="remove", description="Remove a stats channel.")
    @app_commands.choices(stat_type=[
        app_commands.Choice(name=v["description"], value=k)
        for k, v in STAT_TYPES.items()
    ])
    @is_admin()
    async def stats_remove(self, interaction: discord.Interaction, stat_type: str):
        pool = get_pool()
        result = await pool.execute(
            "DELETE FROM stat_channels WHERE guild_id=$1 AND type=$2",
            interaction.guild_id, stat_type,
        )
        if result == "DELETE 0":
            return await interaction.response.send_message(
                embed=error("Not Found", f"No stats channel set for **{stat_type}**."), ephemeral=True
            )
        await interaction.response.send_message(
            embed=success("Removed", f"Stats channel for **{stat_type}** removed."), ephemeral=True
        )

    @stats_group.command(name="list", description="List all stats channels in this server.")
    @is_admin()
    async def stats_list(self, interaction: discord.Interaction):
        pool = get_pool()
        rows = await pool.fetch("SELECT * FROM stat_channels WHERE guild_id=$1", interaction.guild_id)
        if not rows:
            return await interaction.response.send_message(
                embed=info("No Stats Channels", "Add one with `/stats add`."), ephemeral=True
            )

        embed = discord.Embed(title="📊 Stats Channels", color=config.BOT_COLOR)
        for row in rows:
            channel = interaction.guild.get_channel(row["channel_id"])
            ch_name = channel.mention if channel else "`deleted`"
            template = row["custom_name"] or STAT_TYPES.get(row["type"], {}).get("default", "{value}")
            embed.add_field(
                name=STAT_TYPES.get(row["type"], {}).get("description", row["type"]),
                value=f"{ch_name}\n`{template}`",
                inline=True,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @stats_group.command(name="refresh", description="Force refresh all stats channels now.")
    @is_admin()
    async def stats_refresh(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        pool = get_pool()
        rows = await pool.fetch("SELECT * FROM stat_channels WHERE guild_id=$1", interaction.guild_id)
        updated = 0
        for row in rows:
            channel = interaction.guild.get_channel(row["channel_id"])
            if not isinstance(channel, discord.VoiceChannel):
                continue
            value    = get_stat_value(interaction.guild, row["type"])
            template = row["custom_name"] or STAT_TYPES.get(row["type"], {}).get("default", "{value}")
            name     = template.replace("{value}", str(value))
            try:
                await channel.edit(name=name)
                updated += 1
            except (discord.Forbidden, discord.HTTPException):
                pass
        await interaction.followup.send(
            embed=success("Refreshed", f"Updated **{updated}** stats channel(s)."), ephemeral=True
        )

    async def cog_app_command_error(self, interaction: discord.Interaction, err: app_commands.AppCommandError):
        msg = "You need Administrator permission." if isinstance(err, app_commands.MissingPermissions) else f"`{err}`"
        if interaction.response.is_done():
            await interaction.followup.send(embed=error("Error", msg), ephemeral=True)
        else:
            await interaction.response.send_message(embed=error("Error", msg), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Stats(bot))
