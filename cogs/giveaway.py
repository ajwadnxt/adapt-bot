import asyncio
import datetime
import json
import logging
import os
import random
import re
import discord
from discord import app_commands
from discord.ext import commands, tasks
from database import db
from utils.embeds import success, error, info
from utils.paginator import Paginator
import config

log = logging.getLogger("bot")


# ── Duration Parser Utility ───────────────────────────────────────────────────

def parse_duration(duration_str: str) -> int | None:
    """Parse a duration string (e.g. 1d 2h 30m) into total seconds.
    Returns None if the format is invalid.
    """
    clean = duration_str.strip().lower()
    units = {"d": 86400, "h": 3600, "m": 60, "s": 1}
    total_seconds = 0
    pattern = re.compile(r"(\d+)([dhms])")
    matches = pattern.findall(clean)
    if not matches:
        return None

    # Rebuild input string to check if the whole string matched correctly
    rebuilt = "".join(f"{num}{unit}" for num, unit in matches)
    if clean.replace(" ", "") != rebuilt:
        return None

    for num, unit in matches:
        total_seconds += int(num) * units[unit]
    return total_seconds


# ── Persistent Views for Giveaways ───────────────────────────────────────────

class GiveawayJoinButton(discord.ui.Button):
    def __init__(self, emoji_str: str = "🎉"):
        btn_emoji = None
        btn_label = "Join 🎉"
        if emoji_str:
            try:
                if ":" in emoji_str:
                    btn_emoji = discord.PartialEmoji.from_str(emoji_str.strip())
                    btn_label = "Join"
                else:
                    btn_emoji = emoji_str.strip()
                    btn_label = f"Join {emoji_str.strip()}"
            except Exception:
                btn_emoji = "🎉"
                btn_label = "Join 🎉"

        super().__init__(
            label=btn_label,
            emoji=btn_emoji,
            style=discord.ButtonStyle.primary,
            custom_id="giveaway_join_btn",
        )

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("Giveaway")
        if not cog:
            await interaction.response.send_message(
                embed=error("Giveaways", "Giveaway module is not loaded currently."),
                ephemeral=True,
            )
            return

        msg_id = interaction.message.id
        user_id = interaction.user.id

        # Get the current giveaway
        giveaway = await cog.get_giveaway(msg_id)
        if not giveaway:
            await interaction.response.send_message(
                embed=error("Giveaways", "This giveaway could not be found in the database."),
                ephemeral=True,
            )
            return

        if giveaway["status"] != "active":
            await interaction.response.send_message(
                embed=error("Giveaways", "This giveaway has already ended or been cancelled."),
                ephemeral=True,
            )
            return

        participants = list(giveaway["participants"] or [])
        if user_id in participants:
            # Leave the giveaway
            await cog.remove_participant(msg_id, user_id)
            # Re-fetch updated info
            giveaway = await cog.get_giveaway(msg_id)
            participants = list(giveaway["participants"] or [])

            # Update message embed count
            embed = interaction.message.embeds[0]
            embed.set_field_at(0, name="Entries", value=f"👥 **{len(participants)}**", inline=True)
            await interaction.message.edit(embed=embed)

            await interaction.response.send_message(
                "❌ You have left the giveaway. Your entry has been removed.",
                ephemeral=True,
            )
        else:
            # Join the giveaway
            await cog.add_participant(msg_id, user_id)
            # Re-fetch updated info
            giveaway = await cog.get_giveaway(msg_id)
            participants = list(giveaway["participants"] or [])

            # Update message embed count
            embed = interaction.message.embeds[0]
            embed.set_field_at(0, name="Entries", value=f"👥 **{len(participants)}**", inline=True)
            await interaction.message.edit(embed=embed)

            await interaction.response.send_message(
                "🎉 You have entered the giveaway! Good luck!",
                ephemeral=True,
            )


class GiveawayView(discord.ui.View):
    def __init__(self, emoji_str: str = "🎉"):
        super().__init__(timeout=None)
        self.add_item(GiveawayJoinButton(emoji_str))


# ── Giveaway Cog Class ────────────────────────────────────────────────────────

