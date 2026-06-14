import discord
import config


def success(title: str, description: str = None) -> discord.Embed:
    return discord.Embed(title=f"✅ {title}", description=description, color=discord.Color.green())

def error(title: str, description: str = None) -> discord.Embed:
    return discord.Embed(title=f"❌ {title}", description=description, color=discord.Color.red())

def warning(title: str, description: str = None) -> discord.Embed:
    return discord.Embed(title=f"⚠️ {title}", description=description, color=discord.Color.yellow())

def info(title: str, description: str = None) -> discord.Embed:
    return discord.Embed(title=f"ℹ️ {title}", description=description, color=config.BOT_COLOR)

def mod_action(action: str, target: discord.Member, moderator: discord.Member, reason: str, **extras) -> discord.Embed:
    icons = {"ban": "🔨", "kick": "👢", "mute": "🔇", "warn": "⚠️", "timeout": "⏱️", "unban": "✅"}
    colors = {
        "ban": discord.Color.red(), "kick": discord.Color.orange(),
        "mute": discord.Color.gold(), "warn": discord.Color.yellow(),
        "timeout": discord.Color.gold(), "unban": discord.Color.green(),
    }
    embed = discord.Embed(
        title=f"{icons.get(action, '🔨')} {action.title()}",
        color=colors.get(action, config.BOT_COLOR),
    )
    embed.add_field(name="Member", value=f"{target.mention} (`{target}`)")
    embed.add_field(name="Moderator", value=moderator.mention)
    embed.add_field(name="Reason", value=reason, inline=False)
    for k, v in extras.items():
        embed.add_field(name=k.replace("_", " ").title(), value=str(v))
    embed.set_thumbnail(url=target.display_avatar.url)
    return embed

def log_event(title: str, color: discord.Color = None, **fields) -> discord.Embed:
    embed = discord.Embed(title=title, color=color or config.BOT_COLOR)
    for k, v in fields.items():
        embed.add_field(name=k.replace("_", " ").title(), value=str(v), inline=len(str(v)) < 50)
    import datetime
    embed.timestamp = datetime.datetime.utcnow()
    return embed
