import discord
from discord.ext import commands
from database import db
import datetime
import logging

log = logging.getLogger("logging_cog")


class Logging(commands.Cog):
    """Logs server events to a designated channel."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _get_log_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        try:
            cfg = await db.get_guild(guild.id)
            if not cfg or not cfg["log_channel_id"]:
                return None
            channel = guild.get_channel(cfg["log_channel_id"])
            if not isinstance(channel, discord.TextChannel):
                return None
            if not channel.permissions_for(guild.me).send_messages:
                return None
            return channel
        except Exception as e:
            log.error(f"Error getting log channel: {e}")
            return None

    async def _send(self, guild: discord.Guild, embed: discord.Embed):
        embed.timestamp = datetime.datetime.utcnow()
        channel = await self._get_log_channel(guild)
        if channel:
            try:
                await channel.send(embed=embed)
            except (discord.Forbidden, discord.HTTPException):
                pass

    # ── Messages ──────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        # Ignore empty messages (e.g. image only)
        if not message.content and not message.attachments:
            return

        embed = discord.Embed(title="🗑️ Message Deleted", color=discord.Color.red())
        embed.add_field(name="Author",  value=f"{message.author.mention} (`{message.author}`)")
        embed.add_field(name="Channel", value=message.channel.mention)
        if message.content:
            embed.add_field(name="Content", value=message.content[:1024], inline=False)
        if message.attachments:
            embed.add_field(name="Attachments", value="\n".join(a.filename for a in message.attachments), inline=False)
        await self._send(message.guild, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild or before.author.bot:
            return
        if before.content == after.content:
            return
        if not before.content:
            return

        embed = discord.Embed(title="✏️ Message Edited", color=discord.Color.blue())
        embed.add_field(name="Author",  value=f"{before.author.mention} (`{before.author}`)")
        embed.add_field(name="Channel", value=before.channel.mention)
        embed.add_field(name="Before",  value=before.content[:512] or "*empty*", inline=False)
        embed.add_field(name="After",   value=after.content[:512]  or "*empty*", inline=False)
        embed.add_field(name="Jump",    value=f"[Click here]({after.jump_url})")
        await self._send(before.guild, embed)

    # ── Members ───────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        embed = discord.Embed(title="📥 Member Joined", color=discord.Color.green())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Member",  value=f"{member.mention} (`{member}`)")
        embed.add_field(name="ID",      value=f"`{member.id}`")
        embed.add_field(name="Account Created", value=discord.utils.format_dt(member.created_at, "R"))
        embed.add_field(name="Member Count", value=f"`{member.guild.member_count}`")
        await self._send(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        embed = discord.Embed(title="📤 Member Left", color=discord.Color.orange())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Member", value=f"`{member}`")
        embed.add_field(name="ID",     value=f"`{member.id}`")
        roles = [r.mention for r in member.roles[1:]]
        if roles:
            embed.add_field(name=f"Roles ({len(roles)})", value=" ".join(roles[:10]), inline=False)
        await self._send(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.nick != after.nick:
            embed = discord.Embed(title="📝 Nickname Changed", color=discord.Color.blurple())
            embed.add_field(name="Member", value=after.mention)
            embed.add_field(name="Before", value=before.nick or "*None*")
            embed.add_field(name="After",  value=after.nick  or "*None*")
            await self._send(after.guild, embed)

        added   = [r for r in after.roles  if r not in before.roles]
        removed = [r for r in before.roles if r not in after.roles]
        if added or removed:
            embed = discord.Embed(title="🎭 Roles Updated", color=discord.Color.blurple())
            embed.add_field(name="Member", value=after.mention)
            if added:   embed.add_field(name="Added",   value=" ".join(r.mention for r in added))
            if removed: embed.add_field(name="Removed", value=" ".join(r.mention for r in removed))
            await self._send(after.guild, embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        embed = discord.Embed(title="🔨 Member Banned", color=discord.Color.red())
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="User", value=f"`{user}`")
        embed.add_field(name="ID",   value=f"`{user.id}`")
        await self._send(guild, embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        embed = discord.Embed(title="✅ Member Unbanned", color=discord.Color.green())
        embed.add_field(name="User", value=f"`{user}`")
        embed.add_field(name="ID",   value=f"`{user.id}`")
        await self._send(guild, embed)

    # ── Channels ──────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        embed = discord.Embed(title="📢 Channel Created", color=discord.Color.green())
        embed.add_field(name="Name", value=channel.mention if hasattr(channel, 'mention') else f"`#{channel.name}`")
        embed.add_field(name="Type", value=str(channel.type).replace("_", " ").title())
        embed.add_field(name="Category", value=channel.category.name if channel.category else "None")
        await self._send(channel.guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        embed = discord.Embed(title="🗑️ Channel Deleted", color=discord.Color.red())
        embed.add_field(name="Name", value=f"`#{channel.name}`")
        embed.add_field(name="Type", value=str(channel.type).replace("_", " ").title())
        await self._send(channel.guild, embed)

    # ── Roles ─────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        embed = discord.Embed(title="🎭 Role Created", color=discord.Color.green())
        embed.add_field(name="Name",  value=role.mention)
        embed.add_field(name="Color", value=str(role.color))
        await self._send(role.guild, embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        embed = discord.Embed(title="🗑️ Role Deleted", color=discord.Color.red())
        embed.add_field(name="Name",  value=f"`@{role.name}`")
        embed.add_field(name="Color", value=str(role.color))
        await self._send(role.guild, embed)

    # ── Voice ─────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if before.channel == after.channel:
            return

        if before.channel is None:
            embed = discord.Embed(title="🔊 Joined Voice", color=discord.Color.green())
            embed.add_field(name="Member",  value=member.mention)
            embed.add_field(name="Channel", value=after.channel.mention)
        elif after.channel is None:
            embed = discord.Embed(title="🔇 Left Voice", color=discord.Color.red())
            embed.add_field(name="Member",  value=member.mention)
            embed.add_field(name="Channel", value=before.channel.mention)
        else:
            embed = discord.Embed(title="🔀 Moved Voice Channel", color=discord.Color.blurple())
            embed.add_field(name="Member", value=member.mention)
            embed.add_field(name="From",   value=before.channel.mention)
            embed.add_field(name="To",     value=after.channel.mention)

        await self._send(member.guild, embed)

    # ── Server ────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        if before.name != after.name:
            embed = discord.Embed(title="🏠 Server Renamed", color=discord.Color.blurple())
            embed.add_field(name="Before", value=before.name)
            embed.add_field(name="After",  value=after.name)
            await self._send(after, embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Logging(bot))
