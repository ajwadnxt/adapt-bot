import asyncio
import json
import logging
import os
import re
import discord
from discord import app_commands
from discord.ext import commands
from database import db
from utils.embeds import success, error, info
import config

log = logging.getLogger("bot")


# ── Persistent Views for Tickets ───────────────────────────────────────────

class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Open Ticket",
        style=discord.ButtonStyle.primary,
        emoji="📩",
        custom_id="open_ticket_btn",
    )
    async def open_ticket(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        cog = interaction.client.get_cog("Tickets")
        if cog:
            await cog.create_user_ticket(interaction)


class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Close Ticket",
        style=discord.ButtonStyle.danger,
        emoji="🔒",
        custom_id="close_ticket_btn",
    )
    async def close_ticket(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        cog = interaction.client.get_cog("Tickets")
        if cog:
            await cog.close_user_ticket(interaction)


# ── Tickets Cog Class ──────────────────────────────────────────────────────

class Tickets(commands.Cog):
    """Modern ticket support system with local database fallback."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.json_file = "database/tickets.json"
        self._local_tickets = {}
        self._local_settings = {}

        if not os.path.exists("database"):
            os.makedirs("database")
        self._load_local_tickets()

    async def cog_load(self):
        # Register persistent views so buttons work after bot restarts
        self.bot.add_view(TicketPanelView())
        self.bot.add_view(TicketCloseView())

    # ── Database & Local Fallback Methods ─────────────────────────────────────

    def _load_local_tickets(self):
        if os.path.exists(self.json_file):
            try:
                with open(self.json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self._local_tickets = data.get("tickets", {})
                        self._local_settings = data.get("settings", {})
                    else:
                        self._local_tickets = {}
                        self._local_settings = {}
            except Exception:
                self._local_tickets = {}
                self._local_settings = {}
        else:
            self._local_tickets = {}
            self._local_settings = {}

    def _save_local_tickets(self):
        try:
            with open(self.json_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "tickets": self._local_tickets,
                        "settings": self._local_settings,
                    },
                    f,
                    indent=4,
                    ensure_ascii=False,
                )
        except Exception as e:
            log.error(f"Failed to save local tickets: {e}")

    async def get_user_open_ticket(self, guild_id: int, user_id: int):
        if db._pool is not None:
            try:
                return await db.get_user_open_ticket(guild_id, user_id)
            except Exception:
                pass
        # Fallback JSON
        guild_key = str(guild_id)
        if guild_key in self._local_tickets:
            for ch_id, ticket in self._local_tickets[guild_key].items():
                if ticket["user_id"] == user_id and ticket["status"] == "open":
                    return {
                        "channel_id": int(ch_id),
                        "user_id": user_id,
                        "status": "open",
                    }
        return None

    async def add_ticket(self, guild_id: int, channel_id: int, user_id: int):
        if db._pool is not None:
            try:
                await db.create_ticket(guild_id, channel_id, user_id)
                return
            except Exception:
                pass
        # Fallback JSON
        guild_key = str(guild_id)
        if guild_key not in self._local_tickets:
            self._local_tickets[guild_key] = {}
        self._local_tickets[guild_key][str(channel_id)] = {
            "user_id": user_id,
            "status": "open",
            "created_at": discord.utils.utcnow().isoformat(),
        }
        self._save_local_tickets()

    async def close_ticket_db(self, guild_id: int, channel_id: int):
        if db._pool is not None:
            try:
                await db.close_ticket(channel_id)
                return
            except Exception:
                pass
        # Fallback JSON
        guild_key = str(guild_id)
        if (
            guild_key in self._local_tickets
            and str(channel_id) in self._local_tickets[guild_key]
        ):
            self._local_tickets[guild_key][str(channel_id)]["status"] = "closed"
            self._local_tickets[guild_key][str(channel_id)][
                "closed_at"
            ] = discord.utils.utcnow().isoformat()
            self._save_local_tickets()

    async def get_settings(self, guild_id: int):
        cfg = await db.ensure_guild(guild_id)
        if db._pool is not None:
            return cfg
        # Fallback JSON
        guild_key = str(guild_id)
        local_cfg = self._local_settings.get(guild_key, {})
        return {
            "ticket_category_id": local_cfg.get("ticket_category_id"),
            "ticket_support_role_id": local_cfg.get("ticket_support_role_id"),
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
        self._save_local_tickets()

    # ── Support Ticket Logical Flows ──────────────────────────────────────────

    async def create_user_ticket(self, interaction: discord.Interaction):
        guild = interaction.guild
        user = interaction.user

        await interaction.response.defer(ephemeral=True)

        existing = await self.get_user_open_ticket(guild.id, user.id)
        if existing:
            channel = guild.get_channel(existing["channel_id"])
            if channel:
                await interaction.followup.send(
                    embed=error(
                        "Ticket Already Open",
                        f"You already have an open support ticket: {channel.mention}",
                    ),
                    ephemeral=True,
                )
                return

        cfg = await self.get_settings(guild.id)
        category_id = cfg.get("ticket_category_id")
        support_role_id = cfg.get("ticket_support_role_id")

        category = guild.get_channel(category_id) if category_id else None
        support_role = guild.get_role(support_role_id) if support_role_id else None

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
                manage_permissions=True,
            ),
        }

        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
            )

        # Build clean channel name
        channel_name = f"ticket-{user.name}"
        channel_name = re.sub(r"[^a-zA-Z0-9-]", "", channel_name).lower()
        if not channel_name:
            channel_name = f"ticket-{user.id}"

        try:
            ticket_channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                reason=f"Support ticket created by {user}",
            )
        except discord.Forbidden:
            await interaction.followup.send(
                embed=error(
                    "Permission Denied",
                    "The bot lacks permission to create channels in this server.",
                ),
                ephemeral=True,
            )
            return
        except Exception as e:
            await interaction.followup.send(
                embed=error("Error", f"Failed to create ticket channel: {e}"),
                ephemeral=True,
            )
            return

        await self.add_ticket(guild.id, ticket_channel.id, user.id)

        embed = discord.Embed(
            title=f"🎫 Support Ticket - {user.display_name}",
            description=(
                f"Welcome {user.mention}!\n\n"
                "Please describe your issue or question here in detail. "
                "Our support staff will assist you shortly.\n\n"
                "To close this ticket, click the **Close Ticket** button below."
            ),
            color=config.BOT_COLOR,
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text=f"Ticket ID: {ticket_channel.id}")

        mention_str = (
            f"{user.mention} | {support_role.mention}"
            if support_role
            else f"{user.mention} | @here"
        )
        await ticket_channel.send(
            content=mention_str, embed=embed, view=TicketCloseView()
        )

        await interaction.followup.send(
            embed=success(
                "Ticket Created",
                f"Your support ticket has been created: {ticket_channel.mention}",
            ),
            ephemeral=True,
        )

    async def close_user_ticket(self, interaction: discord.Interaction):
        channel = interaction.channel
        guild = interaction.guild

        await interaction.response.defer()
        await self.close_ticket_db(guild.id, channel.id)

        # Retrieve ticket opener
        opener_id = None
        if db._pool is not None:
            try:
                ticket_info = await db.get_ticket(channel.id)
                if ticket_info:
                    opener_id = ticket_info["user_id"]
            except Exception:
                pass
        else:
            guild_key = str(guild.id)
            if (
                guild_key in self._local_tickets
                and str(channel.id) in self._local_tickets[guild_key]
            ):
                opener_id = self._local_tickets[guild_key][str(channel.id)]["user_id"]

        opener = guild.get_member(opener_id) if opener_id else None
        closer = interaction.user

        # 1. Lock the channel by removing viewing permissions from the opener
        if opener:
            try:
                await channel.set_permissions(
                    opener, view_channel=False, reason="Ticket closed"
                )
            except discord.Forbidden:
                pass

        # Send closing confirmation in the channel
        embed = discord.Embed(
            title="🔒 Ticket Closed",
            description=(
                f"This support ticket was closed by **{closer.mention}**.\n\n"
                "Generating transcript and sending logs to DMs...\n"
                "This channel will be deleted in **10 seconds**."
            ),
            color=discord.Color.orange(),
        )
        await interaction.followup.send(embed=embed)

        # 2. Generate Transcript
        transcript_lines = []
        try:
            async for msg in channel.history(limit=1000, oldest_first=True):
                timestamp = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
                attachments_str = ""
                if msg.attachments:
                    attachments_str = f" [Attachments: {', '.join(a.url for a in msg.attachments)}]"
                
                content_str = msg.clean_content
                transcript_lines.append(
                    f"[{timestamp}] {msg.author} ({msg.author.id}): {content_str}{attachments_str}"
                )
        except Exception as e:
            log.error(f"Failed to compile message history for transcript: {e}")
            transcript_lines.append(f"[Error generating transcript: {e}]")

        transcript_text = "\n".join(transcript_lines)
        file_path = f"database/transcript-{channel.name}.txt"
        
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(f"--- Support Ticket Transcript for #{channel.name} ---\n")
                f.write(f"Server: {guild.name} (ID: {guild.id})\n")
                f.write(f"Opened By: {opener if opener else f'User ID {opener_id}'}\n")
                f.write(f"Closed By: {closer} (ID: {closer.id})\n")
                f.write(f"Total Messages: {len(transcript_lines)}\n")
                f.write("-" * 50 + "\n\n")
                f.write(transcript_text)
        except Exception as e:
            log.error(f"Failed to write transcript file: {e}")
            file_path = None

        # 3. DM Both Users
        dm_embed = discord.Embed(
            title="🎫 Support Ticket Log",
            description=f"Your support ticket in **{guild.name}** has been closed.",
            color=config.BOT_COLOR,
            timestamp=discord.utils.utcnow()
        )
        dm_embed.add_field(name="Ticket Channel", value=f"`#{channel.name}`", inline=True)
        dm_embed.add_field(name="Opened By", value=opener.mention if opener else f"User ID {opener_id}", inline=True)
        dm_embed.add_field(name="Closed By", value=closer.mention, inline=True)

        users_to_dm = []
        if opener and not opener.bot:
            users_to_dm.append(opener)
        if closer and not closer.bot and (not opener or closer.id != opener.id):
            users_to_dm.append(closer)

        for u in users_to_dm:
            try:
                if file_path and os.path.exists(file_path):
                    await u.send(embed=dm_embed, file=discord.File(file_path))
                else:
                    await u.send(embed=dm_embed)
            except discord.Forbidden:
                log.info(f"Failed to DM ticket log to {u} (DMs closed)")
            except Exception as e:
                log.error(f"Error sending DM ticket log to {u}: {e}")

        # 4. Clean up transcript file
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                log.error(f"Failed to delete temp transcript file: {e}")

        # 5. Send Audit Log
        cfg = await db.ensure_guild(guild.id)
        log_channel_id = cfg.get("mod_log_channel_id") or cfg.get("log_channel_id")
        if not log_channel_id and db._pool is None:
            guild_key = str(guild.id)
            local_cfg = self._local_settings.get(guild_key, {})
            log_channel_id = local_cfg.get("mod_log_channel_id") or local_cfg.get(
                "log_channel_id"
            )

        if log_channel_id:
            log_channel = guild.get_channel(log_channel_id)
            if log_channel:
                log_embed = discord.Embed(
                    title="🎫 Support Ticket Closed",
                    description=(
                        f"**Ticket Channel:** `#{channel.name}` (ID: {channel.id})\n"
                        f"**Closed By:** {closer.mention} ({closer})\n"
                        f"**Opener:** {opener.mention if opener else f'<@{opener_id}>' if opener_id else 'Unknown'}"
                    ),
                    color=discord.Color.red(),
                    timestamp=discord.utils.utcnow(),
                )
                try:
                    await log_channel.send(embed=log_embed)
                except discord.Forbidden:
                    pass

        async def delete_after_delay():
            await asyncio.sleep(10)
            try:
                await channel.delete(reason="Ticket channel closed and deleted.")
            except discord.NotFound:
                pass
            except discord.Forbidden:
                log.error(
                    f"Failed to delete ticket channel {channel.name}: Missing Permissions"
                )

        self.bot.loop.create_task(delete_after_delay())

    # ── Ticket Command Group (/ticket) ─────────────────────────────────────────

    ticket_group = app_commands.Group(
        name="ticket", description="Manage the support ticket system."
    )

    @ticket_group.command(
        name="setup", description="Spawn a support ticket creation panel."
    )
    @app_commands.describe(
        title="Custom title for the panel embed",
        description="Custom description for the panel embed",
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    async def ticket_setup(
        self,
        interaction: discord.Interaction,
        title: str = "🎟️ Open a Support Ticket",
        description: str = "Need assistance? Click the button below to open a private support ticket and chat with our staff team!",
    ):
        embed = discord.Embed(title=title, description=description, color=config.BOT_COLOR)
        embed.set_footer(text="Please open only one support ticket at a time.")

        await interaction.response.send_message(
            embed=success(
                "Ticket System", "Ticket setup panel spawned successfully!"
            ),
            ephemeral=True,
        )
        await interaction.channel.send(embed=embed, view=TicketPanelView())

    @ticket_group.command(
        name="role",
        description="Set the support role allowed to access ticket channels.",
    )
    @app_commands.describe(role="The staff role that can view and answer tickets")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def ticket_role(self, interaction: discord.Interaction, role: discord.Role):
        await self.save_setting(interaction.guild_id, ticket_support_role_id=role.id)
        await interaction.response.send_message(
            embed=success(
                "Setting Updated", f"Support role has been set to {role.mention}."
            ),
            ephemeral=True,
        )

    @ticket_group.command(
        name="category",
        description="Set the category where new tickets are created.",
    )
    @app_commands.describe(category="The category channel where tickets should be placed")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def ticket_category(
        self, interaction: discord.Interaction, category: discord.CategoryChannel
    ):
        await self.save_setting(interaction.guild_id, ticket_category_id=category.id)
        await interaction.response.send_message(
            embed=success(
                "Setting Updated",
                f"Ticket category has been set to **{category.name}**.",
            ),
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
