import logging
import asyncpg
import config

log = logging.getLogger("db")

_pool: asyncpg.Pool | None = None


#Pool

async def create_pool() -> asyncpg.Pool:
    global _pool
    _pool = await asyncpg.create_pool(dsn=config.DATABASE_URL, min_size=1, max_size=5, command_timeout=60)
    log.info("✅  Database pool created")
    return _pool

async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        log.info("🔌  Database pool closed")

def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool has not been initialised yet.")
    return _pool


#GuildSettings

async def get_guild(guild_id: int) -> asyncpg.Record | None:
    if _pool is None:
        return None
    return await get_pool().fetchrow("SELECT * FROM guild_settings WHERE guild_id = $1", guild_id)

async def ensure_guild(guild_id: int) -> asyncpg.Record | dict:
    """Get guild settings, creating a default row if it doesn't exist."""
    if _pool is None:
        return {
            "guild_id": guild_id,
            "prefix": config.PREFIX,
            "welcome_channel_id": None,
            "leave_channel_id": None,
            "welcome_embed": True,
            "welcome_message": "Welcome {user} to the server!",
            "leave_message": "{name} has left the server.",
            "mod_log_channel_id": None,
            "mute_role_id": None,
            "log_channel_id": None,
            "xp_cooldown": 60,
            "min_xp": 15,
            "max_xp": 25,
            "level_up_message": "GG {user}, you level up to level {level}!",
            "level_up_channel_id": None,
            "currency_name": "Coins",
            "currency_symbol": "🪙",
            "daily_amount": 100,
            "ticket_category_id": None,
            "ticket_support_role_id": None,
            "link_whitelisted_channels": [],
            "automod_invites": False,
            "automod_links": False,
            "automod_spam": False,
            "automod_mentions": False,
            "auto_role_ids": [],
        }
    row = await get_guild(guild_id)
    if not row:
        await get_pool().execute(
            "INSERT INTO guild_settings (guild_id) VALUES ($1) ON CONFLICT DO NOTHING", guild_id
        )
        row = await get_guild(guild_id)
    return row

async def set_guild(guild_id: int, **kwargs) -> None:
    """Update one or more guild_settings columns."""
    if _pool is None:
        return
    if not kwargs:
        return
    cols = ", ".join(f"{k} = ${i+2}" for i, k in enumerate(kwargs))
    await get_pool().execute(
        f"UPDATE guild_settings SET {cols} WHERE guild_id = $1",
        guild_id, *kwargs.values()
    )


async def get_prefix(guild_id: int) -> str:
    if _pool is None:
        return config.PREFIX
    row = await get_guild(guild_id)
    return row["prefix"] if row else config.PREFIX



#ModLogs

async def add_mod_log(guild_id, target_id, moderator_id, action, reason=None, duration=None) -> int:
    row = await get_pool().fetchrow(
        "INSERT INTO mod_logs (guild_id, target_id, moderator_id, action, reason, duration) VALUES ($1,$2,$3,$4,$5,$6) RETURNING id",
        guild_id, target_id, moderator_id, action, reason, duration
    )
    return row["id"]

async def get_mod_logs(guild_id: int, target_id: int) -> list:
    return await get_pool().fetch(
        "SELECT * FROM mod_logs WHERE guild_id=$1 AND target_id=$2 ORDER BY created_at DESC", guild_id, target_id
    )


#Warnings

async def add_warning(guild_id, user_id, moderator_id, reason) -> int:
    row = await get_pool().fetchrow(
        "INSERT INTO warnings (guild_id, user_id, moderator_id, reason) VALUES ($1,$2,$3,$4) RETURNING id",
        guild_id, user_id, moderator_id, reason
    )
    return row["id"]

async def get_warnings(guild_id: int, user_id: int) -> list:
    return await get_pool().fetch(
        "SELECT * FROM warnings WHERE guild_id=$1 AND user_id=$2 ORDER BY created_at DESC", guild_id, user_id
    )

