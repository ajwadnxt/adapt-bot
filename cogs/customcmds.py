import discord
from discord import app_commands
from discord.ext import commands
from database import db
from utils.checks import is_admin
from utils.embeds import success, error, info
from utils.paginator import Paginator
import config


def format_response(template: str, message: discord.Message) -> str:
    return (
        template
        .replace("{user}",    message.author.mention)
        .replace("{name}",    message.author.display_name)
        .replace("{server}",  message.guild.name)
        .replace("{count}",   str(message.guild.member_count))
        .replace("{channel}", message.channel.mention)
    )


class CustomCommands(commands.Cog):
    """Per-server custom prefix commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        cfg = await db.get_guild(message.guild.id)
        prefix = cfg["prefix"] if cfg else config.PREFIX

        if not message.content.startswith(prefix):
            return

        # Extract command name (first word after prefix)
        name = message.content[len(prefix):].split()[0].lower()
        if not name:
            return

        row = await db.get_custom_command(message.guild.id, name)
        if not row:
            return

        response = format_response(row["response"], message)
        await message.channel.send(response)
        await db.increment_command_uses(message.guild.id, name)

    # ── Command group ─────────────────────────────────────────────────────────
    cmd_group = app_commands.Group(name="cmd", description="Manage custom commands.")

    # ── /cmd add ──────────────────────────────────────────────────────────────
    @cmd_group.command(name="add", description="Add a custom command.")
    @app_commands.describe(
        name="Command name (no spaces, no prefix needed)",
        response="Response the bot sends. Use {user}, {name}, {server}, {count}, {channel}",
    )
    @is_admin()
    async def cmd_add(self, interaction: discord.Interaction, name: str, response: str):
        name = name.lower().strip()

        if " " in name:
            return await interaction.response.send_message(
                embed=error("Invalid Name", "Command name cannot contain spaces."), ephemeral=True
            )
        if len(name) > 30:
            return await interaction.response.send_message(
                embed=error("Too Long", "Command name must be 30 characters or fewer."), ephemeral=True
            )

        existing = await db.get_custom_command(interaction.guild_id, name)
        if existing:
            return await interaction.response.send_message(
                embed=error("Already Exists", f"A command named `{name}` already exists. Use `/cmd edit` to update it."),
                ephemeral=True,
            )

        cfg = await db.ensure_guild(interaction.guild_id)
        all_cmds = await db.get_custom_commands(interaction.guild_id)
        if len(all_cmds) >= 50:
            return await interaction.response.send_message(
                embed=error("Limit Reached", "You can have a maximum of 50 custom commands."), ephemeral=True
            )

        await db.add_custom_command(interaction.guild_id, name, response, interaction.user.id)

        embed = success("Command Added", f"Custom command `{cfg['prefix']}{name}` is ready.")
        embed.add_field(name="Response Preview", value=response[:500], inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /cmd edit ─────────────────────────────────────────────────────────────
    @cmd_group.command(name="edit", description="Edit an existing custom command's response.")
    @app_commands.describe(name="Command to edit", response="New response")
    @is_admin()
    async def cmd_edit(self, interaction: discord.Interaction, name: str, response: str):
        name = name.lower().strip()
        row  = await db.get_custom_command(interaction.guild_id, name)
        if not row:
            return await interaction.response.send_message(
                embed=error("Not Found", f"No command named `{name}` exists."), ephemeral=True
            )

        await db.edit_custom_command(interaction.guild_id, name, response)
        embed = success("Command Updated", f"`{name}` has been updated.")
        embed.add_field(name="New Response", value=response[:500], inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /cmd delete ───────────────────────────────────────────────────────────
    @cmd_group.command(name="delete", description="Delete a custom command.")
    @app_commands.describe(name="Command to delete")
    @is_admin()
    async def cmd_delete(self, interaction: discord.Interaction, name: str):
        name = name.lower().strip()
        row  = await db.get_custom_command(interaction.guild_id, name)
        if not row:
            return await interaction.response.send_message(
                embed=error("Not Found", f"No command named `{name}` exists."), ephemeral=True
            )

        await db.delete_custom_command(interaction.guild_id, name)
        await interaction.response.send_message(
            embed=success("Command Deleted", f"`{name}` has been removed."), ephemeral=True
        )

    # ── /cmd list ─────────────────────────────────────────────────────────────
    @cmd_group.command(name="list", description="List all custom commands.")
    async def cmd_list(self, interaction: discord.Interaction):
        rows = await db.get_custom_commands(interaction.guild_id)
        if not rows:
            return await interaction.response.send_message(
                embed=info("No Commands", "No custom commands yet. Add one with `/cmd add`."), ephemeral=True
            )

        cfg    = await db.ensure_guild(interaction.guild_id)
        prefix = cfg["prefix"]
        pages  = []
        chunks = [rows[i:i+10] for i in range(0, len(rows), 10)]

        for chunk in chunks:
            embed = discord.Embed(
                title=f"⚙️ Custom Commands ({len(rows)} total)",
                color=config.BOT_COLOR,
            )
            for row in chunk:
                embed.add_field(
                    name=f"`{prefix}{row['name']}`",
                    value=f"{row['response'][:80]}{'...' if len(row['response']) > 80 else ''}\n**Uses:** {row['uses']}",
                    inline=False,
                )
            pages.append(embed)

        if len(pages) == 1:
            await interaction.response.send_message(embed=pages[0], ephemeral=True)
        else:
            await interaction.response.send_message(embed=pages[0], view=Paginator(pages, interaction.user.id), ephemeral=True)

    # ── /cmd info ─────────────────────────────────────────────────────────────
    @cmd_group.command(name="info", description="View details about a custom command.")
    @app_commands.describe(name="Command to inspect")
    async def cmd_info(self, interaction: discord.Interaction, name: str):
        row = await db.get_custom_command(interaction.guild_id, name.lower().strip())
        if not row:
            return await interaction.response.send_message(
                embed=error("Not Found", f"No command named `{name}` exists."), ephemeral=True
            )

        cfg = await db.ensure_guild(interaction.guild_id)
        embed = discord.Embed(title=f"⚙️ Command: {cfg['prefix']}{row['name']}", color=config.BOT_COLOR)
        embed.add_field(name="Response", value=row["response"][:500], inline=False)
        embed.add_field(name="Uses",       value=str(row["uses"]))
        embed.add_field(name="Created by", value=f"<@{row['created_by']}>")
        embed.add_field(name="Created at", value=discord.utils.format_dt(row["created_at"], "R"))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── Error handler ─────────────────────────────────────────────────────────
    async def cog_app_command_error(self, interaction: discord.Interaction, err: app_commands.AppCommandError):
        msg = "You need Administrator permission." if isinstance(err, app_commands.MissingPermissions) else f"`{err}`"
        if interaction.response.is_done():
            await interaction.followup.send(embed=error("Error", msg), ephemeral=True)
        else:
            await interaction.response.send_message(embed=error("Error", msg), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(CustomCommands(bot))
