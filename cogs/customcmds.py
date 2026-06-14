import json
import os
import discord
from discord import app_commands
from discord.ext import commands
from database import db
from utils.checks import is_mod
from utils.embeds import success, error, info
import config


class CustomCommands(commands.Cog):
    """Create and manage custom commands for your server."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.json_file = "database/custom_commands.json"
        self._local_commands = {}
        # Ensure database folder exists for fallback json
        if not os.path.exists("database"):
            os.makedirs("database")
        self._load_local_commands()

    def _load_local_commands(self):
        if os.path.exists(self.json_file):
            try:
                with open(self.json_file, "r", encoding="utf-8") as f:
                    self._local_commands = json.load(f)
            except Exception:
                self._local_commands = {}

    def _save_local_commands(self):
        try:
            with open(self.json_file, "w", encoding="utf-8") as f:
                json.dump(self._local_commands, f, indent=4, ensure_ascii=False)
        except Exception as e:
            self.bot.logger.error(f"Failed to save local custom commands: {e}")

    async def get_cmd(self, guild_id: int, name: str):
        name = name.lower()
        if db._pool is not None:
            try:
                return await db.get_custom_command(guild_id, name)
            except Exception:
                pass
        # Fallback to local JSON
        guild_key = str(guild_id)
        if guild_key in self._local_commands and name in self._local_commands[guild_key]:
            return self._local_commands[guild_key][name]
        return None

    async def get_all_cmds(self, guild_id: int):
        if db._pool is not None:
            try:
                return await db.get_custom_commands(guild_id)
            except Exception:
                pass
        # Fallback to local JSON
        guild_key = str(guild_id)
        if guild_key in self._local_commands:
            return [
                {
                    "name": k,
                    "response": v["response"],
                    "created_by": v["created_by"],
                    "uses": v.get("uses", 0),
                }
                for k, v in self._local_commands[guild_key].items()
            ]
        return []

    async def add_cmd(self, guild_id: int, name: str, response: str, created_by: int):
        name = name.lower()
        if db._pool is not None:
            try:
                existing = await db.get_custom_command(guild_id, name)
                if existing:
                    await db.edit_custom_command(guild_id, name, response)
                else:
                    await db.add_custom_command(guild_id, name, response, created_by)
                return
            except Exception:
                pass
        # Fallback to local JSON
        guild_key = str(guild_id)
        if guild_key not in self._local_commands:
            self._local_commands[guild_key] = {}

        uses = 0
        if name in self._local_commands[guild_key]:
            uses = self._local_commands[guild_key][name].get("uses", 0)

        self._local_commands[guild_key][name] = {
            "response": response,
            "created_by": created_by,
            "uses": uses,
        }
        self._save_local_commands()

    async def delete_cmd(self, guild_id: int, name: str) -> bool:
        name = name.lower()
        if db._pool is not None:
            try:
                existing = await db.get_custom_command(guild_id, name)
                if existing:
                    await db.delete_custom_command(guild_id, name)
                    return True
                return False
            except Exception:
                pass
        # Fallback to local JSON
        guild_key = str(guild_id)
        if guild_key in self._local_commands and name in self._local_commands[guild_key]:
            del self._local_commands[guild_key][name]
            self._save_local_commands()
            return True
        return False

    async def incr_uses(self, guild_id: int, name: str):
        name = name.lower()
        if db._pool is not None:
            try:
                await db.increment_command_uses(guild_id, name)
                return
            except Exception:
                pass
        # Fallback to local JSON
        guild_key = str(guild_id)
        if guild_key in self._local_commands and name in self._local_commands[guild_key]:
            self._local_commands[guild_key][name]["uses"] = (
                self._local_commands[guild_key][name].get("uses", 0) + 1
            )
            self._save_local_commands()

    # ── Slash Command Group (/cc) ───────────────────────────────────────────────
    cc_group = app_commands.Group(
        name="cc", description="Manage custom commands for this server."
    )

    @cc_group.command(name="create", description="Create or update a custom command.")
    @app_commands.describe(
        name="The trigger name for the custom command (e.g. rules)",
        response="The message to send when triggered",
    )
    @is_mod()
    async def cc_create(
        self, interaction: discord.Interaction, name: str, response: str
    ):
        prefix = config.PREFIX or "."
        # Clean the command name
        name = name.lower().strip()
        if name.startswith(prefix):
            name = name[len(prefix) :]

        if not name:
            await interaction.response.send_message(
                embed=error("Invalid Name", "The command name cannot be empty."),
                ephemeral=True,
            )
            return

        # Check if name contains spaces
        if len(name.split()) > 1:
            await interaction.response.send_message(
                embed=error("Invalid Name", "Command names cannot contain spaces."),
                ephemeral=True,
            )
            return

        # Check if name conflicts with built-in commands
        if self.bot.get_command(name):
            await interaction.response.send_message(
                embed=error(
                    "Reserved Name",
                    f"`{name}` is a built-in bot command and cannot be overwritten.",
                ),
                ephemeral=True,
            )
            return

        existing = await self.get_cmd(interaction.guild_id, name)
        await self.add_cmd(
            interaction.guild_id, name, response, interaction.user.id
        )

        is_fallback = db._pool is None
        storage_notice = " *(saved to local database)*" if is_fallback else ""

        action = "Updated" if existing else "Created"
        desc = (
            f"Custom command `{prefix}{name}` has been successfully {action.lower()}!{storage_notice}\n\n"
            f"**Response:**\n{response}"
        )
        await interaction.response.send_message(embed=success(f"Command {action}", desc))

    @cc_group.command(name="delete", description="Delete a custom command.")
    @app_commands.describe(name="The name of the custom command to delete")
    @is_mod()
    async def cc_delete(self, interaction: discord.Interaction, name: str):
        prefix = config.PREFIX or "."
        name = name.lower().strip()
        if name.startswith(prefix):
            name = name[len(prefix) :]

        deleted = await self.delete_cmd(interaction.guild_id, name)
        if deleted:
            await interaction.response.send_message(
                embed=success(
                    "Command Deleted",
                    f"Successfully deleted custom command `{prefix}{name}`.",
                )
            )
        else:
            await interaction.response.send_message(
                embed=error(
                    "Not Found",
                    f"No custom command found with the name `{prefix}{name}`.",
                ),
                ephemeral=True,
            )

    @cc_group.command(name="list", description="List all custom commands in this server.")
    async def cc_list(self, interaction: discord.Interaction):
        prefix = config.PREFIX or "."
        cmds = await self.get_all_cmds(interaction.guild_id)
        if not cmds:
            await interaction.response.send_message(
                embed=info(
                    "No Custom Commands",
                    "There are no custom commands configured for this server yet.",
                ),
                ephemeral=True,
            )
            return

        embed = info(
            "Custom Commands",
            f"List of custom commands configured for **{interaction.guild.name}**:",
        )

        cmd_list_str = ""
        for cmd in cmds:
            resp_snippet = cmd["response"]
            if len(resp_snippet) > 40:
                resp_snippet = resp_snippet[:37] + "..."
            cmd_list_str += f"`{prefix}{cmd['name']}`: {resp_snippet} (Uses: {cmd['uses']})\n"

        chunks = [
            cmd_list_str[i : i + 1000] for i in range(0, len(cmd_list_str), 1000)
        ]
        for idx, chunk in enumerate(chunks):
            field_name = "Commands" if idx == 0 else "Commands (continued)"
            embed.add_field(name=field_name, value=chunk, inline=False)

        await interaction.response.send_message(embed=embed)

    # ── Text Listener for Custom Commands ─────────────────────────────────────────
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        prefix = await self.bot.get_prefix(message)
        matched_prefix = None
        if isinstance(prefix, (list, tuple)):
            for p in prefix:
                if p and message.content.startswith(p):
                    matched_prefix = p
                    break
        elif isinstance(prefix, str) and prefix and message.content.startswith(prefix):
            matched_prefix = prefix

        if not matched_prefix:
            return

        content = message.content[len(matched_prefix) :].strip()
        if not content:
            return

        parts = content.split(maxsplit=1)
        cmd_name = parts[0].lower()

        # Don't override standard bot prefix commands
        if self.bot.get_command(cmd_name):
            return

        cmd = await self.get_cmd(message.guild.id, cmd_name)
        if cmd:
            await self.incr_uses(message.guild.id, cmd_name)
            await message.channel.send(cmd["response"])


async def setup(bot: commands.Bot):
    await bot.add_cog(CustomCommands(bot))