async def clear_warnings(guild_id: int, user_id: int) -> int:
    result = await get_pool().execute("DELETE FROM warnings WHERE guild_id=$1 AND user_id=$2", guild_id, user_id)
    return int(result.split()[-1])


#Leveling

async def get_level(guild_id: int, user_id: int) -> asyncpg.Record | None:
    return await get_pool().fetchrow("SELECT * FROM levels WHERE guild_id=$1 AND user_id=$2", guild_id, user_id)

async def add_xp(guild_id: int, user_id: int, xp: int) -> asyncpg.Record:
    return await get_pool().fetchrow(
        """INSERT INTO levels (guild_id, user_id, xp, last_message_at) VALUES ($1,$2,$3,NOW())
           ON CONFLICT (guild_id, user_id) DO UPDATE SET xp=levels.xp+EXCLUDED.xp, last_message_at=NOW()
           RETURNING *""",
        guild_id, user_id, xp
    )

async def set_level(guild_id: int, user_id: int, level: int) -> None:
    await get_pool().execute("UPDATE levels SET level=$3 WHERE guild_id=$1 AND user_id=$2", guild_id, user_id, level)

async def get_leaderboard(guild_id: int, limit: int = 10) -> list:
    return await get_pool().fetch("SELECT * FROM levels WHERE guild_id=$1 ORDER BY xp DESC LIMIT $2", guild_id, limit)

async def get_level_roles(guild_id: int) -> list:
    return await get_pool().fetch("SELECT * FROM level_roles WHERE guild_id=$1 ORDER BY level", guild_id)

async def set_level_role(guild_id: int, level: int, role_id: int) -> None:
    await get_pool().execute(
        "INSERT INTO level_roles (guild_id, level, role_id) VALUES ($1,$2,$3) ON CONFLICT (guild_id, level) DO UPDATE SET role_id=$3",
        guild_id, level, role_id
    )

async def remove_level_role(guild_id: int, level: int) -> None:
    await get_pool().execute("DELETE FROM level_roles WHERE guild_id=$1 AND level=$2", guild_id, level)


#Economy

async def get_economy(guild_id: int, user_id: int) -> asyncpg.Record | None:
    return await get_pool().fetchrow("SELECT * FROM economy WHERE guild_id=$1 AND user_id=$2", guild_id, user_id)

async def ensure_economy(guild_id: int, user_id: int) -> asyncpg.Record:
    await get_pool().execute(
        "INSERT INTO economy (guild_id, user_id) VALUES ($1,$2) ON CONFLICT DO NOTHING", guild_id, user_id
    )
    return await get_economy(guild_id, user_id)

async def add_balance(guild_id: int, user_id: int, amount: int) -> asyncpg.Record:
    return await get_pool().fetchrow(
        "UPDATE economy SET balance=balance+$3 WHERE guild_id=$1 AND user_id=$2 RETURNING *",
        guild_id, user_id, amount
    )

async def set_daily(guild_id: int, user_id: int) -> None:
    await get_pool().execute("UPDATE economy SET last_daily=NOW() WHERE guild_id=$1 AND user_id=$2", guild_id, user_id)

async def get_economy_leaderboard(guild_id: int, limit: int = 10) -> list:
    return await get_pool().fetch(
        "SELECT * FROM economy WHERE guild_id=$1 ORDER BY balance+bank DESC LIMIT $2", guild_id, limit
    )


#Shop

async def get_shop(guild_id: int) -> list:
    return await get_pool().fetch("SELECT * FROM shop_items WHERE guild_id=$1 ORDER BY price", guild_id)

async def get_shop_item(item_id: int) -> asyncpg.Record | None:
    return await get_pool().fetchrow("SELECT * FROM shop_items WHERE id=$1", item_id)

async def add_shop_item(guild_id, name, description, price, role_id=None, stock=None) -> int:
    row = await get_pool().fetchrow(
        "INSERT INTO shop_items (guild_id, name, description, price, role_id, stock) VALUES ($1,$2,$3,$4,$5,$6) RETURNING id",
        guild_id, name, description, price, role_id, stock
    )
    return row["id"]

