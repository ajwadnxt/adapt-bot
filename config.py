import os
from dotenv import load_dotenv

load_dotenv()

#CoreSettings
TOKEN: str = os.getenv("DISCORD_TOKEN", "")
PREFIX: str = os.getenv("BOT_PREFIX", "!")

#InstantSyncOnlyForTesting
GUILD_ID: int | None = int(gid) if (gid := os.getenv("GUILD_ID")) else None

#BotAppearance
BOT_NAME = "MyBot"
BOT_COLOR = "#00a9ff"
BOT_VERSION = "1.0.0"

#FeatureFlags
ENABLE_MODERATION = True
ENABLE_UTILITY = True
