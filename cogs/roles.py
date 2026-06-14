import discord
from discord import app_commands
from discord.ext import commands
from database import db
from utils.checks import is_admin
from utils.embeds import success, error, info
import config


# ── Reaction Role Button View ─────────────────────────────────────────────────

class RoleButton(discord.ui.Button):
    def __init__(self, role: discord.Role, emoji: str = None):
        super().__init__(
            label=role.name,
            emoji=emoji or None,
            style=discord.ButtonStyle.secondary,
            custom_id=f"role:{role.id}",
        )
        self.role_id = role.id

    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(self.role_id)
        if not role:
            return await interaction.response.send_message(
                embed=error("Role Not Found", "This role no longer exists."), ephemeral=True
            )

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role, reason="Role button toggle")
            await interaction.response.send_message(
                embed=error("Role Removed", f"Removed {role.mention} from you."), ephemeral=True
            )
        else:
            await interaction.user.add_roles(role, reason="Role button toggle")
            await interaction.response.send_message(
                embed=success("Role Added", f"Gave you {role.mention}!"), ephemeral=True
            )


class RoleButtonView(discord.ui.View):
    def __init__(self, roles: list[tuple[discord.Role, str]]):
        super().__init__(timeout=None)
        for role, emoji in roles:
            self.add_item(RoleButton(role, emoji))


# ── Cog ───────────────────────────────────────────────────────────────────────

