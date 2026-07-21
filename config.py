import os
from dotenv import load_dotenv

load_dotenv()

# ─── Core ─────────────────────────────────────────────────────────────────────
TOKEN: str           = os.getenv("DISCORD_TOKEN", "")
PREFIX: str          = os.getenv("BOT_PREFIX", ".")
GUILD_ID: int | None = int(gid) if (gid := os.getenv("GUILD_ID")) else None
DATABASE_URL: str    = os.getenv("DATABASE_URL", "")
OWNER_IDS: list[int] = [int(i) for i in os.getenv("OWNER_IDS", "").split(",") if i.strip()]

# ─── Appearance ───────────────────────────────────────────────────────────────
BOT_NAME    = "Adapt"
BOT_COLOR   = 0x5990FD
BOT_VERSION = "2.2.0"

# ─── Lavalink ─────────────────────────────────────────────────────────────────
LAVALINK_URI      = os.getenv("LAVALINK_URI",      "http://lavalink.jirayu.net:13592")
LAVALINK_PASSWORD = os.getenv("LAVALINK_PASSWORD", "youshallnotpass")

# ─── Twitch Alerts ────────────────────────────────────────────────────────────
# Get these from https://dev.twitch.tv/console/apps
TWITCH_CLIENT_ID     = os.getenv("TWITCH_CLIENT_ID",     "")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET", "")

# ─── Feature Flags ────────────────────────────────────────────────────────────
ENABLE_MODERATION   = True
ENABLE_UTILITY      = True
ENABLE_WELCOME      = True
ENABLE_LOGGING      = True
ENABLE_LEVELING     = True
ENABLE_ECONOMY      = True
ENABLE_TICKETS      = True
ENABLE_AUTOMOD      = True
ENABLE_ROLES        = True
ENABLE_CUSTOMCMDS   = True
ENABLE_SETTINGS     = True
ENABLE_DEVELOPER    = True
ENABLE_GIVEAWAY     = True
ENABLE_GAMES        = True
ENABLE_MUSIC        = True
ENABLE_STATS        = True
ENABLE_INVITES      = True
ENABLE_ALERTS       = True
ENABLE_LEADERBOARD  = True