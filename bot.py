import asyncio
import logging
import discord
from discord.ext import commands
import config
from database.db import create_pool, close_pool

#Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("bot")

#Intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

#BotSubclass
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=config.PREFIX,
            intents=intents,
            help_command=None,
        )

    #ThingsToDoBeforeTheBotConnects
    async def setup_hook(self):
        if config.DATABASE_URL:
            self.db_pool = await create_pool()
        else:
            log.warning("⚠️  DATABASE_URL not set — running without database")
            self.db_pool = None
        await self._load_cogs()
        await self._sync_commands()

    async def close(self):
        await close_pool()
        await super().close()

    async def _load_cogs(self):
        cogs = ["cogs.general"]
        if config.ENABLE_MODERATION:
            cogs.append("cogs.moderation")
        if config.ENABLE_UTILITY:
            cogs.append("cogs.utility")

        for cog in cogs:
            try:
                await self.load_extension(cog)
                log.info(f"✅  Loaded cog: {cog}")
            except Exception as e:
                log.error(f"❌  Failed to load cog {cog}: {e}")

    async def _sync_commands(self):
        if config.GUILD_ID:
            guild = discord.Object(id=config.GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            log.info(f"⚡  Slash commands synced to dev guild {config.GUILD_ID}")
        else:
            await self.tree.sync()
            log.info("🌐  Slash commands synced globally (may take up to 1 hour)")

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
            return  # Silently ignore unknown prefix commands
        log.error(f"Prefix command error in {ctx.command}: {error}")


#Entry Point
async def main():
    if not config.TOKEN:
        log.critical("DISCORD_TOKEN is not set. Check your .env file.")
        return

    async with MyBot() as bot:
        await bot.start(config.TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
