import os
from dotenv import load_dotenv

load_dotenv()

#Core
TOKEN: str           = os.getenv("DISCORD_TOKEN", "")
PREFIX: str          = os.getenv("BOT_PREFIX", ".")
GUILD_ID: int | None = int(gid) if (gid := os.getenv("GUILD_ID")) else None
DATABASE_URL: str    = os.getenv("DATABASE_URL", "")
OWNER_IDS: list[int] = [int(i) for i in os.getenv("OWNER_IDS", "").split(",") if i.strip()]

#Appearance
BOT_NAME    = "Adapt"
BOT_COLOR   = 0x5990FD
BOT_VERSION = "2.0.0"

#FeatureFlags
ENABLE_MODERATION  = True
ENABLE_UTILITY     = True
ENABLE_WELCOME     = True
ENABLE_LOGGING     = True
ENABLE_LEVELING    = True
ENABLE_ECONOMY     = True
ENABLE_TICKETS     = True
ENABLE_AUTOMOD     = True
ENABLE_ROLES       = True
ENABLE_CUSTOMCMDS  = True
ENABLE_SETTINGS    = True
ENABLE_DEVELOPER   = True
ENABLE_GIVEAWAY    = True