class Giveaway(commands.Cog):
    """Host and manage giveaways with dynamic buttons and countdowns."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.json_file = "database/giveaways.json"
        self._local_giveaways = {}
        self._local_settings = {}

        if not os.path.exists("database"):
            os.makedirs("database")
        self._load_local_giveaways()

    async def cog_load(self):
        # Register persistent view default fallback
        self.bot.add_view(GiveawayView("🎉"))
        self.check_giveaways.start()

    def cog_unload(self):
        self.check_giveaways.cancel()

    # ── Database & Fallback Methods ──────────────────────────────────────────

    def _load_local_giveaways(self):
        if os.path.exists(self.json_file):
            try:
                with open(self.json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self._local_giveaways = data.get("giveaways", {})
                        self._local_settings = data.get("settings", {})
                    else:
                        self._local_giveaways = {}
                        self._local_settings = {}
            except Exception:
                self._local_giveaways = {}
                self._local_settings = {}
        else:
            self._local_giveaways = {}
            self._local_settings = {}

    def _save_local_giveaways(self):
        try:
            with open(self.json_file, "w", encoding="utf-8") as f:
                json.dump({
                    "giveaways": self._local_giveaways,
                    "settings": self._local_settings
                }, f, indent=4, ensure_ascii=False)
        except Exception as e:
            log.error(f"Failed to save local giveaways: {e}")

    async def get_settings(self, guild_id: int) -> dict:
        if db._pool is not None:
            try:
                cfg = await db.get_guild(guild_id)
                if cfg:
                    res = dict(cfg)
                    return {
                        "giveaway_emoji": res.get("giveaway_emoji", "🎉"),
                        "giveaway_color": res.get("giveaway_color", config.BOT_COLOR),
                        "giveaway_ping_role_id": res.get("giveaway_ping_role_id"),
                        "giveaway_pin": res.get("giveaway_pin", False),
                    }
            except Exception:
                pass
        # Fallback JSON
        guild_key = str(guild_id)
        local_cfg = self._local_settings.get(guild_key, {})
        return {
            "giveaway_emoji": local_cfg.get("giveaway_emoji", "🎉"),
            "giveaway_color": local_cfg.get("giveaway_color", config.BOT_COLOR),
            "giveaway_ping_role_id": local_cfg.get("giveaway_ping_role_id"),
            "giveaway_pin": local_cfg.get("giveaway_pin", False),
        }

    async def save_setting(self, guild_id: int, **kwargs):
        if db._pool is not None:
            try:
                await db.set_guild(guild_id, **kwargs)
                return
            except Exception:
                pass
        # Fallback JSON
        guild_key = str(guild_id)
        if guild_key not in self._local_settings:
            self._local_settings[guild_key] = {}
        self._local_settings[guild_key].update(kwargs)
        self._save_local_giveaways()

    async def get_giveaway(self, message_id: int) -> dict | None:
        if db._pool is not None:
            try:
                record = await db.get_giveaway(message_id)
                if record:
                    return dict(record)
            except Exception as e:
                log.error(f"Postgres get_giveaway failed: {e}")
        # Fallback JSON
        g_key = str(message_id)
        if g_key in self._local_giveaways:
            return self._local_giveaways[g_key]
        return None

    async def get_active_giveaways(self) -> list[dict]:
        if db._pool is not None:
            try:
                records = await db.get_active_giveaways()
                return [dict(r) for r in records]
            except Exception as e:
                log.error(f"Postgres get_active_giveaways failed: {e}")
        # Fallback JSON
        active = []
        for g in self._local_giveaways.values():
            if g["status"] == "active":
                active.append(g)
        return active

    async def get_guild_giveaways(self, guild_id: int) -> list[dict]:
        if db._pool is not None:
            try:
                records = await db.get_guild_giveaways(guild_id)
                return [dict(r) for r in records]
            except Exception as e:
                log.error(f"Postgres get_guild_giveaways failed: {e}")
        # Fallback JSON
        guild_list = []
        for g in self._local_giveaways.values():
            if g["guild_id"] == guild_id:
                guild_list.append(g)
        guild_list.sort(key=lambda x: x["end_time"], reverse=True)
        return guild_list

    async def save_giveaway(
        self,
        guild_id: int,
        channel_id: int,
        message_id: int,
        prize: str,
        description: str | None,
        winners_count: int,
        end_time: datetime.datetime,
        host_id: int,
    ):
        end_time_iso = end_time.isoformat()
        if db._pool is not None:
            try:
                await db.create_giveaway(
                    guild_id,
                    channel_id,
                    message_id,
                    prize,
                    description,
                    winners_count,
                    end_time,
                    host_id,
                )
                return
            except Exception as e:
                log.error(f"Postgres create_giveaway failed: {e}")
        # Fallback JSON
        self._local_giveaways[str(message_id)] = {
            "guild_id": guild_id,
            "channel_id": channel_id,
            "message_id": message_id,
            "prize": prize,
            "description": description,
            "winners_count": winners_count,
            "end_time": end_time_iso,
            "host_id": host_id,
            "participants": [],
            "winners": [],
            "status": "active",
        }
        self._save_local_giveaways()

    async def update_giveaway(self, message_id: int, **kwargs):
        if "end_time" in kwargs and isinstance(kwargs["end_time"], datetime.datetime):
            end_time_db = kwargs["end_time"]
            end_time_json = kwargs["end_time"].isoformat()
        else:
            end_time_db = kwargs.get("end_time")
            end_time_json = kwargs.get("end_time")

        if db._pool is not None:
            try:
                db_kwargs = kwargs.copy()
                if end_time_db is not None:
                    db_kwargs["end_time"] = end_time_db
                await db.update_giveaway(message_id, **db_kwargs)
                return
            except Exception as e:
                log.error(f"Postgres update_giveaway failed: {e}")
        # Fallback JSON
        g_key = str(message_id)
        if g_key in self._local_giveaways:
            for k, v in kwargs.items():
                if k == "end_time" and end_time_json is not None:
                    self._local_giveaways[g_key][k] = end_time_json
                else:
                    self._local_giveaways[g_key][k] = v
            self._save_local_giveaways()

    async def add_participant(self, message_id: int, user_id: int):
        if db._pool is not None:
            try:
                await db.add_giveaway_participant(message_id, user_id)
                return
            except Exception as e:
                log.error(f"Postgres add_giveaway_participant failed: {e}")
        # Fallback JSON
        g_key = str(message_id)
        if g_key in self._local_giveaways:
            parts = self._local_giveaways[g_key].get("participants", [])
            if user_id not in parts:
                parts.append(user_id)
                self._local_giveaways[g_key]["participants"] = parts
                self._save_local_giveaways()

    async def remove_participant(self, message_id: int, user_id: int):
        if db._pool is not None:
            try:
                await db.remove_giveaway_participant(message_id, user_id)
                return
            except Exception as e:
                log.error(f"Postgres remove_giveaway_participant failed: {e}")
        # Fallback JSON
        g_key = str(message_id)
        if g_key in self._local_giveaways:
            parts = self._local_giveaways[g_key].get("participants", [])
            if user_id in parts:
                parts.remove(user_id)
                self._local_giveaways[g_key]["participants"] = parts
                self._save_local_giveaways()

    # ── Background Task Loop ──────────────────────────────────────────────────

    @tasks.loop(seconds=10)
    async def check_giveaways(self):
        now = discord.utils.utcnow()
        active_giveaways = await self.get_active_giveaways()

        for g in active_giveaways:
            end_time = g["end_time"]
            if isinstance(end_time, str):
                end_time = datetime.datetime.fromisoformat(end_time)

            if end_time <= now:
                try:
                    await self.end_giveaway(g)
                except Exception as e:
                    log.error(f"Error ending giveaway {g['message_id']}: {e}")

    @check_giveaways.before_loop
    async def before_check_giveaways(self):
        await self.bot.wait_until_ready()

    async def end_giveaway(self, g: dict):
        guild = self.bot.get_guild(g["guild_id"])
        if not guild:
            await self.update_giveaway(g["message_id"], status="ended")
            return

        channel = guild.get_channel(g["channel_id"])
        if not channel:
            await self.update_giveaway(g["message_id"], status="ended")
            return

        try:
            message = await channel.fetch_message(g["message_id"])
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            await self.update_giveaway(g["message_id"], status="ended")
            return

        participants = list(g["participants"] or [])
        winners_count = g["winners_count"]

        # Ensure participants are valid members (not bots and still in the guild)
        valid_participants = []
        for uid in participants:
            member = guild.get_member(uid)
            if not member:
                try:
                    member = await guild.fetch_member(uid)
                except Exception:
                    member = None
            if member and not member.bot:
                valid_participants.append(member)

        # Draw winners
        winners = []
        if valid_participants:
            draw_count = min(len(valid_participants), winners_count)
            winners = random.sample(valid_participants, draw_count)

        winner_ids = [w.id for w in winners]
        await self.update_giveaway(g["message_id"], status="ended", winners=winner_ids)

        # Re-build Ended Embed
        embed = discord.Embed(
            title="🎁 GIVEAWAY ENDED 🎁",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow(),
        )
        desc = f"**Prize:** {g['prize']}\n"
        if g["description"]:
            desc += f"{g['description']}\n"
        desc += f"**Hosted By:** <@{g['host_id']}>\n"
        embed.description = desc

        embed.add_field(name="Entries", value=f"👥 **{len(participants)}**", inline=True)

        if winners:
            winner_mentions = ", ".join(w.mention for w in winners)
            embed.add_field(name="Winners", value=f"🏆 {winner_mentions}", inline=True)
            announcement = f"🎉 Congratulations {winner_mentions}! You won **{g['prize']}**!"
        else:
            embed.add_field(name="Winners", value="🏆 No valid participants/winners.", inline=True)
            announcement = f"The giveaway for **{g['prize']}** ended, but no winners could be selected."

        # Edit original message with ended status and disabled button
        disabled_view = discord.ui.View(timeout=None)
        disabled_btn = discord.ui.Button(
            label="Join 🎉",
            style=discord.ButtonStyle.primary,
            custom_id="giveaway_join_btn",
            disabled=True,
        )
        disabled_view.add_item(disabled_btn)

        await message.edit(embed=embed, view=disabled_view)
        await channel.send(announcement)

        # DM winners
        for w in winners:
            try:
                dm_embed = discord.Embed(
                    title="🎉 You Won a Giveaway! 🎉",
                    description=(
                        f"Congratulations! You won the giveaway for **{g['prize']}** in **{guild.name}**!\n\n"
                        f"👉 **[Jump to Giveaway Message]({message.jump_url})**"
                    ),
                    color=config.BOT_COLOR,
                    timestamp=discord.utils.utcnow(),
                )
                await w.send(embed=dm_embed)
            except discord.Forbidden:
                pass

    # ── Slash Command Group (/giveaway) ───────────────────────────────────────

    giveaway_group = app_commands.Group(
        name="giveaway", description="Host and manage giveaways."
    )

    # ── /giveaway create
    @giveaway_group.command(
        name="create", description="Start a new giveaway."
    )
    @app_commands.describe(
        prize="The item being given away",
        duration="Length of time (e.g. 10m, 1h, 1d)",
        winners="Number of winners to select (default: 1)",
        channel="The channel to host the giveaway in (default: current)",
        description="Additional description for the giveaway embed",
        host="The member hosting the giveaway (default: you)",
        emoji="Custom button emoji (overrides server default)",
        color="Custom embed hex color (overrides server default)",
        ping="Whether to mention the default ping role (default: False)",
        ping_role="Specific role to mention (overrides default ping settings)",
        pin="Whether to pin the giveaway message (default: False)",
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def giveaway_create(
        self,
        interaction: discord.Interaction,
        prize: str,
        duration: str,
        winners: app_commands.Range[int, 1, 50] = 1,
        channel: discord.TextChannel | None = None,
        description: str | None = None,
        host: discord.Member | None = None,
        emoji: str | None = None,
        color: str | None = None,
        ping: bool = False,
        ping_role: discord.Role | None = None,
        pin: bool = False,
    ):
        target_channel = channel or interaction.channel
        giveaway_host = host or interaction.user

        duration_sec = parse_duration(duration)
        if duration_sec is None or duration_sec <= 0:
            await interaction.response.send_message(
                embed=error(
                    "Invalid Duration",
                    "Please specify a valid duration string. Examples: `10m`, `2h`, `1d3h`.",
                ),
                ephemeral=True,
            )
            return

        end_time = discord.utils.utcnow() + datetime.timedelta(seconds=duration_sec)

        # Get settings defaults
        g_cfg = await self.get_settings(interaction.guild_id)
        use_emoji = emoji or g_cfg.get("giveaway_emoji", "🎉")
        
        # Color parsing
        color_val = g_cfg.get("giveaway_color", config.BOT_COLOR)
        if color:
            clean_hex = color.replace("#", "").strip()
            try:
                color_val = int(clean_hex, 16)
            except ValueError:
                pass
        embed_color = discord.Color(color_val)

        # Build initial embed
        embed = discord.Embed(
            title=f"🎉 GIVEAWAY: {prize} 🎉",
            color=embed_color,
            timestamp=discord.utils.utcnow(),
        )
        desc = ""
        if description:
            desc += f"{description}\n\n"
        desc += (
            f"Click the **Join** button below to enter!\n\n"
            f"⌛ **Ends:** <t:{int(end_time.timestamp())}:F> (<t:{int(end_time.timestamp())}:R>)\n"
            f"👑 **Hosted By:** {giveaway_host.mention}"
        )
        embed.description = desc

        embed.add_field(name="Entries", value="👥 **0**", inline=True)
        embed.add_field(name="Winners Count", value=f"🏆 **{winners}**", inline=True)
        embed.set_footer(text="Join before the timer ends!")

        # Determine ping content
        ping_content = ""
        if ping_role:
            ping_content = ping_role.mention
        elif ping:
            role_id = g_cfg.get("giveaway_ping_role_id")
            if role_id:
                ping_content = f"<@&{role_id}>"

        # Send to channel
        try:
            view = GiveawayView(use_emoji)
            giveaway_msg = await target_channel.send(content=ping_content if ping_content else None, embed=embed, view=view)
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=error(
                    "Permission Denied",
                    f"The bot cannot send messages in {target_channel.mention}.",
                ),
                ephemeral=True,
            )
            return

        # Determine auto-pin
        should_pin = pin or g_cfg.get("giveaway_pin", False)
        if should_pin:
            try:
                await giveaway_msg.pin()
            except discord.Forbidden:
                pass

        # Save to database
        await self.save_giveaway(
            guild_id=interaction.guild_id,
            channel_id=target_channel.id,
            message_id=giveaway_msg.id,
            prize=prize,
            description=description,
            winners_count=winners,
            end_time=end_time,
            host_id=giveaway_host.id,
        )

        await interaction.response.send_message(
            embed=success(
                "Giveaway Created",
                f"Giveaway for **{prize}** has been started in {target_channel.mention}!",
            ),
            ephemeral=True,
        )

    # ── /giveaway announce
    @giveaway_group.command(
        name="announce", description="Announces an active giveaway in a specified channel."
    )
    @app_commands.describe(
        giveaway_id="The message ID of the giveaway",
        channel="The channel to send the announcement to",
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def giveaway_announce(
        self,
        interaction: discord.Interaction,
        giveaway_id: str,
        channel: discord.TextChannel,
    ):
        try:
            msg_id = int(giveaway_id)
        except ValueError:
            await interaction.response.send_message(
                embed=error("Invalid ID", "Please provide a valid numeric giveaway message ID."),
                ephemeral=True,
            )
            return

        giveaway = await self.get_giveaway(msg_id)
        if not giveaway or giveaway["status"] != "active":
            await interaction.response.send_message(
                embed=error("Not Found", "No active giveaway with that ID was found."),
                ephemeral=True,
            )
            return

        end_time = giveaway["end_time"]
        if isinstance(end_time, str):
            end_time = datetime.datetime.fromisoformat(end_time)

        jump_url = f"https://discord.com/channels/{giveaway['guild_id']}/{giveaway['channel_id']}/{giveaway['message_id']}"

        # Get settings defaults
        g_cfg = await self.get_settings(interaction.guild_id)
        color_val = g_cfg.get("giveaway_color", config.BOT_COLOR)
        embed_color = discord.Color(color_val)

        embed = discord.Embed(
            title="📣 Ongoing Giveaway! 📣",
            description=(
                f"A giveaway is currently running for **{giveaway['prize']}**!\n\n"
                f"👉 **[Click Here to Enter the Giveaway!]({jump_url})** 👈\n\n"
                f"Hosted By: <@{giveaway['host_id']}>\n"
                f"Ends in: <t:{int(end_time.timestamp())}:R>"
            ),
            color=embed_color,
            timestamp=discord.utils.utcnow(),
        )

        try:
            await channel.send(content="@everyone" if channel.permissions_for(interaction.guild.me).mention_everyone else None, embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=error("Permission Denied", f"The bot lacks permission to post in {channel.mention}."),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=success("Announced", f"Giveaway announcement sent to {channel.mention}!"),
            ephemeral=True,
        )

    # ── /giveaway cancel
    @giveaway_group.command(
        name="cancel", description="Cancels an active giveaway."
    )
    @app_commands.describe(giveaway_id="The message ID of the giveaway to cancel")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def giveaway_cancel(self, interaction: discord.Interaction, giveaway_id: str):
        try:
            msg_id = int(giveaway_id)
        except ValueError:
            await interaction.response.send_message(
                embed=error("Invalid ID", "Please provide a valid numeric giveaway message ID."),
                ephemeral=True,
            )
            return

        giveaway = await self.get_giveaway(msg_id)
        if not giveaway or giveaway["status"] != "active":
            await interaction.response.send_message(
                embed=error("Not Found", "No active giveaway with that ID was found."),
                ephemeral=True,
            )
            return

        await self.update_giveaway(msg_id, status="cancelled")

        # Edit original message to show cancelled status
        guild = self.bot.get_guild(giveaway["guild_id"])
        if guild:
            channel = guild.get_channel(giveaway["channel_id"])
            if channel:
                try:
                    message = await channel.fetch_message(giveaway["message_id"])
                    embed = discord.Embed(
                        title="❌ GIVEAWAY CANCELLED ❌",
                        description=f"The giveaway for **{giveaway['prize']}** was cancelled by a moderator.",
                        color=discord.Color.light_gray(),
                        timestamp=discord.utils.utcnow(),
                    )
                    disabled_view = discord.ui.View(timeout=None)
                    disabled_btn = discord.ui.Button(
                        label="Join 🎉",
                        style=discord.ButtonStyle.primary,
                        custom_id="giveaway_join_btn",
                        disabled=True,
                    )
                    disabled_view.add_item(disabled_btn)
                    await message.edit(embed=embed, view=disabled_view)
                    
                    # Unpin if pinned
                    if message.pinned:
                        try:
                            await message.unpin()
                        except Exception:
                            pass
                except Exception:
                    pass

        await interaction.response.send_message(
            embed=success("Giveaway Cancelled", f"The giveaway for **{giveaway['prize']}** has been cancelled."),
            ephemeral=True,
        )

    # ── /giveaway details
    @giveaway_group.command(
        name="details", description="View the details of a specific giveaway."
    )
    @app_commands.describe(giveaway_id="The message ID of the giveaway")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def giveaway_details(self, interaction: discord.Interaction, giveaway_id: str):
        try:
            msg_id = int(giveaway_id)
        except ValueError:
            await interaction.response.send_message(
                embed=error("Invalid ID", "Please provide a valid numeric giveaway message ID."),
                ephemeral=True,
            )
            return

        giveaway = await self.get_giveaway(msg_id)
        if not giveaway:
            await interaction.response.send_message(
                embed=error("Not Found", "No giveaway with that ID was found in the database."),
                ephemeral=True,
            )
            return

        end_time = giveaway["end_time"]
        if isinstance(end_time, str):
            end_time = datetime.datetime.fromisoformat(end_time)

        status_emoji = {
            "active": "🟢 Active",
            "ended": "🔴 Ended",
            "cancelled": "❌ Cancelled",
        }.get(giveaway["status"], "❓ Unknown")

        g_cfg = await self.get_settings(interaction.guild_id)
        color_val = g_cfg.get("giveaway_color", config.BOT_COLOR)
        embed_color = discord.Color(color_val)

        embed = discord.Embed(
            title=f"📋 Giveaway Details — ID: {msg_id}",
            color=embed_color,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Prize", value=giveaway["prize"], inline=True)
        embed.add_field(name="Status", value=status_emoji, inline=True)
        embed.add_field(name="Hosted By", value=f"<@{giveaway['host_id']}>", inline=True)
        embed.add_field(name="Channel", value=f"<#{giveaway['channel_id']}>", inline=True)
        embed.add_field(name="Winners Count", value=str(giveaway["winners_count"]), inline=True)
        embed.add_field(name="Entries Count", value=str(len(giveaway["participants"] or [])), inline=True)
        embed.add_field(name="Ends At", value=f"<t:{int(end_time.timestamp())}:F>", inline=False)

        if giveaway["status"] == "ended" and giveaway["winners"]:
            winner_mentions = ", ".join(f"<@{w}>" for w in giveaway["winners"])
            embed.add_field(name="Winners Selected", value=winner_mentions, inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /giveaway edit
    @giveaway_group.command(
        name="edit", description="Edit an existing active giveaway."
    )
    @app_commands.describe(
        giveaway_id="The message ID of the giveaway",
        prize="New prize for the giveaway",
        duration="New duration string (e.g. 10m, 1h, 1d) calculated from now",
        winners="New winners count",
        description="New description",
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def giveaway_edit(
        self,
        interaction: discord.Interaction,
        giveaway_id: str,
        prize: str | None = None,
        duration: str | None = None,
        winners: app_commands.Range[int, 1, 50] | None = None,
        description: str | None = None,
    ):
        try:
            msg_id = int(giveaway_id)
        except ValueError:
            await interaction.response.send_message(
                embed=error("Invalid ID", "Please provide a valid numeric giveaway message ID."),
                ephemeral=True,
            )
            return

        giveaway = await self.get_giveaway(msg_id)
        if not giveaway or giveaway["status"] != "active":
            await interaction.response.send_message(
                embed=error("Not Found", "No active giveaway with that ID was found."),
                ephemeral=True,
            )
            return

        updates = {}
        if prize is not None:
            updates["prize"] = prize
        if description is not None:
            updates["description"] = description
        if winners is not None:
            updates["winners_count"] = winners

        if duration is not None:
            sec = parse_duration(duration)
            if sec is None or sec <= 0:
                await interaction.response.send_message(
                    embed=error("Invalid Duration", "Please provide a valid duration string like `1h` or `1d`."),
                    ephemeral=True,
                )
                return
            new_end = discord.utils.utcnow() + datetime.timedelta(seconds=sec)
            updates["end_time"] = new_end

        await self.update_giveaway(msg_id, **updates)

        # Fetch latest state
        giveaway = await self.get_giveaway(msg_id)
        end_time = giveaway["end_time"]
        if isinstance(end_time, str):
            end_time = datetime.datetime.fromisoformat(end_time)

        # Edit original message embed
        guild = self.bot.get_guild(giveaway["guild_id"])
        if guild:
            channel = guild.get_channel(giveaway["channel_id"])
            if channel:
                try:
                    message = await channel.fetch_message(giveaway["message_id"])
                    embed = message.embeds[0]
                    embed.title = f"🎉 GIVEAWAY: {giveaway['prize']} 🎉"

                    desc = ""
                    if giveaway["description"]:
                        desc += f"{giveaway['description']}\n\n"
                    desc += (
                        f"Click the **Join** button below to enter!\n\n"
                        f"⌛ **Ends:** <t:{int(end_time.timestamp())}:F> (<t:{int(end_time.timestamp())}:R>)\n"
                        f"👑 **Hosted By:** <@{giveaway['host_id']}>"
                    )
                    embed.description = desc
                    embed.set_field_at(1, name="Winners Count", value=f"🏆 **{giveaway['winners_count']}**", inline=True)

                    await message.edit(embed=embed)
                except Exception as e:
                    log.error(f"Failed to edit giveaway message: {e}")

        await interaction.response.send_message(
            embed=success("Giveaway Edited", "Giveaway parameters have been updated successfully!"),
            ephemeral=True,
        )

    # ── /giveaway extend
    @giveaway_group.command(
        name="extend", description="Extends the duration of an ongoing giveaway."
    )
    @app_commands.describe(
        giveaway_id="The message ID of the giveaway",
        duration="Amount of time to add (e.g. 10m, 1h, 1d)",
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def giveaway_extend(self, interaction: discord.Interaction, giveaway_id: str, duration: str):
        try:
            msg_id = int(giveaway_id)
        except ValueError:
            await interaction.response.send_message(
                embed=error("Invalid ID", "Please provide a valid numeric giveaway message ID."),
                ephemeral=True,
            )
            return

        giveaway = await self.get_giveaway(msg_id)
        if not giveaway or giveaway["status"] != "active":
            await interaction.response.send_message(
                embed=error("Not Found", "No active giveaway with that ID was found."),
                ephemeral=True,
            )
            return

        sec_to_add = parse_duration(duration)
        if sec_to_add is None or sec_to_add <= 0:
            await interaction.response.send_message(
                embed=error("Invalid Duration", "Please provide a valid duration string to add (e.g. `30m` or `1h`)."),
                ephemeral=True,
            )
            return

        current_end = giveaway["end_time"]
        if isinstance(current_end, str):
            current_end = datetime.datetime.fromisoformat(current_end)

        new_end = current_end + datetime.timedelta(seconds=sec_to_add)
        await self.update_giveaway(msg_id, end_time=new_end)

        # Edit original message embed
        guild = self.bot.get_guild(giveaway["guild_id"])
        if guild:
            channel = guild.get_channel(giveaway["channel_id"])
            if channel:
                try:
                    message = await channel.fetch_message(giveaway["message_id"])
                    embed = message.embeds[0]

                    desc = ""
                    if giveaway["description"]:
                        desc += f"{giveaway['description']}\n\n"
                    desc += (
                        f"Click the **Join** button below to enter!\n\n"
                        f"⌛ **Ends:** <t:{int(new_end.timestamp())}:F> (<t:{int(new_end.timestamp())}:R>)\n"
                        f"👑 **Hosted By:** <@{giveaway['host_id']}>"
                    )
                    embed.description = desc
                    await message.edit(embed=embed)
                except Exception as e:
                    log.error(f"Failed to edit giveaway message during extension: {e}")

        await interaction.response.send_message(
            embed=success(
                "Giveaway Extended",
                f"The giveaway has been extended by **{duration}**.\n"
                f"New End Time: <t:{int(new_end.timestamp())}:F>",
            ),
            ephemeral=True,
        )

    # ── /giveaway list
    @giveaway_group.command(
        name="list", description="Lists all active giveaways in the server."
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def giveaway_list(self, interaction: discord.Interaction):
        all_giveaways = await self.get_guild_giveaways(interaction.guild_id)
        active_giveaways = [g for g in all_giveaways if g["status"] == "active"]

        if not active_giveaways:
            await interaction.response.send_message(
                embed=info("No Giveaways", "There are no active giveaways running on this server currently."),
                ephemeral=True,
            )
            return

        g_cfg = await self.get_settings(interaction.guild_id)
        color_val = g_cfg.get("giveaway_color", config.BOT_COLOR)
        embed_color = discord.Color(color_val)

        pages = []
        chunks = [active_giveaways[i : i + 10] for i in range(0, len(active_giveaways), 10)]

        for chunk in chunks:
            embed = discord.Embed(
                title="🎉 Active Server Giveaways 🎉",
                color=embed_color,
                timestamp=discord.utils.utcnow(),
            )
            lines = []
            for g in chunk:
                end_time = g["end_time"]
                if isinstance(end_time, str):
                    end_time = datetime.datetime.fromisoformat(end_time)

                jump_url = f"https://discord.com/channels/{g['guild_id']}/{g['channel_id']}/{g['message_id']}"
                lines.append(
                    f"🎁 **{g['prize']}**\n"
                    f"┕ ID: `{g['message_id']}` • Ends: <t:{int(end_time.timestamp())}:R>\n"
                    f"┕ [Jump to Message]({jump_url})\n"
                )
            embed.description = "\n".join(lines)
            pages.append(embed)

        if len(pages) == 1:
            await interaction.response.send_message(embed=pages[0], ephemeral=True)
        else:
            await interaction.response.send_message(
                embed=pages[0],
                view=Paginator(pages, interaction.user.id),
                ephemeral=True,
            )

    # ── /giveaway remove
    @giveaway_group.command(
        name="remove", description="Removes a participant from a giveaway."
    )
    @app_commands.describe(
        giveaway_id="The message ID of the giveaway",
        user="The member to remove from the entry pool",
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def giveaway_remove(
        self,
        interaction: discord.Interaction,
        giveaway_id: str,
        user: discord.Member,
    ):
        try:
            msg_id = int(giveaway_id)
        except ValueError:
            await interaction.response.send_message(
                embed=error("Invalid ID", "Please provide a valid numeric giveaway message ID."),
                ephemeral=True,
            )
            return

        giveaway = await self.get_giveaway(msg_id)
        if not giveaway or giveaway["status"] != "active":
            await interaction.response.send_message(
                embed=error("Not Found", "No active giveaway with that ID was found."),
                ephemeral=True,
            )
            return

        participants = list(giveaway["participants"] or [])
        if user.id not in participants:
            await interaction.response.send_message(
                embed=error("Not Entered", f"**{user.display_name}** is not in the entry pool for this giveaway."),
                ephemeral=True,
            )
            return

        await self.remove_participant(msg_id, user.id)

        # Update message embed count
        guild = self.bot.get_guild(giveaway["guild_id"])
        if guild:
            channel = guild.get_channel(giveaway["channel_id"])
            if channel:
                try:
                    message = await channel.fetch_message(giveaway["message_id"])
                    embed = message.embeds[0]
                    # Update entries count
                    embed.set_field_at(0, name="Entries", value=f"👥 **{len(participants) - 1}**", inline=True)
                    await message.edit(embed=embed)
                except Exception:
                    pass

        await interaction.response.send_message(
            embed=success("Removed User", f"Successfully removed **{user.mention}** from the giveaway."),
            ephemeral=True,
        )

    # ── /giveaway reroll
    @giveaway_group.command(
        name="reroll", description="Rerolls the winners of an ended giveaway."
    )
    @app_commands.describe(
        giveaway_id="The message ID of the giveaway to reroll",
        winners_count="How many new winners to draw (defaults to original count)",
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def giveaway_reroll(
        self,
        interaction: discord.Interaction,
        giveaway_id: str,
        winners_count: int | None = None,
    ):
        try:
            msg_id = int(giveaway_id)
        except ValueError:
            await interaction.response.send_message(
                embed=error("Invalid ID", "Please provide a valid numeric giveaway message ID."),
                ephemeral=True,
            )
            return

        giveaway = await self.get_giveaway(msg_id)
        if not giveaway:
            await interaction.response.send_message(
                embed=error("Not Found", "No giveaway with that ID was found in the database."),
                ephemeral=True,
            )
            return

        if giveaway["status"] != "ended":
            await interaction.response.send_message(
                embed=error("Not Ended", "You can only reroll ended giveaways."),
                ephemeral=True,
            )
            return

        participants = list(giveaway["participants"] or [])
        draw_count = winners_count or giveaway["winners_count"]

        guild = interaction.guild
        valid_participants = []
        for uid in participants:
            member = guild.get_member(uid)
            if not member:
                try:
                    member = await guild.fetch_member(uid)
                except Exception:
                    member = None
            if member and not member.bot:
                valid_participants.append(member)

        if not valid_participants:
            await interaction.response.send_message(
                embed=error("No Entries", "There are no valid participants to draw winners from."),
                ephemeral=True,
            )
            return

        actual_draw = min(len(valid_participants), draw_count)
        winners = random.sample(valid_participants, actual_draw)
        winner_ids = [w.id for w in winners]

        # Save new winners to DB
        await self.update_giveaway(msg_id, winners=winner_ids)

        winner_mentions = ", ".join(w.mention for w in winners)
        channel = guild.get_channel(giveaway["channel_id"])

        if channel:
            # Edit original message embed
            try:
                message = await channel.fetch_message(giveaway["message_id"])
                embed = message.embeds[0]

                # Update the Winners field
                embed.set_field_at(1, name="Winners (Rerolled)", value=f"🏆 {winner_mentions}", inline=True)
                await message.edit(embed=embed)
            except Exception as e:
                log.error(f"Failed to edit giveaway embed during reroll: {e}")

            # Send announcement in channel
            await channel.send(f"🎉 **Giveaway Reroll:** New winner(s) for **{giveaway['prize']}**: {winner_mentions}!")

        await interaction.response.send_message(
            embed=success("Rerolled Winners", f"Successfully drew new winner(s): {winner_mentions}"),
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Giveaway(bot))
