import logging
import asyncpg
import config

log = logging.getLogger("db")

#ConnectionPool

_pool: asyncpg.Pool | None = None


async def create_pool() -> asyncpg.Pool:
    """Create and return the global connection pool. Call once on startup."""
    global _pool
    _pool = await asyncpg.create_pool(
        dsn=config.DATABASE_URL,
        min_size=1,
        max_size=5,          # Keep low for free tier
        command_timeout=60,
    )
    log.info("✅  Database pool created")
    return _pool


async def close_pool():
    """Gracefully close the pool on shutdown."""
    global _pool
    if _pool:
        await _pool.close()
        log.info("🔌  Database pool closed")


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool has not been initialised yet.")
    return _pool


#GuildSettings

async def get_guild_settings(guild_id: int) -> asyncpg.Record | None:
    pool = get_pool()
    return await pool.fetchrow(
        "SELECT * FROM guild_settings WHERE guild_id = $1", guild_id
    )


async def upsert_guild_settings(guild_id: int, **kwargs) -> None:
    """Create or update settings for a guild. Pass column=value kwargs."""
    pool = get_pool()

    # Build SET clause dynamically from provided kwargs
    columns = ", ".join(kwargs.keys())
    placeholders = ", ".join(f"${i+2}" for i in range(len(kwargs)))
    updates = ", ".join(f"{k} = EXCLUDED.{k}" for k in kwargs)

    query = f"""
        INSERT INTO guild_settings (guild_id, {columns})
        VALUES ($1, {placeholders})
        ON CONFLICT (guild_id) DO UPDATE SET {updates}
    """
    await pool.execute(query, guild_id, *kwargs.values())


async def get_prefix(guild_id: int) -> str:
    """Return the guild's custom prefix, falling back to config default."""
    row = await get_guild_settings(guild_id)
    return row["prefix"] if row else config.PREFIX


#ModLogs

async def add_mod_log(
    guild_id: int,
    target_id: int,
    moderator_id: int,
    action: str,
    reason: str | None = None,
    duration: int | None = None,
) -> int:
    """Insert a mod action and return its new ID."""
    pool = get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO mod_logs (guild_id, target_id, moderator_id, action, reason, duration)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id
        """,
        guild_id, target_id, moderator_id, action, reason, duration,
    )
    return row["id"]


async def get_mod_logs(guild_id: int, target_id: int) -> list[asyncpg.Record]:
    """Fetch all mod actions for a user in a guild."""
    pool = get_pool()
    return await pool.fetch(
        """
        SELECT * FROM mod_logs
        WHERE guild_id = $1 AND target_id = $2
        ORDER BY created_at DESC
        """,
        guild_id, target_id,
    )


#Warnings

async def add_warning(
    guild_id: int, user_id: int, moderator_id: int, reason: str
) -> int:
    pool = get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO warnings (guild_id, user_id, moderator_id, reason)
        VALUES ($1, $2, $3, $4)
        RETURNING id
        """,
        guild_id, user_id, moderator_id, reason,
    )
    return row["id"]


async def get_warnings(guild_id: int, user_id: int) -> list[asyncpg.Record]:
    pool = get_pool()
    return await pool.fetch(
        "SELECT * FROM warnings WHERE guild_id = $1 AND user_id = $2 ORDER BY created_at DESC",
        guild_id, user_id,
    )


async def clear_warnings(guild_id: int, user_id: int) -> int:
    """Delete all warnings for a user. Returns number of rows deleted."""
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM warnings WHERE guild_id = $1 AND user_id = $2",
        guild_id, user_id,
    )
    return int(result.split()[-1])


#Levels

async def get_level(guild_id: int, user_id: int) -> asyncpg.Record | None:
    pool = get_pool()
    return await pool.fetchrow(
        "SELECT * FROM levels WHERE guild_id = $1 AND user_id = $2",
        guild_id, user_id,
    )


async def add_xp(guild_id: int, user_id: int, xp: int) -> asyncpg.Record:
    """Add XP to a user and return their updated row."""
    pool = get_pool()
    return await pool.fetchrow(
        """
        INSERT INTO levels (guild_id, user_id, xp, last_message_at)
        VALUES ($1, $2, $3, NOW())
        ON CONFLICT (guild_id, user_id) DO UPDATE
            SET xp              = levels.xp + EXCLUDED.xp,
                last_message_at = NOW()
        RETURNING *
        """,
        guild_id, user_id, xp,
    )


async def get_leaderboard(guild_id: int, limit: int = 10) -> list[asyncpg.Record]:
    pool = get_pool()
    return await pool.fetch(
        "SELECT * FROM levels WHERE guild_id = $1 ORDER BY xp DESC LIMIT $2",
        guild_id, limit,
    )
