import discord
from discord.ext import commands
from database import db
import config
import logging

log = logging.getLogger("welcome")


def format_message(template: str, member: discord.Member) -> str:
    return (
        template
        .replace("{user}",   member.mention)
        .replace("{name}",   member.display_name)
        .replace("{server}", member.guild.name)
        .replace("{count}",  str(member.guild.member_count))
    )


class Welcome(commands.Cog):
    """Sends welcome and leave messages when members join or leave."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        try:
            await self._handle_join(member)
        except Exception as e:
            log.error(f"Error in on_member_join for {member}: {e}")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        try:
            await self._handle_leave(member)
        except Exception as e:
            log.error(f"Error in on_member_remove for {member}: {e}")

    async def _handle_join(self, member: discord.Member):
        cfg = await db.ensure_guild(member.guild.id)

        # ── Auto-roles ────────────────────────────────────────────────────────
        for role_id in (cfg["auto_role_ids"] or []):
            role = member.guild.get_role(role_id)
            if role and role < member.guild.me.top_role:
                try:
                    await member.add_roles(role, reason="Auto-role on join")
                except (discord.Forbidden, discord.HTTPException) as e:
                    log.warning(f"Could not assign auto-role {role_id}: {e}")

        # ── Welcome message ───────────────────────────────────────────────────
        channel_id = cfg["welcome_channel_id"]
        if not channel_id:
            return

        channel = member.guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        # Check bot can send in that channel
        if not channel.permissions_for(member.guild.me).send_messages:
            log.warning(f"No permission to send welcome in #{channel.name}")
            return

        text = format_message(cfg["welcome_message"] or "Welcome {user} to {server}!", member)

        if cfg["welcome_embed"]:
            embed = discord.Embed(
                title=f"👋 Welcome to {member.guild.name}!",
                description=text,
                color=config.BOT_COLOR,
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"Member #{member.guild.member_count}")
            await channel.send(embed=embed)
        else:
            await channel.send(text)

    async def _handle_leave(self, member: discord.Member):
        cfg = await db.ensure_guild(member.guild.id)

        channel_id = cfg["leave_channel_id"]
        if not channel_id:
            return

        channel = member.guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        if not channel.permissions_for(member.guild.me).send_messages:
            log.warning(f"No permission to send leave message in #{channel.name}")
            return

        text = format_message(cfg["leave_message"] or "Goodbye {user}!", member)

        embed = discord.Embed(description=text, color=discord.Color.greyple())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"{member.guild.member_count} members remaining")
        await channel.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
