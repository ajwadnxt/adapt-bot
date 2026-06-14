import re
import time
import discord
from discord.ext import commands
from collections import defaultdict
from database import db
from utils.embeds import log_event


# ── Regex Patterns ────────────────────────────────────────────────────────────
URL_PATTERN = re.compile(
    r"(https?://|discord\.gg/|www\.)[^\s]+"
    r"|[a-zA-Z0-9\-]+\.(com|net|org|io|gg|xyz|co|me|tv|live|app|dev|gg)[^\s]*",
    re.IGNORECASE,
)
INVITE_PATTERN = re.compile(
    r"(discord\.gg|discord\.com/invite|discordapp\.com/invite)/[a-zA-Z0-9\-]+",
    re.IGNORECASE,
)


class AutoMod(commands.Cog):
    """Automatic moderation — spam, links, bad words."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # { guild_id: { user_id: [timestamps] } }
        self._message_cache: dict[int, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
        # Spam config: 5 messages within 5 seconds = spam
        self.SPAM_COUNT    = 5
        self.SPAM_INTERVAL = 5.0

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        if message.author.guild_permissions.manage_messages:
            return  # Mods are exempt

        cfg = await db.get_guild(message.guild.id)
        if not cfg or not cfg["automod_enabled"]:
            return

        # Run all enabled checks — first match wins
        if cfg["automod_spam"] and await self._check_spam(message, cfg):
            return
        if cfg["automod_links"] and await self._check_links(message, cfg):
            return
        if cfg["automod_badwords"] and await self._check_badwords(message, cfg):
            return

    # ── Spam ──────────────────────────────────────────────────────────────────

    async def _check_spam(self, message: discord.Message, cfg) -> bool:
        uid   = message.author.id
        gid   = message.guild.id
        now   = time.monotonic()
        times = self._message_cache[gid][uid]

        # Keep only timestamps within the interval
        times = [t for t in times if now - t < self.SPAM_INTERVAL]
        times.append(now)
        self._message_cache[gid][uid] = times

        if len(times) < self.SPAM_COUNT:
            return False

        # Delete recent spam messages
        try:
            def is_spam(m): return m.author.id == uid
            await message.channel.purge(limit=self.SPAM_COUNT + 2, check=is_spam)
        except discord.Forbidden:
            pass

        # Timeout for 5 minutes
        try:
            import datetime
            await message.author.timeout(datetime.timedelta(minutes=5), reason="[AutoMod] Spam detected")
        except discord.Forbidden:
            pass

        self._message_cache[gid][uid] = []

        await self._notify(message, cfg, "spam", "Sending messages too quickly", "5 minute timeout applied")
        await db.add_automod_log(gid, uid, "spam", f"{self.SPAM_COUNT} messages in {self.SPAM_INTERVAL}s", "timeout 5m")
        return True

    # ── Links ─────────────────────────────────────────────────────────────────

    async def _check_links(self, message: discord.Message, cfg) -> bool:
        if not URL_PATTERN.search(message.content) and not INVITE_PATTERN.search(message.content):
            return False

        try:
            await message.delete()
        except discord.Forbidden:
            pass

        await self._warn_user(message, cfg, "links", "Posting links is not allowed here.")
        await db.add_automod_log(
            message.guild.id, message.author.id, "links",
            message.content[:200], "message deleted"
        )
        return True

    # ── Bad Words ─────────────────────────────────────────────────────────────

    async def _check_badwords(self, message: discord.Message, cfg) -> bool:
        words   = cfg["automod_badwords_list"] or []
        content = message.content.lower()

        triggered = next((w for w in words if re.search(rf"\b{re.escape(w)}\b", content)), None)
        if not triggered:
            return False

        try:
            await message.delete()
        except discord.Forbidden:
            pass

        await self._warn_user(message, cfg, "badwords", "Your message contained a prohibited word.")
        await db.add_automod_log(
            message.guild.id, message.author.id, "badwords",
            f"Triggered: '{triggered}'", "message deleted"
        )
        return True

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _warn_user(self, message: discord.Message, cfg, rule: str, reason: str):
        """Send a temporary warning in the channel and try to DM the user."""
        try:
            warning = await message.channel.send(
                f"⚠️ {message.author.mention} — {reason}",
                delete_after=5,
            )
        except discord.Forbidden:
            pass

        try:
            await message.author.send(
                f"⚠️ Your message in **{message.guild.name}** was removed.\n**Reason:** {reason}"
            )
        except (discord.Forbidden, discord.HTTPException):
            pass

        await self._log(message.guild, cfg, rule, message.author, reason, message.content)

    async def _notify(self, message: discord.Message, cfg, rule: str, reason: str, action: str):
        """Notify in channel about a spam action."""
        try:
            await message.channel.send(
                f"🛡️ {message.author.mention} — {reason}. **{action}**.",
                delete_after=8,
            )
        except discord.Forbidden:
            pass

        await self._log(message.guild, cfg, rule, message.author, reason, action)

    async def _log(self, guild: discord.Guild, cfg, rule: str, member: discord.Member, reason: str, detail: str):
        """Send log embed to the automod log channel."""
        channel_id = cfg["automod_log_channel_id"] or cfg["log_channel_id"]
        if not channel_id:
            return
        channel = guild.get_channel(channel_id)
        if not channel:
            return

        icons = {"spam": "🔁", "links": "🔗", "badwords": "🤬"}
        embed = log_event(
            f"{icons.get(rule, '🛡️')} AutoMod — {rule.title()}",
            color=discord.Color.orange(),
        )
        embed.add_field(name="Member",  value=f"{member.mention} (`{member}`)")
        embed.add_field(name="Channel", value=f"<#{cfg.get('log_channel_id', 0)}>")
        embed.add_field(name="Reason",  value=reason, inline=False)
        embed.add_field(name="Detail",  value=str(detail)[:300], inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)

        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))
