import os
from dotenv import load_dotenv

load_dotenv()

#CoreSettings
TOKEN: str = os.getenv("DISCORD_TOKEN", "")
PREFIX: str = os.getenv("BOT_PREFIX", "!")


#Database
DATABASE_URL: str = os.getenv("DATABASE_URL", "")


#InstantSyncOnlyForTesting
GUILD_ID: int | None = int(gid) if (gid := os.getenv("GUILD_ID")) else None

#BotAppearance
BOT_NAME = "ADAPT v0.1 alpha"
BOT_COLOR = "#00a9ff"
BOT_VERSION = "0.0.1"

#FeatureFlags
ENABLE_MODERATION = True
ENABLE_UTILITY = True
