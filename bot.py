import asyncio
import logging
import discord
from discord.ext import commands
import config
from database.db import create_pool, close_pool
import os
import sys
import atexit

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("bot")

# Prevent multiple instances on Windows/Linux by locking a file
lock_file_handle = None

def acquire_lock():
    global lock_file_handle
    lock_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.lock")
    if os.path.exists(lock_path):
        try:
            os.remove(lock_path)
        except OSError:
            log.critical("❌ Another instance of the bot is already running (bot.lock is active). Exiting.")
            sys.exit(1)
            
    try:
        lock_file_handle = open(lock_path, "w")
        lock_file_handle.write(str(os.getpid()))
        lock_file_handle.flush()
    except OSError as e:
        log.critical(f"❌ Failed to acquire bot.lock: {e}. Exiting.")
        sys.exit(1)

def release_lock():
    global lock_file_handle
    if lock_file_handle:
        try:
            lock_file_handle.close()
        except OSError:
            pass
        lock_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.lock")
        try:
            if os.path.exists(lock_path):
                os.remove(lock_path)
        except OSError:
            pass

intents = discord.Intents.default()
intents.message_content = True
intents.members = True


class AdaptBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=self._get_prefix,
            intents=intents,
            help_command=None,
            owner_ids=set(config.OWNER_IDS),
        )

    async def _get_prefix(self, bot, message: discord.Message):
        if not message.guild:
            return config.PREFIX
        from database.db import get_prefix
        return await get_prefix(message.guild.id)

    async def setup_hook(self):
        if config.DATABASE_URL:
            self.db_pool = await create_pool()
        else:
            log.warning("⚠️  DATABASE_URL not set — running without database")
            self.db_pool = None
        await self._load_cogs()
        await self._sync_commands()

    async def _load_cogs(self):
        cogs = [
            ("cogs.general",     True),
            ("cogs.utility",     config.ENABLE_UTILITY),
            ("cogs.settings",    config.ENABLE_SETTINGS),
            ("cogs.moderation",  config.ENABLE_MODERATION),
            ("cogs.welcome",     config.ENABLE_WELCOME),
            ("cogs.logging",     config.ENABLE_LOGGING),
            ("cogs.leveling",    config.ENABLE_LEVELING),
            ("cogs.economy",     config.ENABLE_ECONOMY),
            ("cogs.tickets",     config.ENABLE_TICKETS),
            ("cogs.automod",     config.ENABLE_AUTOMOD),
            ("cogs.roles",       config.ENABLE_ROLES),
            ("cogs.customcmds",  config.ENABLE_CUSTOMCMDS),
            ("cogs.developer",   config.ENABLE_DEVELOPER),
            ("cogs.games",       True),
        ]
        for cog, enabled in cogs:
            if not enabled:
                continue
            try:
                await self.load_extension(cog)
                log.info(f"✅  Loaded: {cog}")
            except Exception as e:
                log.error(f"❌  Failed to load {cog}: {e}")

    async def _sync_commands(self):
        if config.GUILD_ID:
            guild = discord.Object(id=config.GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            log.info(f"⚡  Commands synced to guild {config.GUILD_ID}")
        else:
            await self.tree.sync()
            log.info("🌐  Commands synced globally")

    async def on_ready(self):
        log.info(f"🤖  Logged in as {self.user} (ID: {self.user.id})")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{len(self.guilds)} servers | /help",
            )
        )

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.CommandNotFound):
            return
        log.error(f"Command error in {ctx.command}: {error}")

    async def close(self):
        await close_pool()
        await super().close()


async def main():
    if not config.TOKEN:
        log.critical("DISCORD_TOKEN is not set.")
        return
    async with AdaptBot() as bot:
        await bot.start(config.TOKEN)


if __name__ == "__main__":
    acquire_lock()
    atexit.register(release_lock)
    asyncio.run(main())
