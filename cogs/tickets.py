import datetime
import discord
from discord import app_commands
from discord.ext import commands
from database import db
from utils.checks import is_admin, is_mod
from utils.embeds import success, error, info
import config


# ── Close Ticket View ─────────────────────────────────────────────────────────

class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # Persistent across restarts

    @discord.ui.button(label="Close Ticket", emoji="🔒", style=discord.ButtonStyle.red, custom_id="ticket:close")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = await db.get_ticket(interaction.channel_id)
        if not ticket:
            return await interaction.response.send_message(embed=error("Not a ticket channel."), ephemeral=True)

        # Check permissions — ticket owner or support role or mod
        cfg = await db.get_guild(interaction.guild_id)
        is_support = False
        if cfg and cfg["ticket_support_role_id"]:
            support_role = interaction.guild.get_role(cfg["ticket_support_role_id"])
            if support_role and support_role in interaction.user.roles:
                is_support = True

        if (interaction.user.id != ticket["user_id"]
                and not is_support
                and not interaction.user.guild_permissions.manage_channels):
            return await interaction.response.send_message(
                embed=error("No Permission", "Only the ticket creator or support can close this."), ephemeral=True
            )

        await interaction.response.send_message(embed=info("Closing ticket in 5 seconds..."))
        await db.close_ticket(interaction.channel_id)

        # Log closure
        if cfg and cfg["ticket_log_channel_id"]:
            log_ch = interaction.guild.get_channel(cfg["ticket_log_channel_id"])
            if log_ch:
                embed = discord.Embed(title="🎫 Ticket Closed", color=discord.Color.red())
                embed.add_field(name="Channel",  value=interaction.channel.name)
                embed.add_field(name="Opened by", value=f"<@{ticket['user_id']}>")
                embed.add_field(name="Closed by", value=interaction.user.mention)
                embed.add_field(name="Topic",     value=ticket["topic"] or "None", inline=False)
                embed.timestamp = datetime.datetime.utcnow()
                await log_ch.send(embed=embed)

        await discord.utils.sleep_until(
            datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=5)
        )
        try:
            await interaction.channel.delete(reason=f"Ticket closed by {interaction.user}")
        except discord.Forbidden:
            pass

    @discord.ui.button(label="Claim", emoji="🙋", style=discord.ButtonStyle.green, custom_id="ticket:claim")
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = await db.get_guild(interaction.guild_id)
        is_support = False
        if cfg and cfg["ticket_support_role_id"]:
            role = interaction.guild.get_role(cfg["ticket_support_role_id"])
            if role and role in interaction.user.roles:
                is_support = True

        if not is_support and not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message(
                embed=error("No Permission", "Only support staff can claim tickets."), ephemeral=True
            )

        await interaction.response.send_message(
            embed=success("Ticket Claimed", f"{interaction.user.mention} has claimed this ticket.")
        )
        button.disabled = True
        await interaction.message.edit(view=self)


# ── Create Ticket Button ──────────────────────────────────────────────────────

class CreateTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # Persistent

    @discord.ui.button(label="Create Ticket", emoji="🎫", style=discord.ButtonStyle.blurple, custom_id="ticket:create")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        cfg = await db.ensure_guild(interaction.guild_id)

        if not cfg["ticket_enabled"]:
            return await interaction.followup.send(embed=error("Tickets are disabled."), ephemeral=True)

        # Check for existing open ticket
        existing = await db.get_user_open_ticket(interaction.guild_id, interaction.user.id)
        if existing:
            ch = interaction.guild.get_channel(existing["channel_id"])
            if ch:
                return await interaction.followup.send(
                    embed=error("Already Open", f"You already have an open ticket: {ch.mention}"), ephemeral=True
                )

        # Get category
        category = None
        if cfg["ticket_category_id"]:
            category = interaction.guild.get_channel(cfg["ticket_category_id"])

        # Build permission overwrites
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        if cfg["ticket_support_role_id"]:
            support_role = interaction.guild.get_role(cfg["ticket_support_role_id"])
            if support_role:
                overwrites[support_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        # Create channel
        try:
            channel = await interaction.guild.create_text_channel(
                name=f"ticket-{interaction.user.name}",
                category=category,
                overwrites=overwrites,
                reason=f"Ticket created by {interaction.user}",
            )
        except discord.Forbidden:
            return await interaction.followup.send(
                embed=error("Missing Permissions", "I don't have permission to create channels."), ephemeral=True
            )

        ticket_id = await db.create_ticket(interaction.guild_id, channel.id, interaction.user.id)

        # Send welcome embed in ticket channel
        embed = discord.Embed(
            title=f"🎫 Ticket #{ticket_id}",
            description=cfg["ticket_message"],
            color=config.BOT_COLOR,
        )
        embed.add_field(name="Opened by", value=interaction.user.mention)
        embed.set_footer(text="Click 🔒 to close this ticket.")
        await channel.send(
            content=interaction.user.mention,
            embed=embed,
            view=TicketControlView(),
        )

        # Log ticket creation
        if cfg["ticket_log_channel_id"]:
            log_ch = interaction.guild.get_channel(cfg["ticket_log_channel_id"])
            if log_ch:
                log_embed = discord.Embed(title="🎫 Ticket Opened", color=discord.Color.green())
                log_embed.add_field(name="Channel",  value=channel.mention)
                log_embed.add_field(name="Opened by", value=interaction.user.mention)
                log_embed.timestamp = datetime.datetime.utcnow()
                await log_ch.send(embed=log_embed)

        await interaction.followup.send(
            embed=success("Ticket Created", f"Your ticket has been created: {channel.mention}"),
            ephemeral=True,
        )


# ── Topic Modal ───────────────────────────────────────────────────────────────

class TicketTopicModal(discord.ui.Modal, title="Create a Ticket"):
    topic = discord.ui.TextInput(
        label="What do you need help with?",
        style=discord.TextStyle.paragraph,
        placeholder="Describe your issue briefly...",
        max_length=200,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        # Reuse CreateTicketView logic but with topic stored
        cfg = await db.ensure_guild(interaction.guild_id)
        if not cfg["ticket_enabled"]:
            return await interaction.followup.send(embed=error("Tickets are disabled."), ephemeral=True)

        existing = await db.get_user_open_ticket(interaction.guild_id, interaction.user.id)
        if existing:
            ch = interaction.guild.get_channel(existing["channel_id"])
            if ch:
                return await interaction.followup.send(
                    embed=error("Already Open", f"You already have an open ticket: {ch.mention}"), ephemeral=True
                )

        category = interaction.guild.get_channel(cfg["ticket_category_id"]) if cfg["ticket_category_id"] else None
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        if cfg["ticket_support_role_id"]:
            role = interaction.guild.get_role(cfg["ticket_support_role_id"])
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        try:
            channel = await interaction.guild.create_text_channel(
                name=f"ticket-{interaction.user.name}",
                category=category,
                overwrites=overwrites,
                reason=f"Ticket by {interaction.user}",
            )
        except discord.Forbidden:
            return await interaction.followup.send(embed=error("Missing Permissions"), ephemeral=True)

        ticket_id = await db.create_ticket(interaction.guild_id, channel.id, interaction.user.id, topic=self.topic.value)

        embed = discord.Embed(
            title=f"🎫 Ticket #{ticket_id}",
            description=cfg["ticket_message"],
            color=config.BOT_COLOR,
        )
        embed.add_field(name="Opened by", value=interaction.user.mention)
        embed.add_field(name="Topic",     value=self.topic.value, inline=False)
        embed.set_footer(text="Click 🔒 to close this ticket.")
        await channel.send(content=interaction.user.mention, embed=embed, view=TicketControlView())

        await interaction.followup.send(
            embed=success("Ticket Created", f"Your ticket: {channel.mention}"), ephemeral=True
        )


# ── Cog ───────────────────────────────────────────────────────────────────────

class Tickets(commands.Cog):
    """Ticket system with persistent buttons."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Register persistent views so buttons work after restart
        bot.add_view(CreateTicketView())
        bot.add_view(TicketControlView())

    # ── /ticket panel ─────────────────────────────────────────────────────────
    ticket_group = app_commands.Group(name="ticket", description="Ticket system commands.")

    @ticket_group.command(name="panel", description="Send the ticket creation panel.")
    @app_commands.describe(channel="Channel to send the panel to", title="Panel title", description="Panel description")
    @is_admin()
    async def ticket_panel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        title: str = "🎫 Support Tickets",
        description: str = "Click the button below to open a support ticket.",
    ):
        cfg = await db.get_guild(interaction.guild_id)
        if not cfg or not cfg["ticket_enabled"]:
            return await interaction.response.send_message(
                embed=error("Tickets Disabled", "Enable tickets first with `/set tickets true`."), ephemeral=True
            )

        embed = discord.Embed(title=title, description=description, color=config.BOT_COLOR)
        embed.set_footer(text="One ticket per user.")
        await channel.send(embed=embed, view=CreateTicketView())
        await interaction.response.send_message(
            embed=success("Panel Sent", f"Ticket panel sent to {channel.mention}."), ephemeral=True
        )

    # ── /ticket panel_with_topic ───────────────────────────────────────────────
    @ticket_group.command(name="panel_topic", description="Send a ticket panel that asks for a topic.")
    @app_commands.describe(channel="Channel to send the panel to")
    @is_admin()
    async def ticket_panel_topic(self, interaction: discord.Interaction, channel: discord.TextChannel):
        cfg = await db.get_guild(interaction.guild_id)
        if not cfg or not cfg["ticket_enabled"]:
            return await interaction.response.send_message(
                embed=error("Tickets Disabled", "Enable tickets first with `/set tickets true`."), ephemeral=True
            )

        class TopicButtonView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=None)

            @discord.ui.button(label="Create Ticket", emoji="🎫", style=discord.ButtonStyle.blurple, custom_id="ticket:create_topic")
            async def open_modal(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                await btn_interaction.response.send_modal(TicketTopicModal())

        embed = discord.Embed(
            title="🎫 Support Tickets",
            description="Click below and describe your issue to open a ticket.",
            color=config.BOT_COLOR,
        )
        await channel.send(embed=embed, view=TopicButtonView())
        await interaction.response.send_message(
            embed=success("Panel Sent", f"Topic panel sent to {channel.mention}."), ephemeral=True
        )

    # ── /ticket close ─────────────────────────────────────────────────────────
    @ticket_group.command(name="close", description="Close the current ticket.")
    @is_mod()
    async def ticket_close(self, interaction: discord.Interaction):
        ticket = await db.get_ticket(interaction.channel_id)
        if not ticket or ticket["status"] == "closed":
            return await interaction.response.send_message(
                embed=error("Not a Ticket", "Run this inside a ticket channel."), ephemeral=True
            )

        await interaction.response.send_message(embed=info("Closing ticket in 5 seconds..."))
        await db.close_ticket(interaction.channel_id)

        await discord.utils.sleep_until(
            datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=5)
        )
        try:
            await interaction.channel.delete(reason=f"Ticket closed by {interaction.user}")
        except discord.Forbidden:
            pass

    # ── /ticket add ───────────────────────────────────────────────────────────
    @ticket_group.command(name="add", description="Add a member to the current ticket.")
    @app_commands.describe(member="Member to add")
    @is_mod()
    async def ticket_add(self, interaction: discord.Interaction, member: discord.Member):
        ticket = await db.get_ticket(interaction.channel_id)
        if not ticket:
            return await interaction.response.send_message(
                embed=error("Not a Ticket", "Run this inside a ticket channel."), ephemeral=True
            )

        await interaction.channel.set_permissions(
            member,
            view_channel=True,
            send_messages=True,
            read_message_history=True,
        )
        await interaction.response.send_message(
            embed=success("Member Added", f"{member.mention} has been added to this ticket.")
        )

    # ── /ticket remove ────────────────────────────────────────────────────────
    @ticket_group.command(name="remove", description="Remove a member from the current ticket.")
    @app_commands.describe(member="Member to remove")
    @is_mod()
    async def ticket_remove(self, interaction: discord.Interaction, member: discord.Member):
        ticket = await db.get_ticket(interaction.channel_id)
        if not ticket:
            return await interaction.response.send_message(
                embed=error("Not a Ticket", "Run this inside a ticket channel."), ephemeral=True
            )

        await interaction.channel.set_permissions(member, overwrite=None)
        await interaction.response.send_message(
            embed=success("Member Removed", f"{member.mention} has been removed from this ticket.")
        )

    # ── Error handler ─────────────────────────────────────────────────────────
    async def cog_app_command_error(self, interaction: discord.Interaction, err: app_commands.AppCommandError):
        msg = "You don't have permission." if isinstance(err, app_commands.MissingPermissions) else f"`{err}`"
        if interaction.response.is_done():
            await interaction.followup.send(embed=error("Error", msg), ephemeral=True)
        else:
            await interaction.response.send_message(embed=error("Error", msg), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
