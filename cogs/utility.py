import discord
from discord import app_commands
from discord.ext import commands
from utils.embeds import error, info
import config


class Utility(commands.Cog):
    """Handy utility commands for getting info about users and the server."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── /avatar ───────────────────────────────────────────────────────────────
    @app_commands.command(name="avatar", description="Get a user's avatar.")
    @app_commands.describe(member="The member whose avatar you want (defaults to you)")
    async def avatar(self, interaction: discord.Interaction, member: discord.Member | None = None):
        target    = member or interaction.user
        avatar_url = target.display_avatar.url
        embed = discord.Embed(title=f"🖼️ {target.display_name}'s Avatar", color=config.BOT_COLOR)
        embed.set_image(url=avatar_url)
        embed.add_field(name="Download", value=f"[PNG]({target.display_avatar.replace(format='png').url}) • [JPG]({target.display_avatar.replace(format='jpg').url}) • [WEBP]({target.display_avatar.replace(format='webp').url})")
        await interaction.response.send_message(embed=embed)

    # ── /userinfo ─────────────────────────────────────────────────────────────
    @app_commands.command(name="userinfo", description="Show info about a member.")
    @app_commands.describe(member="The member to inspect (defaults to you)")
    async def userinfo(self, interaction: discord.Interaction, member: discord.Member | None = None):
        target = member or interaction.user
        roles  = [r.mention for r in reversed(target.roles[1:])]  # Skip @everyone, highest first

        flags  = [name.replace("_", " ").title() for name, val in target.public_flags if val]

        embed = discord.Embed(
            title=f"👤 {target}",
            color=target.color if target.color.value else config.BOT_COLOR,
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="ID",       value=f"`{target.id}`",          inline=True)
        embed.add_field(name="Nickname", value=target.nick or "None",     inline=True)
        embed.add_field(name="Bot",      value="Yes" if target.bot else "No", inline=True)
        embed.add_field(name="Created",  value=discord.utils.format_dt(target.created_at, "R"), inline=True)
        embed.add_field(name="Joined",   value=discord.utils.format_dt(target.joined_at, "R") if target.joined_at else "Unknown", inline=True)
        embed.add_field(name="Boosting", value=discord.utils.format_dt(target.premium_since, "R") if target.premium_since else "No", inline=True)
        if flags:
            embed.add_field(name="Badges", value=" • ".join(flags), inline=False)

        # Truncate roles to avoid hitting embed limits
        if roles:
            role_str = " ".join(roles[:20])
            if len(roles) > 20:
                role_str += f" *+{len(roles)-20} more*"
            embed.add_field(name=f"Roles ({len(roles)})", value=role_str, inline=False)
        else:
            embed.add_field(name="Roles", value="None", inline=False)

        await interaction.response.send_message(embed=embed)

    # ── /serverinfo ───────────────────────────────────────────────────────────
    @app_commands.command(name="serverinfo", description="Show info about this server.")
    async def serverinfo(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message(
                embed=error("Server Only", "This command must be used in a server."), ephemeral=True
            )

        # Count channel types
        text_channels  = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        categories     = len(guild.categories)

        embed = discord.Embed(title=f"🏠 {guild.name}", color=config.BOT_COLOR)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        if guild.banner:
            embed.set_image(url=guild.banner.url)

        embed.add_field(name="ID",         value=f"`{guild.id}`",           inline=True)
        embed.add_field(name="Owner",      value=guild.owner.mention if guild.owner else "Unknown", inline=True)
        embed.add_field(name="Created",    value=discord.utils.format_dt(guild.created_at, "R"), inline=True)
        embed.add_field(name="Members",    value=f"`{guild.member_count}`", inline=True)
        embed.add_field(name="Roles",      value=f"`{len(guild.roles)}`",   inline=True)
        embed.add_field(name="Boosts",     value=f"`{guild.premium_subscription_count}` (Tier {guild.premium_tier})", inline=True)
        embed.add_field(name="Channels",   value=f"💬 {text_channels} • 🔊 {voice_channels} • 📁 {categories}", inline=True)
        embed.add_field(name="Verification", value=str(guild.verification_level).title(), inline=True)
        embed.add_field(name="2FA Required", value="Yes" if guild.mfa_level else "No", inline=True)

        if guild.features:
            features = " • ".join(f.replace("_", " ").title() for f in guild.features[:6])
            embed.add_field(name="Features", value=features, inline=False)

        await interaction.response.send_message(embed=embed)

    # ── /roleinfo ─────────────────────────────────────────────────────────────
    @app_commands.command(name="roleinfo", description="Show info about a role.")
    @app_commands.describe(role="The role to inspect")
    async def roleinfo(self, interaction: discord.Interaction, role: discord.Role):
        perms = [p.replace("_", " ").title() for p, v in role.permissions if v]

        embed = discord.Embed(title=f"🎭 {role.name}", color=role.color)
        embed.add_field(name="ID",         value=f"`{role.id}`",              inline=True)
        embed.add_field(name="Color",      value=str(role.color),             inline=True)
        embed.add_field(name="Members",    value=f"`{len(role.members)}`",    inline=True)
        embed.add_field(name="Position",   value=f"`{role.position}`",        inline=True)
        embed.add_field(name="Mentionable",value="Yes" if role.mentionable else "No", inline=True)
        embed.add_field(name="Hoisted",    value="Yes" if role.hoist else "No", inline=True)
        embed.add_field(name="Created",    value=discord.utils.format_dt(role.created_at, "R"), inline=True)
        embed.add_field(name="Bot Role",   value="Yes" if role.is_bot_managed() else "No", inline=True)
        if perms:
            embed.add_field(name=f"Key Permissions ({len(perms)})", value=" • ".join(perms[:10]), inline=False)
        await interaction.response.send_message(embed=embed)

    # ── /channelinfo ──────────────────────────────────────────────────────────
    @app_commands.command(name="channelinfo", description="Show info about a channel.")
    @app_commands.describe(channel="The channel to inspect (defaults to current)")
    async def channelinfo(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None):
        target = channel or interaction.channel
        if not isinstance(target, discord.TextChannel):
            return await interaction.response.send_message(
                embed=error("Invalid Channel", "This command only works on text channels."), ephemeral=True
            )

        embed = discord.Embed(title=f"📢 #{target.name}", color=config.BOT_COLOR)
        embed.add_field(name="ID",         value=f"`{target.id}`",   inline=True)
        embed.add_field(name="Category",   value=target.category.name if target.category else "None", inline=True)
        embed.add_field(name="Position",   value=f"`{target.position}`", inline=True)
        embed.add_field(name="Slowmode",   value=f"`{target.slowmode_delay}s`" if target.slowmode_delay else "Off", inline=True)
        embed.add_field(name="NSFW",       value="Yes" if target.is_nsfw() else "No", inline=True)
        embed.add_field(name="Created",    value=discord.utils.format_dt(target.created_at, "R"), inline=True)
        if target.topic:
            embed.add_field(name="Topic", value=target.topic[:500], inline=False)
        await interaction.response.send_message(embed=embed)

    # ── /botperms ─────────────────────────────────────────────────────────────
    @app_commands.command(name="botperms", description="Check the bot's permissions in this channel.")
    async def botperms(self, interaction: discord.Interaction):
        perms   = interaction.channel.permissions_for(interaction.guild.me)
        granted = [p.replace("_", " ").title() for p, v in perms if v]
        denied  = [p.replace("_", " ").title() for p, v in perms if not v]

        embed = discord.Embed(title="🔐 Bot Permissions", color=config.BOT_COLOR)
        embed.add_field(name=f"✅ Granted ({len(granted)})", value="\n".join(f"• {p}" for p in granted[:15]) or "None", inline=True)
        embed.add_field(name=f"❌ Denied ({len(denied)})",  value="\n".join(f"• {p}" for p in denied[:15])  or "None", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /snowflake ────────────────────────────────────────────────────────────
    @app_commands.command(name="snowflake", description="Convert a Discord ID to a timestamp.")
    @app_commands.describe(snowflake_id="The Discord ID to convert")
    async def snowflake(self, interaction: discord.Interaction, snowflake_id: str):
        try:
            sid = int(snowflake_id)
        except ValueError:
            return await interaction.response.send_message(
                embed=error("Invalid ID", "Please provide a valid Discord ID."), ephemeral=True
            )
        timestamp = discord.utils.snowflake_time(sid)
        embed = discord.Embed(title="❄️ Snowflake Info", color=config.BOT_COLOR)
        embed.add_field(name="ID",        value=f"`{sid}`")
        embed.add_field(name="Created",   value=discord.utils.format_dt(timestamp, "F"))
        embed.add_field(name="Relative",  value=discord.utils.format_dt(timestamp, "R"))
        await interaction.response.send_message(embed=embed)

    # ── Error handler ─────────────────────────────────────────────────────────
    async def cog_app_command_error(self, interaction: discord.Interaction, err: app_commands.AppCommandError):
        msg = f"`{err}`"
        if interaction.response.is_done():
            await interaction.followup.send(embed=error("Error", msg), ephemeral=True)
        else:
            await interaction.response.send_message(embed=error("Error", msg), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Utility(bot))