class Roles(commands.Cog):
    """Reaction roles, button roles, and auto-roles."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        """Re-register all persistent role button views on startup."""
        # We can't restore exact views without knowing which roles were used,
        # so we register a generic handler via on_interaction instead.
        pass

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """Handle persistent role button clicks that survive restarts."""
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = interaction.data.get("custom_id", "")
        if not custom_id.startswith("role:"):
            return

        try:
            role_id = int(custom_id.split(":")[1])
        except (IndexError, ValueError):
            return

        role = interaction.guild.get_role(role_id)
        if not role:
            return await interaction.response.send_message(
                embed=error("Role Not Found", "This role no longer exists."), ephemeral=True
            )

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role, reason="Role button toggle")
            await interaction.response.send_message(
                embed=error("Role Removed", f"Removed {role.mention} from you."), ephemeral=True
            )
        else:
            await interaction.user.add_roles(role, reason="Role button toggle")
            await interaction.response.send_message(
                embed=success("Role Added", f"Gave you {role.mention}!"), ephemeral=True
            )

    # ── Role group ────────────────────────────────────────────────────────────
    role_group = app_commands.Group(name="role", description="Role management commands.")

    # ── /role panel ───────────────────────────────────────────────────────────
    @role_group.command(name="panel", description="Send a role selection panel with buttons.")
    @app_commands.describe(
        channel="Channel to send the panel",
        title="Panel title",
        description="Panel description",
        role1="First role",
        role2="Second role",
        role3="Third role",
        role4="Fourth role",
        role5="Fifth role",
    )
    @is_admin()
    async def role_panel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        title: str,
        description: str,
        role1: discord.Role,
        role2: discord.Role | None = None,
        role3: discord.Role | None = None,
        role4: discord.Role | None = None,
        role5: discord.Role | None = None,
    ):
        roles = [(r, None) for r in [role1, role2, role3, role4, role5] if r is not None]

        # Validate all roles are below bot's top role
        bot_top = interaction.guild.me.top_role
        invalid = [r for r, _ in roles if r >= bot_top]
        if invalid:
            return await interaction.response.send_message(
                embed=error("Role Too High", f"My role is below: {', '.join(r.mention for r in invalid)}"),
                ephemeral=True,
            )

        embed = discord.Embed(title=title, description=description, color=config.BOT_COLOR)
        embed.set_footer(text="Click a button to toggle a role.")

        view = RoleButtonView(roles)
        await channel.send(embed=embed, view=view)
        await interaction.response.send_message(
            embed=success("Panel Sent", f"Role panel sent to {channel.mention}."), ephemeral=True
        )

    # ── /role reaction add ────────────────────────────────────────────────────
    @role_group.command(name="reaction_add", description="Add a reaction role to a message.")
    @app_commands.describe(
        message_id="ID of the message",
        channel="Channel containing the message",
        emoji="Emoji to react with",
        role="Role to give",
    )
    @is_admin()
    async def reaction_add(
        self,
        interaction: discord.Interaction,
        message_id: str,
        channel: discord.TextChannel,
        emoji: str,
        role: discord.Role,
    ):
        await interaction.response.defer(ephemeral=True)
        try:
            message = await channel.fetch_message(int(message_id))
        except (discord.NotFound, ValueError):
            return await interaction.followup.send(embed=error("Message Not Found"), ephemeral=True)

        try:
            await message.add_reaction(emoji)
        except discord.HTTPException:
            return await interaction.followup.send(
                embed=error("Invalid Emoji", f"`{emoji}` is not a valid emoji."), ephemeral=True
            )

        await db.add_reaction_role(interaction.guild_id, channel.id, message.id, emoji, role.id)
        await interaction.followup.send(
            embed=success("Reaction Role Added", f"{emoji} → {role.mention} on [that message]({message.jump_url})."),
            ephemeral=True,
        )

    # ── /role reaction remove ─────────────────────────────────────────────────
    @role_group.command(name="reaction_remove", description="Remove a reaction role from a message.")
    @app_commands.describe(message_id="ID of the message", emoji="Emoji to remove")
    @is_admin()
    async def reaction_remove(
        self,
        interaction: discord.Interaction,
        message_id: str,
        emoji: str,
    ):
        await db.remove_reaction_role(int(message_id), emoji)
        await interaction.response.send_message(
            embed=success("Reaction Role Removed", f"Removed {emoji} reaction role."), ephemeral=True
        )

    # ── /role reaction list ───────────────────────────────────────────────────
    @role_group.command(name="reaction_list", description="List all reaction roles in this server.")
    @is_admin()
    async def reaction_list(self, interaction: discord.Interaction):
        rows = await db.get_reaction_roles(interaction.guild_id)
        if not rows:
            return await interaction.response.send_message(
                embed=info("No Reaction Roles", "None set up yet."), ephemeral=True
            )

        embed = discord.Embed(title="🎭 Reaction Roles", color=config.BOT_COLOR)
        for row in rows[:20]:
            embed.add_field(
                name=f"{row['emoji']} → <@&{row['role_id']}>",
                value=f"Message: `{row['message_id']}` in <#{row['channel_id']}>",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /role auto add ────────────────────────────────────────────────────────
    @role_group.command(name="auto_add", description="Add a role to be given to all new members.")
    @app_commands.describe(role="Role to auto-assign on join")
    @is_admin()
    async def auto_add(self, interaction: discord.Interaction, role: discord.Role):
        cfg = await db.ensure_guild(interaction.guild_id)
        roles = list(cfg["auto_role_ids"] or [])

        if role.id in roles:
            return await interaction.response.send_message(
                embed=error("Already Added", f"{role.mention} is already an auto-role."), ephemeral=True
            )
        if len(roles) >= 5:
            return await interaction.response.send_message(
                embed=error("Limit Reached", "You can have a maximum of 5 auto-roles."), ephemeral=True
            )

        roles.append(role.id)
        await db.set_guild(interaction.guild_id, auto_role_ids=roles)
        await interaction.response.send_message(
            embed=success("Auto-Role Added", f"{role.mention} will now be given to all new members."), ephemeral=True
        )

    # ── /role auto remove ─────────────────────────────────────────────────────
    @role_group.command(name="auto_remove", description="Remove a role from the auto-role list.")
    @app_commands.describe(role="Role to remove from auto-assign")
    @is_admin()
    async def auto_remove(self, interaction: discord.Interaction, role: discord.Role):
        cfg = await db.ensure_guild(interaction.guild_id)
        roles = list(cfg["auto_role_ids"] or [])

        if role.id not in roles:
            return await interaction.response.send_message(
                embed=error("Not Found", f"{role.mention} is not an auto-role."), ephemeral=True
            )

        roles.remove(role.id)
        await db.set_guild(interaction.guild_id, auto_role_ids=roles)
        await interaction.response.send_message(
            embed=success("Auto-Role Removed", f"{role.mention} will no longer be auto-assigned."), ephemeral=True
        )

    # ── /role auto list ───────────────────────────────────────────────────────
    @role_group.command(name="auto_list", description="List all auto-roles.")
    @is_admin()
    async def auto_list(self, interaction: discord.Interaction):
        cfg = await db.ensure_guild(interaction.guild_id)
        roles = cfg["auto_role_ids"] or []

        if not roles:
            return await interaction.response.send_message(
                embed=info("No Auto-Roles", "None configured yet. Use `/role auto_add` to add one."), ephemeral=True
            )

        embed = discord.Embed(title="🎭 Auto-Roles", color=config.BOT_COLOR)
        embed.description = "\n".join(f"• <@&{rid}>" for rid in roles)
        embed.set_footer(text="These roles are given to all new members on join.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /role give ────────────────────────────────────────────────────────────
    @role_group.command(name="give", description="Give a role to a member.")
    @app_commands.describe(member="Member to give the role to", role="Role to give")
    @is_admin()
    async def role_give(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        if role >= interaction.guild.me.top_role:
            return await interaction.response.send_message(
                embed=error("Role Too High", "I can't assign roles above my own."), ephemeral=True
            )
        if role in member.roles:
            return await interaction.response.send_message(
                embed=error("Already Has Role", f"{member.mention} already has {role.mention}."), ephemeral=True
            )

        await member.add_roles(role, reason=f"Role given by {interaction.user}")
        await interaction.response.send_message(
            embed=success("Role Given", f"Gave {role.mention} to {member.mention}."), ephemeral=True
        )

    # ── /role take ────────────────────────────────────────────────────────────
    @role_group.command(name="take", description="Take a role from a member.")
    @app_commands.describe(member="Member to take the role from", role="Role to remove")
    @is_admin()
    async def role_take(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        if role >= interaction.guild.me.top_role:
            return await interaction.response.send_message(
                embed=error("Role Too High", "I can't remove roles above my own."), ephemeral=True
            )
        if role not in member.roles:
            return await interaction.response.send_message(
                embed=error("Doesn't Have Role", f"{member.mention} doesn't have {role.mention}."), ephemeral=True
            )

        await member.remove_roles(role, reason=f"Role taken by {interaction.user}")
        await interaction.response.send_message(
            embed=success("Role Taken", f"Removed {role.mention} from {member.mention}."), ephemeral=True
        )

    # ── /role all ─────────────────────────────────────────────────────────────
    @role_group.command(name="all", description="Give a role to all current members.")
    @app_commands.describe(role="Role to give everyone")
    @is_admin()
    async def role_all(self, interaction: discord.Interaction, role: discord.Role):
        if role >= interaction.guild.me.top_role:
            return await interaction.response.send_message(
                embed=error("Role Too High", "I can't assign roles above my own."), ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)
        count = 0
        for member in interaction.guild.members:
            if not member.bot and role not in member.roles:
                try:
                    await member.add_roles(role, reason=f"Mass role by {interaction.user}")
                    count += 1
                except discord.Forbidden:
                    pass

        await interaction.followup.send(
            embed=success("Mass Role Complete", f"Gave {role.mention} to **{count}** member(s)."), ephemeral=True
        )

    # ── Reaction role listeners ───────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id or payload.member.bot:
            return

        emoji = str(payload.emoji)
        row   = await db.get_reaction_role(payload.message_id, emoji)
        if not row:
            return

        guild = self.bot.get_guild(payload.guild_id)
        role  = guild.get_role(row["role_id"])
        if role:
            try:
                await payload.member.add_roles(role, reason="Reaction role")
            except discord.Forbidden:
                pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id:
            return

        emoji = str(payload.emoji)
        row   = await db.get_reaction_role(payload.message_id, emoji)
        if not row:
            return

        guild  = self.bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id)
        if not member or member.bot:
            return

        role = guild.get_role(row["role_id"])
        if role and role in member.roles:
            try:
                await member.remove_roles(role, reason="Reaction role removed")
            except discord.Forbidden:
                pass

    # ── Error handler ─────────────────────────────────────────────────────────
    async def cog_app_command_error(self, interaction: discord.Interaction, err: app_commands.AppCommandError):
        msg = "You need Administrator permission." if isinstance(err, app_commands.MissingPermissions) else f"`{err}`"
        if interaction.response.is_done():
            await interaction.followup.send(embed=error("Error", msg), ephemeral=True)
        else:
            await interaction.response.send_message(embed=error("Error", msg), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Roles(bot))
