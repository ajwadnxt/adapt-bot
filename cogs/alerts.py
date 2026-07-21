import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks
from database.db import get_pool
from utils.checks import is_admin
from utils.embeds import success, error, info
import config
import logging

log = logging.getLogger("alerts")


class Alerts(commands.Cog):
    """Twitch live alerts and YouTube new video notifications."""

    def __init__(self, bot: commands.Bot):
        self.bot     = bot
        self.session: aiohttp.ClientSession | None = None
        self.check_twitch.start()
        self.check_youtube.start()

    async def cog_load(self):
        self.session = aiohttp.ClientSession()

    def cog_unload(self):
        self.check_twitch.cancel()
        self.check_youtube.cancel()
        if self.session:
            self.bot.loop.create_task(self.session.close())

    # ── Twitch ────────────────────────────────────────────────────────────────

    async def _get_twitch_token(self) -> str | None:
        client_id     = config.TWITCH_CLIENT_ID
        client_secret = config.TWITCH_CLIENT_SECRET
        if not client_id or not client_secret:
            return None
        try:
            async with self.session.post(
                "https://id.twitch.tv/oauth2/token",
                params={"client_id": client_id, "client_secret": client_secret, "grant_type": "client_credentials"},
            ) as resp:
                data = await resp.json()
                return data.get("access_token")
        except Exception as e:
            log.error(f"Twitch token error: {e}")
            return None

    async def _get_twitch_stream(self, username: str, token: str) -> dict | None:
        try:
            async with self.session.get(
                f"https://api.twitch.tv/helix/streams?user_login={username}",
                headers={"Client-ID": config.TWITCH_CLIENT_ID, "Authorization": f"Bearer {token}"},
            ) as resp:
                data = await resp.json()
                streams = data.get("data", [])
                return streams[0] if streams else None
        except Exception as e:
            log.error(f"Twitch stream check error: {e}")
            return None

    @tasks.loop(minutes=5)
    async def check_twitch(self):
        if not config.TWITCH_CLIENT_ID or not config.TWITCH_CLIENT_SECRET:
            return

        token = await self._get_twitch_token()
        if not token:
            return

        pool = get_pool()
        rows = await pool.fetch("SELECT * FROM twitch_alerts")

        for row in rows:
            stream = await self._get_twitch_stream(row["twitch_user"], token)
            stream_id = stream["id"] if stream else None

            if stream and stream_id != row["last_stream"]:
                # New stream detected
                await pool.execute(
                    "UPDATE twitch_alerts SET last_stream=$1 WHERE guild_id=$2 AND twitch_user=$3",
                    stream_id, row["guild_id"], row["twitch_user"],
                )
                guild   = self.bot.get_guild(row["guild_id"])
                channel = guild.get_channel(row["channel_id"]) if guild else None
                if channel:
                    embed = discord.Embed(
                        title=f"🔴 {row['twitch_user']} is now LIVE!",
                        description=stream.get("title", "No title"),
                        url=f"https://twitch.tv/{row['twitch_user']}",
                        color=0x9146FF,
                    )
                    embed.add_field(name="Game",    value=stream.get("game_name", "Unknown"))
                    embed.add_field(name="Viewers", value=f"`{stream.get('viewer_count', 0):,}`")
                    embed.set_image(url=stream.get("thumbnail_url", "").replace("{width}", "1280").replace("{height}", "720"))
                    embed.set_footer(text="Twitch")
                    try:
                        await channel.send(
                            content=f"🔴 **{row['twitch_user']}** is live! https://twitch.tv/{row['twitch_user']}",
                            embed=embed,
                        )
                    except (discord.Forbidden, discord.HTTPException):
                        pass

            elif not stream and row["last_stream"]:
                # Stream ended — reset
                await pool.execute(
                    "UPDATE twitch_alerts SET last_stream=NULL WHERE guild_id=$1 AND twitch_user=$2",
                    row["guild_id"], row["twitch_user"],
                )

    @check_twitch.before_loop
    async def before_twitch(self):
        await self.bot.wait_until_ready()

    # ── YouTube ───────────────────────────────────────────────────────────────

    async def _get_latest_video(self, channel_id: str) -> tuple[str, str, str] | None:
        """Fetch latest video via RSS feed. Returns (video_id, title, url) or None."""
        try:
            url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
            async with self.session.get(url) as resp:
                if resp.status != 200:
                    return None
                text = await resp.text()

            # Simple XML parse — find first video entry
            import re
            video_id = re.search(r"<yt:videoId>(.*?)</yt:videoId>", text)
            title    = re.search(r"<title>(.*?)</title>",            text)
            if not video_id or not title:
                return None

            vid  = video_id.group(1)
            name = title.group(1)
            return vid, name, f"https://www.youtube.com/watch?v={vid}"
        except Exception as e:
            log.error(f"YouTube RSS error: {e}")
            return None

    @tasks.loop(minutes=15)
    async def check_youtube(self):
        pool = get_pool()
        rows = await pool.fetch("SELECT * FROM youtube_alerts")

        for row in rows:
            result = await self._get_latest_video(row["yt_channel_id"])
            if not result:
                continue

            video_id, title, url = result
            if video_id == row["last_video"]:
                continue

            # New video detected
            await pool.execute(
                "UPDATE youtube_alerts SET last_video=$1 WHERE guild_id=$2 AND yt_channel_id=$3",
                video_id, row["guild_id"], row["yt_channel_id"],
            )
            guild   = self.bot.get_guild(row["guild_id"])
            channel = guild.get_channel(row["channel_id"]) if guild else None
            if channel:
                embed = discord.Embed(
                    title=f"📺 New YouTube Video!",
                    description=f"**{title}**",
                    url=url,
                    color=0xFF0000,
                )
                embed.add_field(name="Watch Now", value=f"[Click here]({url})")
                embed.set_footer(text="YouTube")
                try:
                    await channel.send(
                        content=f"📺 New video uploaded! {url}",
                        embed=embed,
                    )
                except (discord.Forbidden, discord.HTTPException):
                    pass

    @check_youtube.before_loop
    async def before_youtube(self):
        await self.bot.wait_until_ready()

    # ── /alert group ──────────────────────────────────────────────────────────
    alert_group = app_commands.Group(name="alert", description="Social alert commands.")

    # ── Twitch commands ───────────────────────────────────────────────────────
    @alert_group.command(name="twitch_add", description="Add a Twitch live alert.")
    @app_commands.describe(
        username="Twitch username to track",
        channel="Channel to send alerts to",
    )
    @is_admin()
    async def twitch_add(self, interaction: discord.Interaction, username: str, channel: discord.TextChannel):
        if not config.TWITCH_CLIENT_ID or not config.TWITCH_CLIENT_SECRET:
            return await interaction.response.send_message(
                embed=error(
                    "Twitch Not Configured",
                    "Set `TWITCH_CLIENT_ID` and `TWITCH_CLIENT_SECRET` in your environment variables.\n"
                    "Get them at [dev.twitch.tv](https://dev.twitch.tv/console/apps)."
                ),
                ephemeral=True,
            )

        pool = get_pool()
        await pool.execute(
            """INSERT INTO twitch_alerts (guild_id, channel_id, twitch_user)
               VALUES ($1,$2,$3)
               ON CONFLICT (guild_id, twitch_user) DO UPDATE SET channel_id=$2""",
            interaction.guild_id, channel.id, username.lower(),
        )
        await interaction.response.send_message(
            embed=success("Twitch Alert Added", f"Will notify {channel.mention} when **{username}** goes live."),
            ephemeral=True,
        )

    @alert_group.command(name="twitch_remove", description="Remove a Twitch live alert.")
    @app_commands.describe(username="Twitch username to remove")
    @is_admin()
    async def twitch_remove(self, interaction: discord.Interaction, username: str):
        pool   = get_pool()
        result = await pool.execute(
            "DELETE FROM twitch_alerts WHERE guild_id=$1 AND twitch_user=$2",
            interaction.guild_id, username.lower(),
        )
        if result == "DELETE 0":
            return await interaction.response.send_message(
                embed=error("Not Found", f"No Twitch alert for `{username}`."), ephemeral=True
            )
        await interaction.response.send_message(
            embed=success("Removed", f"Twitch alert for **{username}** removed."), ephemeral=True
        )

    @alert_group.command(name="twitch_list", description="List all Twitch alerts.")
    @is_admin()
    async def twitch_list(self, interaction: discord.Interaction):
        pool = get_pool()
        rows = await pool.fetch("SELECT * FROM twitch_alerts WHERE guild_id=$1", interaction.guild_id)
        if not rows:
            return await interaction.response.send_message(
                embed=info("No Alerts", "No Twitch alerts set up."), ephemeral=True
            )

        embed = discord.Embed(title="🟣 Twitch Alerts", color=0x9146FF)
        for row in rows:
            ch = interaction.guild.get_channel(row["channel_id"])
            embed.add_field(
                name=row["twitch_user"],
                value=f"→ {ch.mention if ch else '`deleted`'}",
                inline=True,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── YouTube commands ──────────────────────────────────────────────────────
    @alert_group.command(name="youtube_add", description="Add a YouTube new video alert.")
    @app_commands.describe(
        channel_id="YouTube channel ID (from the channel URL)",
        channel="Discord channel to send alerts to",
    )
    @is_admin()
    async def youtube_add(self, interaction: discord.Interaction, channel_id: str, channel: discord.TextChannel):
        # Verify channel exists via RSS
        result = await self._get_latest_video(channel_id)
        if not result:
            return await interaction.response.send_message(
                embed=error("Invalid Channel", f"Could not find a YouTube channel with ID `{channel_id}`.\nMake sure it's the channel ID, not the username."),
                ephemeral=True,
            )

        pool = get_pool()
        await pool.execute(
            """INSERT INTO youtube_alerts (guild_id, channel_id, yt_channel_id, last_video)
               VALUES ($1,$2,$3,$4)
               ON CONFLICT (guild_id, yt_channel_id) DO UPDATE SET channel_id=$2""",
            interaction.guild_id, channel.id, channel_id, result[0],
        )
        await interaction.response.send_message(
            embed=success("YouTube Alert Added", f"Will notify {channel.mention} when a new video is uploaded.\nLatest video: **{result[1]}**"),
            ephemeral=True,
        )

    @alert_group.command(name="youtube_remove", description="Remove a YouTube alert.")
    @app_commands.describe(channel_id="YouTube channel ID to remove")
    @is_admin()
    async def youtube_remove(self, interaction: discord.Interaction, channel_id: str):
        pool   = get_pool()
        result = await pool.execute(
            "DELETE FROM youtube_alerts WHERE guild_id=$1 AND yt_channel_id=$2",
            interaction.guild_id, channel_id,
        )
        if result == "DELETE 0":
            return await interaction.response.send_message(
                embed=error("Not Found", f"No YouTube alert for `{channel_id}`."), ephemeral=True
            )
        await interaction.response.send_message(
            embed=success("Removed", f"YouTube alert for `{channel_id}` removed."), ephemeral=True
        )

    @alert_group.command(name="youtube_list", description="List all YouTube alerts.")
    @is_admin()
    async def youtube_list(self, interaction: discord.Interaction):
        pool = get_pool()
        rows = await pool.fetch("SELECT * FROM youtube_alerts WHERE guild_id=$1", interaction.guild_id)
        if not rows:
            return await interaction.response.send_message(
                embed=info("No Alerts", "No YouTube alerts set up."), ephemeral=True
            )

        embed = discord.Embed(title="📺 YouTube Alerts", color=0xFF0000)
        for row in rows:
            ch = interaction.guild.get_channel(row["channel_id"])
            embed.add_field(
                name=f"`{row['yt_channel_id']}`",
                value=f"→ {ch.mention if ch else '`deleted`'}",
                inline=True,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def cog_app_command_error(self, interaction: discord.Interaction, err: app_commands.AppCommandError):
        msg = "You need Administrator permission." if isinstance(err, app_commands.MissingPermissions) else f"`{err}`"
        if interaction.response.is_done():
            await interaction.followup.send(embed=error("Error", msg), ephemeral=True)
        else:
            await interaction.response.send_message(embed=error("Error", msg), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Alerts(bot))
