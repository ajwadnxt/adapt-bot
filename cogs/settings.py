import discord
from discord import app_commands
from discord.ext import commands
from utils.checks import is_admin
from utils.embeds import success, error, info
from database import db
import config


# ── Category Select Menu ──────────────────────────────────────────────────────

class SettingsSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="General",      value="general",    emoji="⚙️",  description="Prefix and basic settings"),
            discord.SelectOption(label="Welcome",      value="welcome",    emoji="👋",  description="Welcome & leave messages"),
            discord.SelectOption(label="Moderation",   value="moderation", emoji="🔨",  description="Mod log channel & mute role"),
            discord.SelectOption(label="Logging",      value="logging",    emoji="📝",  description="Event log channel"),
            discord.SelectOption(label="Leveling",     value="leveling",   emoji="⭐",  description="XP system settings"),
            discord.SelectOption(label="Economy",      value="economy",    emoji="🪙",  description="Currency settings"),
            discord.SelectOption(label="Tickets",      value="tickets",    emoji="🎫",  description="Ticket system settings"),
            discord.SelectOption(label="Auto-Mod",     value="automod",    emoji="🛡️",  description="Auto-moderation settings"),
        ]
        super().__init__(placeholder="Select a category...", options=options)

    async def callback(self, interaction: discord.Interaction):
        await self.view.show_category(interaction, self.values[0])


class SettingsView(discord.ui.View):
    def __init__(self, guild_id: int, author_id: int):
        super().__init__(timeout=120)
        self.guild_id  = guild_id
        self.author_id = author_id
        self.add_item(SettingsSelect())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This isn't your settings panel.", ephemeral=True)
            return False
        return True

    async def show_category(self, interaction: discord.Interaction, category: str):
        cfg = await db.ensure_guild(self.guild_id)
        guild = interaction.guild

        def ch(cid): return f"<#{cid}>" if cid else "`Not set`"
        def ro(rid): return f"<@&{rid}>" if rid else "`Not set`"
        def bo(val): return "✅ Enabled" if val else "❌ Disabled"

        if category == "general":
            embed = info("General Settings")
            embed.add_field(name="Prefix",  value=f"`{cfg['prefix']}`")

        elif category == "welcome":
            embed = info("Welcome & Leave Settings")
            embed.add_field(name="Welcome Channel", value=ch(cfg["welcome_channel_id"]), inline=True)
            embed.add_field(name="Leave Channel",   value=ch(cfg["leave_channel_id"]),   inline=True)
            embed.add_field(name="Welcome Embed",   value=bo(cfg["welcome_embed"]),       inline=True)
            embed.add_field(name="Welcome Message", value=f"```{cfg['welcome_message']}```", inline=False)
            embed.add_field(name="Leave Message",   value=f"```{cfg['leave_message']}```",   inline=False)
            embed.add_field(name="Variables", value="`{user}` `{server}` `{count}`", inline=False)

        elif category == "moderation":
            embed = info("Moderation Settings")
            embed.add_field(name="Mod Log Channel", value=ch(cfg["mod_log_channel_id"]), inline=True)
            embed.add_field(name="Mute Role",       value=ro(cfg["mute_role_id"]),       inline=True)

        elif category == "logging":
            embed = info("Logging Settings")
            embed.add_field(name="Log Channel", value=ch(cfg["log_channel_id"]))

        elif category == "leveling":
            embed = info("Leveling Settings")
            embed.add_field(name="Status",           value=bo(cfg["leveling_enabled"]),      inline=True)
            embed.add_field(name="Level Up Channel", value=ch(cfg["level_up_channel_id"]),   inline=True)
            embed.add_field(name="XP Cooldown",      value=f"`{cfg['xp_cooldown']}s`",       inline=True)
            embed.add_field(name="XP Per Message",   value=f"`{cfg['xp_min']}–{cfg['xp_max']}`", inline=True)
            embed.add_field(name="Level Up Message", value=f"```{cfg['level_up_message']}```", inline=False)
            embed.add_field(name="Variables", value="`{user}` `{level}` `{server}`", inline=False)

        elif category == "economy":
            embed = info("Economy Settings")
            embed.add_field(name="Status",         value=bo(cfg["economy_enabled"]),  inline=True)
            embed.add_field(name="Currency Name",  value=f"`{cfg['currency_name']}`", inline=True)
            embed.add_field(name="Currency Emoji", value=cfg["currency_emoji"],        inline=True)
            embed.add_field(name="Daily Amount",   value=f"`{cfg['daily_amount']}`",  inline=True)

        elif category == "tickets":
            embed = info("Ticket Settings")
            embed.add_field(name="Status",           value=bo(cfg["ticket_enabled"]),           inline=True)
            embed.add_field(name="Category",         value=ch(cfg["ticket_category_id"]),       inline=True)
            embed.add_field(name="Log Channel",      value=ch(cfg["ticket_log_channel_id"]),    inline=True)
            embed.add_field(name="Support Role",     value=ro(cfg["ticket_support_role_id"]),   inline=True)
            embed.add_field(name="Welcome Message",  value=f"```{cfg['ticket_message']}```",    inline=False)

        elif category == "automod":
            embed = info("Auto-Mod Settings")
            embed.add_field(name="Auto-Mod",    value=bo(cfg["automod_enabled"]), inline=True)
            embed.add_field(name="Anti-Spam",   value=bo(cfg["automod_spam"]),    inline=True)
            embed.add_field(name="Anti-Links",  value=bo(cfg["automod_links"]),   inline=True)
            embed.add_field(name="Bad Words",   value=bo(cfg["automod_badwords"]),inline=True)
            embed.add_field(name="Log Channel", value=ch(cfg["automod_log_channel_id"]), inline=True)
            words = cfg["automod_badwords_list"] or []
            embed.add_field(name=f"Bad Word List ({len(words)})", value=f"`{', '.join(words)}`" if words else "`None`", inline=False)
        else:
            embed = error("Unknown category")

        embed.set_footer(text="Use /set <category> to change settings")
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


