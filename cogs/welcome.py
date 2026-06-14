import discord
from discord.ext import commands
from database import db
from utils.embeds import error
import config


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
        await self._handle_join(member)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        await self._handle_leave(member)

    async def _handle_join(self, member: discord.Member):
        cfg = await db.ensure_guild(member.guild.id)

        # ── Auto-roles ────────────────────────────────────────────────────────
        auto_roles = cfg["auto_role_ids"] or []
        for role_id in auto_roles:
            role = member.guild.get_role(role_id)
            if role:
                try:
                    await member.add_roles(role, reason="Auto-role on join")
                except discord.Forbidden:
                    pass

        # ── Welcome message ───────────────────────────────────────────────────
        channel_id = cfg["welcome_channel_id"]
        if not channel_id:
            return

        channel = member.guild.get_channel(channel_id)
        if not channel:
            return

        text = format_message(cfg["welcome_message"], member)

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
        if not channel:
            return

        text = format_message(cfg["leave_message"], member)

        embed = discord.Embed(
            description=text,
            color=discord.Color.greyple(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"{member.guild.member_count} members remaining")
        await channel.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
