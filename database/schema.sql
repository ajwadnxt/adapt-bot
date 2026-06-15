-- PostgreSQL Database Schema for Adapt Discord Bot

-- 1. Guild Settings
CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id BIGINT PRIMARY KEY,
    prefix VARCHAR(10) DEFAULT '.',
    
    -- Leveling Settings
    leveling_enabled BOOLEAN DEFAULT TRUE,
    xp_cooldown INT DEFAULT 60, -- seconds
    xp_min INT DEFAULT 15,
    xp_max INT DEFAULT 25,
    level_up_message TEXT DEFAULT '🎉 {user} has reached level {level}!',
    level_up_channel_id BIGINT,

    -- Economy Settings
    economy_enabled BOOLEAN DEFAULT TRUE,
    currency_name VARCHAR(32) DEFAULT 'coins',
    currency_emoji VARCHAR(32) DEFAULT '🪙',
    daily_amount INT DEFAULT 100,

    -- Ticket Settings
    ticket_category_id BIGINT,
    ticket_support_role_id BIGINT,

    -- Log Settings
    log_channel_id BIGINT,
    mod_log_channel_id BIGINT,

    -- AutoMod Settings
    automod_enabled BOOLEAN DEFAULT FALSE,
    automod_spam BOOLEAN DEFAULT FALSE,
    automod_links BOOLEAN DEFAULT FALSE,
    automod_badwords BOOLEAN DEFAULT FALSE,
    automod_badwords_list TEXT[] DEFAULT '{}',
    automod_log_channel_id BIGINT,

    -- Giveaway Settings
    giveaway_emoji VARCHAR(64) DEFAULT '🎉',
    giveaway_color INT DEFAULT 5869821, -- Hex 0x5990FD
    giveaway_ping_role_id BIGINT,
    giveaway_pin BOOLEAN DEFAULT FALSE
);


-- 2. Mod Logs
CREATE TABLE IF NOT EXISTS mod_logs (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    target_id BIGINT NOT NULL,
    moderator_id BIGINT NOT NULL,
    action VARCHAR(32) NOT NULL,
    reason TEXT,
    duration INT, -- in seconds (for temporary mutes/bans)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. Warnings
CREATE TABLE IF NOT EXISTS warnings (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    moderator_id BIGINT NOT NULL,
    reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4. Levels / XP
CREATE TABLE IF NOT EXISTS levels (
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    xp INT DEFAULT 0,
    level INT DEFAULT 0,
    last_message_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (guild_id, user_id)
);

-- 5. Level Roles
CREATE TABLE IF NOT EXISTS level_roles (
    guild_id BIGINT NOT NULL,
    level INT NOT NULL,
    role_id BIGINT NOT NULL,
    PRIMARY KEY (guild_id, level)
);

-- 6. Economy Accounts
CREATE TABLE IF NOT EXISTS economy (
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    balance BIGINT DEFAULT 0,
    bank BIGINT DEFAULT 0,
    last_daily TIMESTAMP WITH TIME ZONE,
    last_work TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (guild_id, user_id)
);

-- 7. Shop Items
CREATE TABLE IF NOT EXISTS shop_items (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    name VARCHAR(64) NOT NULL,
    description TEXT,
    price INT NOT NULL,
    role_id BIGINT,
    stock INT
);

-- 8. Tickets
CREATE TABLE IF NOT EXISTS tickets (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    channel_id BIGINT UNIQUE NOT NULL,
    user_id BIGINT NOT NULL,
    topic TEXT,
    status VARCHAR(16) DEFAULT 'open',
    closed_at TIMESTAMP WITH TIME ZONE
);

-- 9. Reaction Roles
CREATE TABLE IF NOT EXISTS reaction_roles (
    guild_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    emoji VARCHAR(64) NOT NULL,
    role_id BIGINT NOT NULL,
    PRIMARY KEY (message_id, emoji)
);

-- 10. Custom Commands
CREATE TABLE IF NOT EXISTS custom_commands (
    guild_id BIGINT NOT NULL,
    name VARCHAR(64) NOT NULL,
    response TEXT NOT NULL,
    created_by BIGINT NOT NULL,
    uses INT DEFAULT 0,
    PRIMARY KEY (guild_id, name)
);

-- 11. AutoMod Logs
CREATE TABLE IF NOT EXISTS automod_logs (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    rule VARCHAR(32) NOT NULL,
    content TEXT,
    action_taken VARCHAR(64) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 12. Giveaways
CREATE TABLE IF NOT EXISTS giveaways (
    message_id BIGINT PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    prize TEXT NOT NULL,
    description TEXT,
    winners_count INT NOT NULL DEFAULT 1,
    end_time TIMESTAMP WITH TIME ZONE NOT NULL,
    host_id BIGINT NOT NULL,
    participants BIGINT[] DEFAULT '{}',
    winners BIGINT[] DEFAULT '{}',
    status VARCHAR(20) NOT NULL DEFAULT 'active'
);
