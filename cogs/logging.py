import discord
from discord.ext import commands
from database import db
from utils.embeds import log_event
import datetime


class Logging(commands.Cog):
    """Logs server events to a designated channel."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _get_log_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        cfg = await db.get_guild(guild.id)
        if not cfg or not cfg["log_channel_id"]:
            return None
        return guild.get_channel(cfg["log_channel_id"])

    async def _send(self, guild: discord.Guild, embed: discord.Embed):
        channel = await self._get_log_channel(guild)
        if channel:
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                pass

    # ── Messages ──────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        embed = log_event("🗑️ Message Deleted", color=discord.Color.red())
        embed.add_field(name="Author",  value=f"{message.author.mention} (`{message.author}`)")
        embed.add_field(name="Channel", value=message.channel.mention)
        if message.content:
            embed.add_field(name="Content", value=message.content[:1024], inline=False)
        await self._send(message.guild, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild or before.author.bot:
            return
        if before.content == after.content:
            return
        embed = log_event("✏️ Message Edited", color=discord.Color.blue())
        embed.add_field(name="Author",  value=f"{before.author.mention} (`{before.author}`)")
        embed.add_field(name="Channel", value=before.channel.mention)
        embed.add_field(name="Before",  value=before.content[:512] or "*empty*", inline=False)
        embed.add_field(name="After",   value=after.content[:512]  or "*empty*", inline=False)
        embed.add_field(name="Jump",    value=f"[Click here]({after.jump_url})")
        await self._send(before.guild, embed)

    # ── Members ───────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        embed = log_event("📥 Member Joined", color=discord.Color.green())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Member",  value=f"{member.mention} (`{member}`)")
        embed.add_field(name="ID",      value=str(member.id))
        embed.add_field(name="Account Created", value=discord.utils.format_dt(member.created_at, "R"))
        await self._send(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        embed = log_event("📤 Member Left", color=discord.Color.orange())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Member", value=f"`{member}`")
        embed.add_field(name="ID",     value=str(member.id))
        roles = [r.mention for r in member.roles[1:]]
        if roles:
            embed.add_field(name="Roles", value=" ".join(roles[:10]), inline=False)
        await self._send(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        # Nickname change
        if before.nick != after.nick:
            embed = log_event("📝 Nickname Changed", color=discord.Color.blurple())
            embed.add_field(name="Member", value=after.mention)
            embed.add_field(name="Before", value=before.nick or "*None*")
            embed.add_field(name="After",  value=after.nick  or "*None*")
            await self._send(after.guild, embed)

        # Roles added/removed
        added   = [r for r in after.roles  if r not in before.roles]
        removed = [r for r in before.roles if r not in after.roles]
        if added or removed:
            embed = log_event("🎭 Roles Updated", color=discord.Color.blurple())
            embed.add_field(name="Member", value=after.mention)
            if added:
                embed.add_field(name="Added",   value=" ".join(r.mention for r in added))
            if removed:
                embed.add_field(name="Removed", value=" ".join(r.mention for r in removed))
            await self._send(after.guild, embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        embed = log_event("🔨 Member Banned", color=discord.Color.red())
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="User", value=f"`{user}`")
        embed.add_field(name="ID",   value=str(user.id))
        await self._send(guild, embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        embed = log_event("✅ Member Unbanned", color=discord.Color.green())
        embed.add_field(name="User", value=f"`{user}`")
        embed.add_field(name="ID",   value=str(user.id))
        await self._send(guild, embed)

    # ── Channels ──────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        embed = log_event("📢 Channel Created", color=discord.Color.green())
        embed.add_field(name="Name", value=channel.mention)
        embed.add_field(name="Type", value=str(channel.type).title())
        await self._send(channel.guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        embed = log_event("🗑️ Channel Deleted", color=discord.Color.red())
        embed.add_field(name="Name", value=f"`#{channel.name}`")
        embed.add_field(name="Type", value=str(channel.type).title())
        await self._send(channel.guild, embed)

    # ── Roles ─────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        embed = log_event("🎭 Role Created", color=discord.Color.green())
        embed.add_field(name="Name",  value=role.mention)
        embed.add_field(name="Color", value=str(role.color))
        await self._send(role.guild, embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        embed = log_event("🗑️ Role Deleted", color=discord.Color.red())
        embed.add_field(name="Name",  value=f"`@{role.name}`")
        embed.add_field(name="Color", value=str(role.color))
        await self._send(role.guild, embed)

    # ── Voice ─────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        if before.channel == after.channel:
            return

        if before.channel is None:
            embed = log_event("🔊 Joined Voice", color=discord.Color.green())
            embed.add_field(name="Member",  value=member.mention)
            embed.add_field(name="Channel", value=after.channel.mention)
        elif after.channel is None:
            embed = log_event("🔇 Left Voice", color=discord.Color.red())
            embed.add_field(name="Member",  value=member.mention)
            embed.add_field(name="Channel", value=before.channel.mention)
        else:
            embed = log_event("🔀 Moved Voice Channel", color=discord.Color.blurple())
            embed.add_field(name="Member", value=member.mention)
            embed.add_field(name="From",   value=before.channel.mention)
            embed.add_field(name="To",     value=after.channel.mention)

        await self._send(member.guild, embed)

    # ── Invites / Server ──────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        if before.name != after.name:
            embed = log_event("🏠 Server Renamed", color=discord.Color.blurple())
            embed.add_field(name="Before", value=before.name)
            embed.add_field(name="After",  value=after.name)
            await self._send(after, embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Logging(bot))