async def remove_shop_item(item_id: int) -> None:
    await get_pool().execute("DELETE FROM shop_items WHERE id=$1", item_id)


#Tickets

async def create_ticket(guild_id, channel_id, user_id, topic=None) -> int:
    row = await get_pool().fetchrow(
        "INSERT INTO tickets (guild_id, channel_id, user_id, topic) VALUES ($1,$2,$3,$4) RETURNING id",
        guild_id, channel_id, user_id, topic
    )
    return row["id"]

async def get_ticket(channel_id: int) -> asyncpg.Record | None:
    return await get_pool().fetchrow("SELECT * FROM tickets WHERE channel_id=$1", channel_id)

async def close_ticket(channel_id: int) -> None:
    await get_pool().execute(
        "UPDATE tickets SET status='closed', closed_at=NOW() WHERE channel_id=$1", channel_id
    )

async def get_user_open_ticket(guild_id: int, user_id: int) -> asyncpg.Record | None:
    return await get_pool().fetchrow(
        "SELECT * FROM tickets WHERE guild_id=$1 AND user_id=$2 AND status='open'", guild_id, user_id
    )


#ReactionRoles

async def add_reaction_role(guild_id, channel_id, message_id, emoji, role_id) -> None:
    await get_pool().execute(
        "INSERT INTO reaction_roles (guild_id, channel_id, message_id, emoji, role_id) VALUES ($1,$2,$3,$4,$5) ON CONFLICT (message_id, emoji) DO UPDATE SET role_id=$5",
        guild_id, channel_id, message_id, emoji, role_id
    )

async def get_reaction_role(message_id: int, emoji: str) -> asyncpg.Record | None:
    return await get_pool().fetchrow("SELECT * FROM reaction_roles WHERE message_id=$1 AND emoji=$2", message_id, emoji)

async def get_reaction_roles(guild_id: int) -> list:
    return await get_pool().fetch("SELECT * FROM reaction_roles WHERE guild_id=$1", guild_id)

async def remove_reaction_role(message_id: int, emoji: str) -> None:
    await get_pool().execute("DELETE FROM reaction_roles WHERE message_id=$1 AND emoji=$2", message_id, emoji)


#CustomCommands

async def get_custom_command(guild_id: int, name: str) -> asyncpg.Record | None:
    return await get_pool().fetchrow("SELECT * FROM custom_commands WHERE guild_id=$1 AND name=$2", guild_id, name)

async def get_custom_commands(guild_id: int) -> list:
    return await get_pool().fetch("SELECT * FROM custom_commands WHERE guild_id=$1 ORDER BY name", guild_id)

async def add_custom_command(guild_id, name, response, created_by) -> None:
    await get_pool().execute(
        "INSERT INTO custom_commands (guild_id, name, response, created_by) VALUES ($1,$2,$3,$4)",
        guild_id, name, response, created_by
    )

async def edit_custom_command(guild_id, name, response) -> None:
    await get_pool().execute("UPDATE custom_commands SET response=$3 WHERE guild_id=$1 AND name=$2", guild_id, name, response)

async def delete_custom_command(guild_id: int, name: str) -> None:
    await get_pool().execute("DELETE FROM custom_commands WHERE guild_id=$1 AND name=$2", guild_id, name)

async def increment_command_uses(guild_id: int, name: str) -> None:
    await get_pool().execute("UPDATE custom_commands SET uses=uses+1 WHERE guild_id=$1 AND name=$2", guild_id, name)


#Automod

async def add_automod_log(guild_id, user_id, rule, content=None, action_taken=None) -> None:
    await get_pool().execute(
        "INSERT INTO automod_logs (guild_id, user_id, rule, content, action_taken) VALUES ($1,$2,$3,$4,$5)",
        guild_id, user_id, rule, content, action_taken
    )