# ── Cog ───────────────────────────────────────────────────────────────────────

class Settings(commands.Cog):
    """Server configuration dashboard."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── /settings ─────────────────────────────────────────────────────────────
    @app_commands.command(name="settings", description="View and manage all server settings.")
    @is_admin()
    async def settings(self, interaction: discord.Interaction):
        await db.ensure_guild(interaction.guild_id)
        embed = info(
            f"⚙️ {interaction.guild.name} Settings",
            "Select a category below to view or edit settings.\nUse `/set` commands to change individual values."
        )
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        view = SettingsView(interaction.guild_id, interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # ── /set general ──────────────────────────────────────────────────────────
    set_group = app_commands.Group(name="set", description="Change server settings.")

    @set_group.command(name="prefix", description="Set the bot's command prefix.")
    @is_admin()
    async def set_prefix(self, interaction: discord.Interaction, prefix: str):
        if len(prefix) > 5:
            return await interaction.response.send_message(embed=error("Prefix too long", "Max 5 characters."), ephemeral=True)
        await db.ensure_guild(interaction.guild_id)
        await db.set_guild(interaction.guild_id, prefix=prefix)
        await interaction.response.send_message(embed=success("Prefix Updated", f"Prefix set to `{prefix}`"), ephemeral=True)

    # ── /set welcome ──────────────────────────────────────────────────────────
    @set_group.command(name="welcome_channel", description="Set the welcome message channel.")
    @is_admin()
    async def set_welcome_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await db.ensure_guild(interaction.guild_id)
        await db.set_guild(interaction.guild_id, welcome_channel_id=channel.id)
        await interaction.response.send_message(embed=success("Welcome Channel Set", f"Welcome messages will be sent to {channel.mention}"), ephemeral=True)

    @set_group.command(name="leave_channel", description="Set the leave message channel.")
    @is_admin()
    async def set_leave_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await db.ensure_guild(interaction.guild_id)
        await db.set_guild(interaction.guild_id, leave_channel_id=channel.id)
        await interaction.response.send_message(embed=success("Leave Channel Set", f"Leave messages will be sent to {channel.mention}"), ephemeral=True)

    @set_group.command(name="welcome_message", description="Set the welcome message. Use {user}, {server}, {count}.")
    @is_admin()
    async def set_welcome_message(self, interaction: discord.Interaction, message: str):
        await db.ensure_guild(interaction.guild_id)
        await db.set_guild(interaction.guild_id, welcome_message=message)
        await interaction.response.send_message(embed=success("Welcome Message Set", f"```{message}```"), ephemeral=True)

    @set_group.command(name="leave_message", description="Set the leave message. Use {user}, {server}, {count}.")
    @is_admin()
    async def set_leave_message(self, interaction: discord.Interaction, message: str):
        await db.ensure_guild(interaction.guild_id)
        await db.set_guild(interaction.guild_id, leave_message=message)
        await interaction.response.send_message(embed=success("Leave Message Set", f"```{message}```"), ephemeral=True)

    @set_group.command(name="welcome_embed", description="Toggle whether welcome messages use an embed.")
    @is_admin()
    async def set_welcome_embed(self, interaction: discord.Interaction, enabled: bool):
        await db.ensure_guild(interaction.guild_id)
        await db.set_guild(interaction.guild_id, welcome_embed=enabled)
        await interaction.response.send_message(embed=success("Welcome Embed", f"{'Enabled' if enabled else 'Disabled'}"), ephemeral=True)

    # ── /set moderation ───────────────────────────────────────────────────────
    @set_group.command(name="mod_log", description="Set the moderation log channel.")
    @is_admin()
    async def set_mod_log(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await db.ensure_guild(interaction.guild_id)
        await db.set_guild(interaction.guild_id, mod_log_channel_id=channel.id)
        await interaction.response.send_message(embed=success("Mod Log Set", f"Mod actions will be logged to {channel.mention}"), ephemeral=True)

    @set_group.command(name="mute_role", description="Set the mute role.")
    @is_admin()
    async def set_mute_role(self, interaction: discord.Interaction, role: discord.Role):
        await db.ensure_guild(interaction.guild_id)
        await db.set_guild(interaction.guild_id, mute_role_id=role.id)
        await interaction.response.send_message(embed=success("Mute Role Set", f"Mute role set to {role.mention}"), ephemeral=True)

    # ── /set logging ──────────────────────────────────────────────────────────
    @set_group.command(name="log_channel", description="Set the event log channel.")
    @is_admin()
    async def set_log_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await db.ensure_guild(interaction.guild_id)
        await db.set_guild(interaction.guild_id, log_channel_id=channel.id)
        await interaction.response.send_message(embed=success("Log Channel Set", f"Events will be logged to {channel.mention}"), ephemeral=True)

    # ── /set leveling ─────────────────────────────────────────────────────────
    @set_group.command(name="leveling", description="Enable or disable the leveling system.")
    @is_admin()
    async def set_leveling(self, interaction: discord.Interaction, enabled: bool):
        await db.ensure_guild(interaction.guild_id)
        await db.set_guild(interaction.guild_id, leveling_enabled=enabled)
        await interaction.response.send_message(embed=success("Leveling", f"{'Enabled' if enabled else 'Disabled'}"), ephemeral=True)

    @set_group.command(name="level_up_channel", description="Set the level up announcement channel.")
    @is_admin()
    async def set_level_up_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await db.ensure_guild(interaction.guild_id)
        await db.set_guild(interaction.guild_id, level_up_channel_id=channel.id)
        await interaction.response.send_message(embed=success("Level Up Channel Set", f"{channel.mention}"), ephemeral=True)

    @set_group.command(name="xp_cooldown", description="Set the XP cooldown in seconds.")
    @is_admin()
    async def set_xp_cooldown(self, interaction: discord.Interaction, seconds: app_commands.Range[int, 5, 3600]):
        await db.ensure_guild(interaction.guild_id)
        await db.set_guild(interaction.guild_id, xp_cooldown=seconds)
        await interaction.response.send_message(embed=success("XP Cooldown Set", f"`{seconds}` seconds"), ephemeral=True)

    @set_group.command(name="xp_range", description="Set the min and max XP per message.")
    @is_admin()
    async def set_xp_range(self, interaction: discord.Interaction,
                           minimum: app_commands.Range[int, 1, 100],
                           maximum: app_commands.Range[int, 1, 100]):
        if minimum > maximum:
            return await interaction.response.send_message(embed=error("Invalid Range", "Minimum must be less than maximum."), ephemeral=True)
        await db.ensure_guild(interaction.guild_id)
        await db.set_guild(interaction.guild_id, xp_min=minimum, xp_max=maximum)
        await interaction.response.send_message(embed=success("XP Range Set", f"`{minimum}–{maximum}` XP per message"), ephemeral=True)

    @set_group.command(name="level_up_message", description="Set the level up message. Use {user}, {level}, {server}.")
    @is_admin()
    async def set_level_up_message(self, interaction: discord.Interaction, message: str):
        await db.ensure_guild(interaction.guild_id)
        await db.set_guild(interaction.guild_id, level_up_message=message)
        await interaction.response.send_message(embed=success("Level Up Message Set", f"```{message}```"), ephemeral=True)

    # ── /set economy ──────────────────────────────────────────────────────────
    @set_group.command(name="economy", description="Enable or disable the economy system.")
    @is_admin()
    async def set_economy(self, interaction: discord.Interaction, enabled: bool):
        await db.ensure_guild(interaction.guild_id)
        await db.set_guild(interaction.guild_id, economy_enabled=enabled)
        await interaction.response.send_message(embed=success("Economy", f"{'Enabled' if enabled else 'Disabled'}"), ephemeral=True)

    @set_group.command(name="currency", description="Set the currency name and emoji.")
    @is_admin()
    async def set_currency(self, interaction: discord.Interaction, name: str, emoji: str):
        await db.ensure_guild(interaction.guild_id)
        await db.set_guild(interaction.guild_id, currency_name=name, currency_emoji=emoji)
        await interaction.response.send_message(embed=success("Currency Updated", f"{emoji} `{name}`"), ephemeral=True)

    @set_group.command(name="daily_amount", description="Set how many coins users get from /daily.")
    @is_admin()
    async def set_daily(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100000]):
        await db.ensure_guild(interaction.guild_id)
        await db.set_guild(interaction.guild_id, daily_amount=amount)
        await interaction.response.send_message(embed=success("Daily Amount Set", f"`{amount}` coins"), ephemeral=True)

    # ── /set tickets ──────────────────────────────────────────────────────────
    @set_group.command(name="tickets", description="Enable or disable the ticket system.")
    @is_admin()
    async def set_tickets(self, interaction: discord.Interaction, enabled: bool):
        await db.ensure_guild(interaction.guild_id)
        await db.set_guild(interaction.guild_id, ticket_enabled=enabled)
        await interaction.response.send_message(embed=success("Tickets", f"{'Enabled' if enabled else 'Disabled'}"), ephemeral=True)

    @set_group.command(name="ticket_category", description="Set the category where ticket channels are created.")
    @is_admin()
    async def set_ticket_category(self, interaction: discord.Interaction, category: discord.CategoryChannel):
        await db.ensure_guild(interaction.guild_id)
        await db.set_guild(interaction.guild_id, ticket_category_id=category.id)
        await interaction.response.send_message(embed=success("Ticket Category Set", f"`{category.name}`"), ephemeral=True)

    @set_group.command(name="ticket_log", description="Set the ticket log channel.")
    @is_admin()
    async def set_ticket_log(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await db.ensure_guild(interaction.guild_id)
        await db.set_guild(interaction.guild_id, ticket_log_channel_id=channel.id)
        await interaction.response.send_message(embed=success("Ticket Log Set", f"{channel.mention}"), ephemeral=True)

    @set_group.command(name="ticket_support_role", description="Set the support role that can see tickets.")
    @is_admin()
    async def set_ticket_support_role(self, interaction: discord.Interaction, role: discord.Role):
        await db.ensure_guild(interaction.guild_id)
        await db.set_guild(interaction.guild_id, ticket_support_role_id=role.id)
        await interaction.response.send_message(embed=success("Support Role Set", f"{role.mention}"), ephemeral=True)

    @set_group.command(name="ticket_message", description="Set the message sent when a ticket is opened.")
    @is_admin()
    async def set_ticket_message(self, interaction: discord.Interaction, message: str):
        await db.ensure_guild(interaction.guild_id)
        await db.set_guild(interaction.guild_id, ticket_message=message)
        await interaction.response.send_message(embed=success("Ticket Message Set", f"```{message}```"), ephemeral=True)

    # ── /set automod ──────────────────────────────────────────────────────────
    @set_group.command(name="automod", description="Enable or disable auto-moderation.")
    @is_admin()
    async def set_automod(self, interaction: discord.Interaction, enabled: bool):
        await db.ensure_guild(interaction.guild_id)
        await db.set_guild(interaction.guild_id, automod_enabled=enabled)
        await interaction.response.send_message(embed=success("Auto-Mod", f"{'Enabled' if enabled else 'Disabled'}"), ephemeral=True)

    @set_group.command(name="antispam", description="Enable or disable anti-spam.")
    @is_admin()
    async def set_antispam(self, interaction: discord.Interaction, enabled: bool):
        await db.ensure_guild(interaction.guild_id)
        await db.set_guild(interaction.guild_id, automod_spam=enabled)
        await interaction.response.send_message(embed=success("Anti-Spam", f"{'Enabled' if enabled else 'Disabled'}"), ephemeral=True)

    @set_group.command(name="antilinks", description="Enable or disable anti-links.")
    @is_admin()
    async def set_antilinks(self, interaction: discord.Interaction, enabled: bool):
        await db.ensure_guild(interaction.guild_id)
        await db.set_guild(interaction.guild_id, automod_links=enabled)
        await interaction.response.send_message(embed=success("Anti-Links", f"{'Enabled' if enabled else 'Disabled'}"), ephemeral=True)

    @set_group.command(name="badwords", description="Enable or disable bad word filter.")
    @is_admin()
    async def set_badwords(self, interaction: discord.Interaction, enabled: bool):
        await db.ensure_guild(interaction.guild_id)
        await db.set_guild(interaction.guild_id, automod_badwords=enabled)
        await interaction.response.send_message(embed=success("Bad Word Filter", f"{'Enabled' if enabled else 'Disabled'}"), ephemeral=True)

    @set_group.command(name="add_badword", description="Add a word to the bad word filter.")
    @is_admin()
    async def add_badword(self, interaction: discord.Interaction, word: str):
        await db.ensure_guild(interaction.guild_id)
        cfg = await db.get_guild(interaction.guild_id)
        words = list(cfg["automod_badwords_list"] or [])
        if word.lower() in words:
            return await interaction.response.send_message(embed=error("Already exists", f"`{word}` is already in the list."), ephemeral=True)
        words.append(word.lower())
        await db.set_guild(interaction.guild_id, automod_badwords_list=words)
        await interaction.response.send_message(embed=success("Word Added", f"`{word}` added to the filter."), ephemeral=True)

    @set_group.command(name="remove_badword", description="Remove a word from the bad word filter.")
    @is_admin()
    async def remove_badword(self, interaction: discord.Interaction, word: str):
        await db.ensure_guild(interaction.guild_id)
        cfg = await db.get_guild(interaction.guild_id)
        words = list(cfg["automod_badwords_list"] or [])
        if word.lower() not in words:
            return await interaction.response.send_message(embed=error("Not found", f"`{word}` is not in the list."), ephemeral=True)
        words.remove(word.lower())
        await db.set_guild(interaction.guild_id, automod_badwords_list=words)
        await interaction.response.send_message(embed=success("Word Removed", f"`{word}` removed from the filter."), ephemeral=True)

    @set_group.command(name="automod_log", description="Set the auto-mod log channel.")
    @is_admin()
    async def set_automod_log(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await db.ensure_guild(interaction.guild_id)
        await db.set_guild(interaction.guild_id, automod_log_channel_id=channel.id)
        await interaction.response.send_message(embed=success("Auto-Mod Log Set", f"{channel.mention}"), ephemeral=True)

    # ── Error handler ─────────────────────────────────────────────────────────
    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ You need **Administrator** to use settings.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ `{error}`", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Settings(bot))
