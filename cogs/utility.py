import os
import ast
import operator
import random
import re
import json
import asyncio
import aiohttp
import urllib.parse
import discord
from discord import app_commands
from discord.ext import commands
import config
import time
import logging

log = logging.getLogger("bot.utility")

# Math operations mapping for safe evaluator
MATH_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
}

def safe_math_eval(node):
    if isinstance(node, ast.Constant):
        return node.value
    elif isinstance(node, ast.BinOp):
        op = type(node.op)
        if op in MATH_OPERATORS:
            return MATH_OPERATORS[op](safe_math_eval(node.left), safe_math_eval(node.right))
    elif isinstance(node, ast.UnaryOp):
        op = type(node.op)
        if op in MATH_OPERATORS:
            return MATH_OPERATORS[op](safe_math_eval(node.operand))
    raise TypeError(f"Unsupported node type: {type(node)}")

def evaluate_math_expr(expr: str):
    try:
        # replace standard symbols like ^ with ** for power evaluation
        clean_expr = expr.replace("^", "**").replace("x", "*").replace(" ", "")
        node = ast.parse(clean_expr, mode='eval').body
        return safe_math_eval(node)
    except Exception as e:
        raise ValueError(f"Invalid syntax or unsupported operator: {e}")

def parse_duration(time_str: str) -> int | None:
    """Parse standard time format (e.g. 5m, 1h, 30s) into seconds."""
    match = re.match(r"^(\d+)([shmd])$", time_str.lower().strip())
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2)
    if unit == 's':
        return amount
    elif unit == 'm':
        return amount * 60
    elif unit == 'h':
        return amount * 3600
    elif unit == 'd':
        return amount * 86400
    return None


class Utility(commands.Cog):
    """Handy utility commands for getting info about users and the server."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.start_time = time.time()


    @app_commands.command(name="avatar", description="Get a user's avatar.")
    @app_commands.describe(member="The member whose avatar you want (defaults to you)")
    async def avatar(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
    ):
        target = member or interaction.user
        avatar_url = target.display_avatar.url
        embed = discord.Embed(
            title=f"🖼️ {target.display_name}'s Avatar",
            color=config.BOT_COLOR,
        )
        embed.set_image(url=avatar_url)
        embed.add_field(
            name="Download",
            value=f"[Click here]({avatar_url})",
        )
        await interaction.response.send_message(embed=embed)


    @app_commands.command(name="userinfo", description="Show info about a member.")
    @app_commands.describe(member="The member to inspect (defaults to you)")
    async def userinfo(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
    ):
        target = member or interaction.user   # type: ignore[assignment]
        roles = [r.mention for r in target.roles[1:]]  # Skip @everyone

        embed = discord.Embed(
            title=f"👤 {target}",
            color=target.color if target.color.value else config.BOT_COLOR,
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="ID", value=str(target.id), inline=True)
        embed.add_field(name="Nickname", value=target.nick or "None", inline=True)
        embed.add_field(name="Bot?", value="Yes" if target.bot else "No", inline=True)
        embed.add_field(
            name="Account Created",
            value=discord.utils.format_dt(target.created_at, style="R"),
            inline=True,
        )
        embed.add_field(
            name="Joined Server",
            value=discord.utils.format_dt(target.joined_at, style="R") if target.joined_at else "Unknown",
            inline=True,
        )
        embed.add_field(
            name=f"Roles ({len(roles)})",
            value=" ".join(roles) if roles else "None",
            inline=False,
        )
        await interaction.response.send_message(embed=embed)


    @app_commands.command(name="serverinfo", description="Show info about this server.")
    async def serverinfo(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ This command must be used in a server.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"🏠 {guild.name}",
            color=config.BOT_COLOR,
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(name="ID", value=str(guild.id), inline=True)
        embed.add_field(name="Owner", value=str(guild.owner), inline=True)
        embed.add_field(name="Members", value=str(guild.member_count), inline=True)
        embed.add_field(name="Channels", value=str(len(guild.channels)), inline=True)
        embed.add_field(name="Roles", value=str(len(guild.roles)), inline=True)
        embed.add_field(name="Boost Level", value=str(guild.premium_tier), inline=True)
        embed.add_field(
            name="Created",
            value=discord.utils.format_dt(guild.created_at, style="R"),
            inline=True,
        )
        embed.add_field(
            name="Verification Level",
            value=str(guild.verification_level).title(),
            inline=True,
        )
        await interaction.response.send_message(embed=embed)


    @app_commands.command(name="embed", description="Send a custom embed message.")
    @app_commands.describe(
        description="The description content of the embed (use \\n for new lines)",
        title="The title of the embed",
        color="Hex color code (e.g. #FF5733 or FF5733)",
        channel="The channel to send the embed to (defaults to current)",
        thumbnail="URL of the thumbnail image",
        image="URL of the main image",
        footer="Footer text of the embed"
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def embed(
        self,
        interaction: discord.Interaction,
        description: str,
        title: str | None = None,
        color: str | None = None,
        channel: discord.TextChannel | None = None,
        thumbnail: str | None = None,
        image: str | None = None,
        footer: str | None = None
    ):
        target_channel = channel or interaction.channel # type: ignore[assignment]
        processed_desc = description.replace("\\n", "\n")

        embed_color = config.BOT_COLOR
        if color:
            cleaned_color = color.strip().lstrip("#")
            try:
                embed_color = int(cleaned_color, 16)
            except ValueError:
                await interaction.response.send_message(
                    "❌ Invalid hex color code. Please use format `#HEX` (e.g. `#FF5733`) or `HEX` (e.g. `FF5733`).",
                    ephemeral=True
                )
                return

        new_embed = discord.Embed(
            title=title,
            description=processed_desc,
            color=embed_color
        )

        if thumbnail:
            if thumbnail.startswith(("http://", "https://")):
                new_embed.set_thumbnail(url=thumbnail.strip())
            else:
                await interaction.response.send_message(
                    "❌ Invalid thumbnail URL. It must start with http:// or https://",
                    ephemeral=True
                )
                return

        if image:
            if image.startswith(("http://", "https://")):
                new_embed.set_image(url=image.strip())
            else:
                await interaction.response.send_message(
                    "❌ Invalid image URL. It must start with http:// or https://",
                    ephemeral=True
                )
                return

        if footer:
            new_embed.set_footer(text=footer)

        try:
            await target_channel.send(embed=new_embed)
        except discord.Forbidden:
            await interaction.response.send_message(
                f"❌ I don't have permission to send messages in {target_channel.mention}.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"✅ Embed sent successfully to {target_channel.mention}!",
            ephemeral=True
        )


    @app_commands.command(name="calculate", description="Safely evaluate a mathematical expression.")
    @app_commands.describe(expression="The math expression to evaluate (e.g. 2 + 2 * 5 or (10 / 2) ^ 3)")
    async def calculate(self, interaction: discord.Interaction, expression: str):
        try:
            result = evaluate_math_expr(expression)
            embed = discord.Embed(
                title="🧮 Calculator",
                color=config.BOT_COLOR
            )
            embed.add_field(name="Expression", value=f"```\n{expression}\n```", inline=False)
            embed.add_field(name="Result", value=f"```\n{result}\n```", inline=False)
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            embed = discord.Embed(
                title="❌ Calculator Error",
                description=f"Could not evaluate expression: `{expression}`\n\n> **Error:** {str(e)}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="choose", description="Randomly choose an option from a list.")
    @app_commands.describe(choices="Options separated by commas (e.g. pizza, burger, pasta)")
    async def choose(self, interaction: discord.Interaction, choices: str):
        choice_list = [c.strip() for c in choices.split(",") if c.strip()]
        if not choice_list:
            await interaction.response.send_message("❌ Please provide at least one choice.", ephemeral=True)
            return

        chosen = random.choice(choice_list)
        embed = discord.Embed(
            title="🎲 Random Choice",
            description=f"I choose: **{chosen}**",
            color=config.BOT_COLOR
        )
        embed.set_footer(text=f"Chosen from {len(choice_list)} options")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="poll", description="Create a reaction poll.")
    @app_commands.describe(
        question="The topic or question for the poll",
        choices="Up to 5 options separated by commas (leave blank for Yes/No)"
    )
    async def poll(self, interaction: discord.Interaction, question: str, choices: str | None = None):
        options = [c.strip() for c in choices.split(",") if c.strip()] if choices else []
        
        if len(options) > 5:
            await interaction.response.send_message("❌ You can specify at most 5 options.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"📊 Poll: {question}",
            color=config.BOT_COLOR
        )
        embed.set_footer(text=f"Poll created by {interaction.user.display_name}")

        reactions = []
        if options:
            reactions_map = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
            desc_lines = []
            for i, opt in enumerate(options):
                emoji = reactions_map[i]
                desc_lines.append(f"{emoji} **{opt}**")
                reactions.append(emoji)
            embed.description = "\n".join(desc_lines)
        else:
            embed.description = "👍 **Yes**\n\n👎 **No**"
            reactions = ["👍", "👎"]

        await interaction.response.send_message(embed=embed)
        response_msg = await interaction.original_response()
        
        for emoji in reactions:
            await response_msg.add_reaction(emoji)

    @app_commands.command(name="banner", description="Get a user's profile banner.")
    @app_commands.describe(member="The member whose banner you want (defaults to you)")
    async def banner(self, interaction: discord.Interaction, member: discord.Member | None = None):
        target = member or interaction.user
        await interaction.response.defer()
        
        try:
            user = await self.bot.fetch_user(target.id)
            if user.banner:
                embed = discord.Embed(
                    title=f"🖼️ {target.display_name}'s Banner",
                    color=config.BOT_COLOR
                )
                embed.set_image(url=user.banner.url)
                embed.add_field(name="Download", value=f"[Click here]({user.banner.url})")
                await interaction.followup.send(embed=embed)
            else:
                embed = discord.Embed(
                    title=f"❌ No Banner",
                    description=f"{target.mention} does not have a custom profile banner.",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed)
        except Exception as e:
            embed = discord.Embed(
                title="❌ Error",
                description=f"Could not retrieve banner for {target.mention}: `{e}`",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="wiki", description="Search Wikipedia for an article summary.")
    @app_commands.describe(query="The article topic to search for")
    async def wiki(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()
        encoded = urllib.parse.quote(query)
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
        headers = {
            "User-Agent": f"AdaptBot/{config.BOT_VERSION} (contact: info@adaptbot.xyz; public-discord-bot)"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        embed = discord.Embed(
                            title=data.get("title", query),
                            description=data.get("extract", "No summary extract available."),
                            color=config.BOT_COLOR
                        )
                        if "description" in data:
                            embed.add_field(name="Overview", value=data["description"], inline=False)
                        
                        desktop_url = data.get("content_urls", {}).get("desktop", {}).get("page")
                        if desktop_url:
                            embed.add_field(name="Read More", value=f"[Click here to open Wikipedia article]({desktop_url})", inline=False)
                            
                        thumbnail_url = data.get("thumbnail", {}).get("source")
                        if thumbnail_url:
                            embed.set_thumbnail(url=thumbnail_url)
                            
                        embed.set_footer(text="Information sourced from Wikipedia")
                        await interaction.followup.send(embed=embed)
                    elif resp.status == 404:
                        embed = discord.Embed(
                            title="❌ Not Found",
                            description=f"Could not find any Wikipedia article matching `{query}`.",
                            color=discord.Color.red()
                        )
                        await interaction.followup.send(embed=embed)
                    else:
                        raise RuntimeError(f"HTTP Status {resp.status}")
        except Exception as e:
            embed = discord.Embed(
                title="❌ Error",
                description=f"An error occurred while fetching Wikipedia data: `{e}`",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="roll", description="Roll virtual dice.")
    @app_commands.describe(
        dice="Number of dice to roll (default 1, max 100)",
        sides="Number of sides per die (default 6, max 1000)"
    )
    async def roll(self, interaction: discord.Interaction, dice: int = 1, sides: int = 6):
        if dice < 1 or dice > 100:
            await interaction.response.send_message("❌ Number of dice must be between 1 and 100.", ephemeral=True)
            return
        if sides < 2 or sides > 1000:
            await interaction.response.send_message("❌ Number of sides must be between 2 and 1000.", ephemeral=True)
            return

        rolls = [random.randint(1, sides) for _ in range(dice)]
        total = sum(rolls)
        
        embed = discord.Embed(
            title="🎲 Dice Roll",
            color=config.BOT_COLOR
        )
        embed.add_field(name="Dice", value=f"{dice}d{sides}", inline=True)
        embed.add_field(name="Total Sum", value=f"**{total}**", inline=True)
        
        rolls_str = ", ".join(map(str, rolls))
        if len(rolls_str) > 1000:
            rolls_str = rolls_str[:997] + "..."
        embed.add_field(name="Rolls", value=f"`{rolls_str}`", inline=False)
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="coinflip", description="Flip a coin.")
    async def coinflip(self, interaction: discord.Interaction):
        result = random.choice(["Heads", "Tails"])
        embed = discord.Embed(
            title="🪙 Coin Flip",
            description=f"The coin landed on: **{result}**!",
            color=config.BOT_COLOR
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="remind", description="Set a custom reminder.")
    @app_commands.describe(
        time="Time duration (e.g. 10s, 5m, 1h)",
        reminder="The reminder message"
    )
    async def remind(self, interaction: discord.Interaction, time: str, reminder: str):
        seconds = parse_duration(time)
        if not seconds:
            await interaction.response.send_message(
                "❌ Invalid time format. Please use a format like: `30s`, `10m`, `2h`, or `1d`.",
                ephemeral=True
            )
            return
        
        if seconds < 5:
            await interaction.response.send_message("❌ Reminders must be at least 5 seconds.", ephemeral=True)
            return
        if seconds > 86400 * 30:
            await interaction.response.send_message("❌ Reminders cannot be set for more than 30 days.", ephemeral=True)
            return
            
        embed = discord.Embed(
            title="⏰ Reminder Set",
            description=f"I will remind you in **{time}** about:\n> {reminder}",
            color=config.BOT_COLOR
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        async def reminder_task(user_id, channel_id, delay, msg_text):
            await asyncio.sleep(delay)
            user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
            if user:
                dm_embed = discord.Embed(
                    title="⏰ Reminder!",
                    description=f"You set a reminder in **{interaction.guild.name if interaction.guild else 'DMs'}**:\n\n> {msg_text}",
                    color=config.BOT_COLOR,
                    timestamp=discord.utils.utcnow()
                )
                try:
                    await user.send(embed=dm_embed)
                except discord.Forbidden:
                    channel = self.bot.get_channel(channel_id)
                    if channel:
                        try:
                            await channel.send(content=f"{user.mention}", embed=dm_embed)
                        except Exception:
                            pass

        self.bot.loop.create_task(reminder_task(interaction.user.id, interaction.channel_id, seconds, reminder))


    @app_commands.command(name="servericon", description="Get the server's icon.")
    async def servericon(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ This command must be used in a server.", ephemeral=True)
            return
        if not guild.icon:
            await interaction.response.send_message("❌ This server does not have an icon.", ephemeral=True)
            return
        
        icon_url = guild.icon.url
        embed = discord.Embed(
            title=f"🖼️ {guild.name}'s Icon",
            color=config.BOT_COLOR
        )
        embed.set_image(url=icon_url)
        embed.add_field(name="Download", value=f"[Click here]({icon_url})")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="qr", description="Generate a QR code for a link or text.")
    @app_commands.describe(text="The URL or text to encode into the QR code")
    async def qr(self, interaction: discord.Interaction, text: str):
        encoded = urllib.parse.quote(text)
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={encoded}"
        
        embed = discord.Embed(
            title="📷 QR Code Generator",
            description=f"Here is your QR code for: `{text[:100]}`",
            color=config.BOT_COLOR
        )
        embed.set_image(url=qr_url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="weather", description="Check the weather for a specific location.")
    @app_commands.describe(location="The city or region to check (e.g. London, Paris)")
    async def weather(self, interaction: discord.Interaction, location: str):
        await interaction.response.defer()
        encoded_loc = urllib.parse.quote(location)
        url = f"https://wttr.in/{encoded_loc}?format=j1"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        current = data["current_condition"][0]
                        area = data["nearest_area"][0]
                        
                        temp_c = current.get("temp_C")
                        temp_f = current.get("temp_F")
                        desc = current.get("weatherDesc")[0].get("value")
                        humidity = current.get("humidity")
                        wind = current.get("windspeedKmph")
                        feels_c = current.get("FeelsLikeC")
                        
                        city = area.get("areaName")[0].get("value")
                        country = area.get("country")[0].get("value")
                        
                        embed = discord.Embed(
                            title=f"☀️ Weather in {city}, {country}",
                            color=config.BOT_COLOR
                        )
                        embed.add_field(name="Condition", value=desc, inline=True)
                        embed.add_field(name="Temperature", value=f"{temp_c}°C ({temp_f}°F)", inline=True)
                        embed.add_field(name="Feels Like", value=f"{feels_c}°C", inline=True)
                        embed.add_field(name="Humidity", value=f"{humidity}%", inline=True)
                        embed.add_field(name="Wind Speed", value=f"{wind} km/h", inline=True)
                        
                        embed.set_footer(text="Powered by wttr.in")
                        await interaction.followup.send(embed=embed)
                    else:
                        await interaction.followup.send(f"❌ Could not find weather data for `{location}`.")
        except Exception as e:
            await interaction.followup.send(f"❌ Error fetching weather details: `{e}`")

    @app_commands.command(name="translate", description="Translate text to a specified language.")
    @app_commands.describe(
        text="The text to translate",
        language="The language code to translate to (default is 'en' for English)"
    )
    async def translate(self, interaction: discord.Interaction, text: str, language: str = "en"):
        await interaction.response.defer()
        encoded_text = urllib.parse.quote(text)
        encoded_lang = urllib.parse.quote(language)
        url = f"https://api.popcat.xyz/translate?to={encoded_lang}&text={encoded_text}"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        translated = data.get("translated")
                        if translated:
                            embed = discord.Embed(
                                title="🌐 Translation Result",
                                color=config.BOT_COLOR
                            )
                            embed.add_field(name="Original Text", value=text, inline=False)
                            embed.add_field(name=f"Translated ({language.upper()})", value=translated, inline=False)
                            await interaction.followup.send(embed=embed)
                        else:
                            await interaction.followup.send("❌ Translation failed. Please check the language code.")
                    else:
                        await interaction.followup.send("❌ Service currently unavailable.")
        except Exception as e:
            await interaction.followup.send(f"❌ Error performing translation: `{e}`")

    async def get_system_prompt(self, guild_id: int) -> str | None:
        try:
            if os.path.exists("database/chatbot_prompts.json"):
                with open("database/chatbot_prompts.json", "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get(str(guild_id))
        except Exception as e:
            pass
        return None

    async def set_system_prompt(self, guild_id: int, prompt: str) -> None:
        try:
            os.makedirs("database", exist_ok=True)
            data = {}
            if os.path.exists("database/chatbot_prompts.json"):
                with open("database/chatbot_prompts.json", "r", encoding="utf-8") as f:
                    try:
                        data = json.load(f)
                    except json.JSONDecodeError:
                        data = {}
            data[str(guild_id)] = prompt
            with open("database/chatbot_prompts.json", "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            pass

    async def execute_bot_tool(self, name: str, args: dict, guild: discord.Guild | None, caller: discord.Member | discord.User) -> dict:
        """Executes a Discord action triggered by Gemini Tool Calling and returns a response dict."""
        try:
            if name == "give_role":
                if not guild:
                    return {"status": "error", "message": "Cannot manage roles outside of a Discord server."}
                
                # Check caller permissions
                if isinstance(caller, discord.User) or not caller.guild_permissions.manage_roles:
                    return {"status": "error", "message": "Permission denied: The user requesting this action does not have 'Manage Roles' permission in this server."}
                
                # Check bot permissions
                bot_member = guild.me
                if not bot_member.guild_permissions.manage_roles:
                    return {"status": "error", "message": "Permission denied: The bot does not have 'Manage Roles' permission in this server."}
                
                user_id_str = args.get("user_id", "").strip()
                user_id_clean = "".join(filter(str.isdigit, user_id_str))
                if not user_id_clean:
                    return {"status": "error", "message": "Invalid user ID format."}
                user_id = int(user_id_clean)
                
                member = guild.get_member(user_id) or await guild.fetch_member(user_id)
                if not member:
                    return {"status": "error", "message": f"Member with ID '{user_id_str}' not found in this server."}
                
                role_name = args.get("role_name", "").strip()
                role = discord.utils.find(lambda r: r.name.lower() == role_name.lower(), guild.roles)
                if not role:
                    return {"status": "error", "message": f"Role '{role_name}' not found in this server."}
                
                # Check role hierarchy
                if role >= bot_member.top_role:
                    return {"status": "error", "message": f"Permission denied: Role '{role.name}' is higher than or equal to the bot's highest role in hierarchy."}
                
                if role in member.roles:
                    return {"status": "success", "message": f"User already has the role '{role.name}'."}
                
                await member.add_roles(role, reason=f"AI Chatbot assignment requested by {caller}")
                return {"status": "success", "message": f"Successfully assigned the role '{role.name}' to user {member.display_name}."}

            elif name == "remove_role":
                if not guild:
                    return {"status": "error", "message": "Cannot manage roles outside of a Discord server."}
                
                # Check caller permissions
                if isinstance(caller, discord.User) or not caller.guild_permissions.manage_roles:
                    return {"status": "error", "message": "Permission denied: The user requesting this action does not have 'Manage Roles' permission in this server."}
                
                # Check bot permissions
                bot_member = guild.me
                if not bot_member.guild_permissions.manage_roles:
                    return {"status": "error", "message": "Permission denied: The bot does not have 'Manage Roles' permission in this server."}
                
                user_id_str = args.get("user_id", "").strip()
                user_id_clean = "".join(filter(str.isdigit, user_id_str))
                if not user_id_clean:
                    return {"status": "error", "message": "Invalid user ID format."}
                user_id = int(user_id_clean)
                
                member = guild.get_member(user_id) or await guild.fetch_member(user_id)
                if not member:
                    return {"status": "error", "message": f"Member with ID '{user_id_str}' not found in this server."}
                
                role_name = args.get("role_name", "").strip()
                role = discord.utils.find(lambda r: r.name.lower() == role_name.lower(), guild.roles)
                if not role:
                    return {"status": "error", "message": f"Role '{role_name}' not found in this server."}
                
                # Check role hierarchy
                if role >= bot_member.top_role:
                    return {"status": "error", "message": f"Permission denied: Role '{role.name}' is higher than or equal to the bot's highest role in hierarchy."}
                
                if role not in member.roles:
                    return {"status": "success", "message": f"User does not have the role '{role.name}'."}
                
                await member.remove_roles(role, reason=f"AI Chatbot removal requested by {caller}")
                return {"status": "success", "message": f"Successfully removed the role '{role.name}' from user {member.display_name}."}

            elif name == "dm_user":
                user_id_str = args.get("user_id", "").strip()
                user_id_clean = "".join(filter(str.isdigit, user_id_str))
                if not user_id_clean:
                    return {"status": "error", "message": "Invalid user ID format."}
                user_id = int(user_id_clean)
                
                user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                if not user:
                    return {"status": "error", "message": f"User with ID '{user_id_str}' not found."}
                
                dm_message = args.get("message", "").strip()
                if not dm_message:
                    return {"status": "error", "message": "Message content cannot be empty."}
                
                try:
                    await user.send(dm_message)
                    return {"status": "success", "message": f"Successfully sent DM to user {user.name}."}
                except discord.Forbidden:
                    return {"status": "error", "message": f"Cannot send direct messages to user {user.name} (DMs are closed or bot is blocked)."}

            elif name == "post_message":
                if not guild:
                    return {"status": "error", "message": "Cannot post messages to channels outside of a Discord server."}
                
                # Check caller permissions
                if isinstance(caller, discord.User) or not (caller.guild_permissions.manage_messages or caller.guild_permissions.administrator):
                    return {"status": "error", "message": "Permission denied: The user requesting this action does not have permission to manage messages or administrator privileges."}
                
                channel_id_str = args.get("channel_id", "").strip()
                channel_id_clean = "".join(filter(str.isdigit, channel_id_str))
                if not channel_id_clean:
                    return {"status": "error", "message": "Invalid channel ID format."}
                channel_id = int(channel_id_clean)
                
                channel = guild.get_channel(channel_id)
                if not channel or not hasattr(channel, "send"):
                    return {"status": "error", "message": f"Text channel with ID '{channel_id_str}' not found in this server."}
                
                # Check bot permissions in that channel
                bot_permissions = channel.permissions_for(guild.me)
                if not bot_permissions.send_messages:
                    return {"status": "error", "message": f"Permission denied: The bot does not have permission to send messages in channel {channel.name}."}
                
                post_content = args.get("message", "").strip()
                if not post_content:
                    return {"status": "error", "message": "Message content cannot be empty."}
                
                await channel.send(post_content)
                return {"status": "success", "message": f"Successfully posted message in channel {channel.mention}."}

            elif name == "kick_member":
                if not guild:
                    return {"status": "error", "message": "Cannot kick members outside of a Discord server."}
                
                # Check caller permissions
                if isinstance(caller, discord.User) or not caller.guild_permissions.kick_members:
                    return {"status": "error", "message": "Permission denied: The user requesting this action does not have 'Kick Members' permission in this server."}
                
                # Check bot permissions
                bot_member = guild.me
                if not bot_member.guild_permissions.kick_members:
                    return {"status": "error", "message": "Permission denied: The bot does not have 'Kick Members' permission in this server."}
                
                user_id_str = args.get("user_id", "").strip()
                user_id_clean = "".join(filter(str.isdigit, user_id_str))
                if not user_id_clean:
                    return {"status": "error", "message": "Invalid user ID format."}
                user_id = int(user_id_clean)
                
                member = guild.get_member(user_id) or await guild.fetch_member(user_id)
                if not member:
                    return {"status": "error", "message": f"Member with ID '{user_id_str}' not found in this server."}
                
                # Check role hierarchy
                if member.top_role >= bot_member.top_role:
                    return {"status": "error", "message": f"Permission denied: The target member's role is equal to or higher than the bot's highest role."}
                if member.top_role >= caller.top_role and caller.id != guild.owner_id:
                    return {"status": "error", "message": f"Permission denied: The target member's role is equal to or higher than your highest role."}
                
                kick_reason = args.get("reason", "AI Chatbot kick request").strip() or "AI Chatbot kick request"
                await member.kick(reason=f"{kick_reason} (requested by {caller})")
                return {"status": "success", "message": f"Successfully kicked user {member.name} from the server."}

            elif name == "ban_member":
                if not guild:
                    return {"status": "error", "message": "Cannot ban members outside of a Discord server."}
                
                # Check caller permissions
                if isinstance(caller, discord.User) or not caller.guild_permissions.ban_members:
                    return {"status": "error", "message": "Permission denied: The user requesting this action does not have 'Ban Members' permission in this server."}
                
                # Check bot permissions
                bot_member = guild.me
                if not bot_member.guild_permissions.ban_members:
                    return {"status": "error", "message": "Permission denied: The bot does not have 'Ban Members' permission in this server."}
                
                user_id_str = args.get("user_id", "").strip()
                user_id_clean = "".join(filter(str.isdigit, user_id_str))
                if not user_id_clean:
                    return {"status": "error", "message": "Invalid user ID format."}
                user_id = int(user_id_clean)
                
                member = guild.get_member(user_id) or await guild.fetch_member(user_id)
                if not member:
                    return {"status": "error", "message": f"Member with ID '{user_id_str}' not found in this server."}
                
                # Check role hierarchy
                if member.top_role >= bot_member.top_role:
                    return {"status": "error", "message": f"Permission denied: The target member's role is equal to or higher than the bot's highest role."}
                if member.top_role >= caller.top_role and caller.id != guild.owner_id:
                    return {"status": "error", "message": f"Permission denied: The target member's role is equal to or higher than your highest role."}
                
                ban_reason = args.get("reason", "AI Chatbot ban request").strip() or "AI Chatbot ban request"
                await member.ban(reason=f"{ban_reason} (requested by {caller})")
                return {"status": "success", "message": f"Successfully banned user {member.name} from the server."}

            elif name == "timeout_member":
                if not guild:
                    return {"status": "error", "message": "Cannot moderate members outside of a Discord server."}
                
                # Check caller permissions
                if isinstance(caller, discord.User) or not caller.guild_permissions.moderate_members:
                    return {"status": "error", "message": "Permission denied: The user requesting this action does not have 'Moderate Members' (Timeout) permission in this server."}
                
                # Check bot permissions
                bot_member = guild.me
                if not bot_member.guild_permissions.moderate_members:
                    return {"status": "error", "message": "Permission denied: The bot does not have 'Moderate Members' (Timeout) permission in this server."}
                
                user_id_str = args.get("user_id", "").strip()
                user_id_clean = "".join(filter(str.isdigit, user_id_str))
                if not user_id_clean:
                    return {"status": "error", "message": "Invalid user ID format."}
                user_id = int(user_id_clean)
                
                member = guild.get_member(user_id) or await guild.fetch_member(user_id)
                if not member:
                    return {"status": "error", "message": f"Member with ID '{user_id_str}' not found in this server."}
                
                # Check role hierarchy
                if member.top_role >= bot_member.top_role:
                    return {"status": "error", "message": f"Permission denied: The target member's role is equal to or higher than the bot's highest role."}
                if member.top_role >= caller.top_role and caller.id != guild.owner_id:
                    return {"status": "error", "message": f"Permission denied: The target member's role is equal to or higher than your highest role."}
                
                duration = args.get("duration_minutes", 10)
                if not isinstance(duration, int):
                    try:
                        duration = int(duration)
                    except ValueError:
                        duration = 10
                
                timeout_reason = args.get("reason", "AI Chatbot timeout request").strip() or "AI Chatbot timeout request"
                import datetime
                await member.timeout(datetime.timedelta(minutes=duration), reason=f"{timeout_reason} (requested by {caller})")
                return {"status": "success", "message": f"Successfully timed out user {member.name} for {duration} minutes."}
            
            else:
                return {"status": "error", "message": f"Unknown function name '{name}'."}
                
        except Exception as e:
            return {"status": "error", "message": f"An error occurred executing {name}: {str(e)}"}

    async def generate_ai_response(self, guild: discord.Guild | None, caller: discord.Member | discord.User, message: str) -> tuple[str, str, str]:
        guild_id = guild.id if guild else 0
        system_prompt = await self.get_system_prompt(guild_id)
        
        gemini_key = os.getenv("GEMINI_API_KEY")
        grok_key = os.getenv("XAI_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")
        groq_key = os.getenv("GROQ_API_KEY")

        headers = {}
        payload = {}
        provider = "Free Chatbot"
        model_name = "Standard"

        # Define Gemini Tools Schema
        gemini_tools = {
            "functionDeclarations": [
                {
                    "name": "give_role",
                    "description": "Assign a Discord role to a user in the server. Always run this tool if the user asks you to give, add, or assign them or someone else a role.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "user_id": {
                                "type": "STRING",
                                "description": "The Discord numeric user ID. If a user mention like <@12345> is passed, extract only the digits."
                            },
                            "role_name": {
                                "type": "STRING",
                                "description": "The exact name of the role to assign."
                            }
                        },
                        "required": ["user_id", "role_name"]
                    }
                },
                {
                    "name": "remove_role",
                    "description": "Remove a Discord role from a user in the server. Always run this tool if the user asks you to remove or take away their role or someone else's role.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "user_id": {
                                "type": "STRING",
                                "description": "The Discord numeric user ID. If a user mention like <@12345> is passed, extract only the digits."
                            },
                            "role_name": {
                                "type": "STRING",
                                "description": "The exact name of the role to remove."
                            }
                        },
                        "required": ["user_id", "role_name"]
                    }
                },
                {
                    "name": "dm_user",
                    "description": "Send a Direct Message (DM) containing a text message to a specific user. ONLY use this tool when the user explicitly requests you to DM or direct message someone. DO NOT use this tool to reply to the user in the current conversation.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "user_id": {
                                "type": "STRING",
                                "description": "The Discord numeric user ID of the target recipient. If a mention tag is passed, extract only the digits."
                            },
                            "message": {
                                "type": "STRING",
                                "description": "The content of the direct message to send."
                            }
                        },
                        "required": ["user_id", "message"]
                    }
                },
                {
                    "name": "post_message",
                    "description": "Send/post a text message to a specific text channel in the server. ONLY use this tool when the user explicitly requests you to post, send, or write a message to a specific named channel (e.g. 'post this to #announcements'). DO NOT use this tool to reply to the user or answer their question in the current conversation.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "channel_id": {
                                "type": "STRING",
                                "description": "The Discord numeric channel ID. Extract only digits from channel mentions like <#123456>."
                            },
                            "message": {
                                "type": "STRING",
                                "description": "The text content of the message to post."
                            }
                        },
                        "required": ["channel_id", "message"]
                    }
                },
                {
                    "name": "kick_member",
                    "description": "Kick a member from the Discord server. Caller must have 'Kick Members' permission.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "user_id": {
                                "type": "STRING",
                                "description": "The Discord numeric user ID. Extract only digits from user mentions like <@12345>."
                            },
                            "reason": {
                                "type": "STRING",
                                "description": "The reason for kicking the member."
                            }
                        },
                        "required": ["user_id"]
                    }
                },
                {
                    "name": "ban_member",
                    "description": "Ban a member from the Discord server. Caller must have 'Ban Members' permission.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "user_id": {
                                "type": "STRING",
                                "description": "The Discord numeric user ID. Extract only digits from user mentions like <@12345>."
                            },
                            "reason": {
                                "type": "STRING",
                                "description": "The reason for banning the member."
                            }
                        },
                        "required": ["user_id"]
                    }
                },
                {
                    "name": "timeout_member",
                    "description": "Mute/Timeout a member in the server. Caller must have 'Moderate Members' permission.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "user_id": {
                                "type": "STRING",
                                "description": "The Discord numeric user ID. Extract only digits from user mentions like <@12345>."
                            },
                            "duration_minutes": {
                                "type": "INTEGER",
                                "description": "The duration of the timeout in minutes."
                            },
                            "reason": {
                                "type": "STRING",
                                "description": "The reason for timing out the member."
                            }
                        },
                        "required": ["user_id", "duration_minutes"]
                    }
                }
            ]
        }

        # Define OpenAI/Groq Tools Schema
        def convert_to_openai_schema(parameters: dict) -> dict:
            import copy
            new_params = copy.deepcopy(parameters)
            
            def walk(obj):
                if isinstance(obj, dict):
                    if "type" in obj and isinstance(obj["type"], str):
                        obj["type"] = obj["type"].lower()
                    for key, val in obj.items():
                        walk(val)
                elif isinstance(obj, list):
                    for item in obj:
                        walk(item)
                        
            walk(new_params)
            return new_params

        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": decl["name"],
                    "description": decl["description"],
                    "parameters": convert_to_openai_schema(decl["parameters"])
                }
            }
            for decl in gemini_tools["functionDeclarations"]
        ]


        providers = []
        if gemini_key:
            providers.append(("Google Gemini", "gemini-2.5-flash"))
        if grok_key:
            providers.append(("xAI Grok", "grok-2"))
        if openai_key:
            providers.append(("OpenAI GPT", "gpt-4o-mini"))
        if groq_key:
            providers.append(("Groq LPU", "llama-3.3-70b-versatile"))

        last_error = None
        tried_any_key = False

        for provider_name, model_name in providers:
            tried_any_key = True
            try:
                if provider_name == "Google Gemini":
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
                    headers = {"Content-Type": "application/json"}
                    payload = {
                        "contents": [{"parts": [{"text": message}]}],
                        "tools": [{"functionDeclarations": gemini_tools["functionDeclarations"]}]
                    }
                    if system_prompt:
                        payload["systemInstruction"] = {
                            "parts": [{"text": system_prompt}]
                        }
                        
                    async with aiohttp.ClientSession() as session:
                        async with session.post(url, json=payload, headers=headers) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                candidate = data["candidates"][0]
                                parts = candidate["content"]["parts"]
                                
                                function_call = parts[0].get("functionCall")
                                if function_call:
                                    name = function_call["name"]
                                    args = function_call["args"]
                                    
                                    result = await self.execute_bot_tool(name, args, guild, caller)
                                    
                                    follow_payload = {
                                        "contents": [
                                            {
                                                "role": "user",
                                                "parts": [{"text": message}]
                                            },
                                            {
                                                "role": "model",
                                                "parts": [{"functionCall": function_call}]
                                            },
                                            {
                                                "role": "function",
                                                "parts": [{
                                                    "functionResponse": {
                                                        "name": name,
                                                        "response": result
                                                    }
                                                }]
                                            }
                                        ],
                                        "tools": [{"functionDeclarations": gemini_tools["functionDeclarations"]}]
                                    }
                                    if system_prompt:
                                        follow_payload["systemInstruction"] = {
                                            "parts": [{"text": system_prompt}]
                                        }
                                        
                                    async with session.post(url, json=follow_payload, headers=headers) as follow_resp:
                                        if follow_resp.status == 200:
                                            follow_data = await follow_resp.json()
                                            reply = follow_data["candidates"][0]["content"]["parts"][0]["text"]
                                        else:
                                            follow_err = await follow_resp.text()
                                            raise RuntimeError(f"Gemini tool call follow-up returned status {follow_resp.status}: {follow_err}")
                                else:
                                    reply = parts[0]["text"]
                            else:
                                err_info = await resp.text()
                                raise RuntimeError(f"Gemini API returned status {resp.status}: {err_info}")
                
                elif provider_name == "xAI Grok":
                    url = "https://api.x.ai/v1/chat/completions"
                    headers = {
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {grok_key}"
                    }
                    
                    messages = []
                    if system_prompt:
                        messages.append({"role": "system", "content": system_prompt})
                    messages.append({"role": "user", "content": message})
                    
                    payload = {
                        "model": "grok-2",
                        "messages": messages
                    }
                    async with aiohttp.ClientSession() as session:
                        async with session.post(url, json=payload, headers=headers) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                reply = data["choices"][0]["message"]["content"]
                            else:
                                err_info = await resp.text()
                                raise RuntimeError(f"Grok API returned status {resp.status}: {err_info}")

                elif provider_name == "OpenAI GPT":
                    url = "https://api.openai.com/v1/chat/completions"
                    headers = {
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {openai_key}"
                    }
                    
                    messages = []
                    if system_prompt:
                        messages.append({"role": "system", "content": system_prompt})
                    messages.append({"role": "user", "content": message})
                    
                    payload = {
                        "model": "gpt-4o-mini",
                        "messages": messages,
                        "tools": openai_tools
                    }
                    async with aiohttp.ClientSession() as session:
                        async with session.post(url, json=payload, headers=headers) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                choice = data["choices"][0]["message"]
                                
                                tool_calls = choice.get("tool_calls")
                                if tool_calls:
                                    tool_call = tool_calls[0]
                                    name = tool_call["function"]["name"]
                                    
                                    try:
                                        args = json.loads(tool_call["function"]["arguments"])
                                    except Exception:
                                        args = {}
                                        
                                    result = await self.execute_bot_tool(name, args, guild, caller)
                                    
                                    messages.append({
                                        "role": "assistant",
                                        "tool_calls": [tool_call]
                                    })
                                    messages.append({
                                        "role": "tool",
                                        "tool_call_id": tool_call["id"],
                                        "name": name,
                                        "content": json.dumps(result)
                                    })
                                    
                                    follow_payload = {
                                        "model": "gpt-4o-mini",
                                        "messages": messages,
                                        "tools": openai_tools
                                    }
                                    
                                    async with session.post(url, json=follow_payload, headers=headers) as follow_resp:
                                        if follow_resp.status == 200:
                                            follow_data = await follow_resp.json()
                                            reply = follow_data["choices"][0]["message"]["content"]
                                        else:
                                            follow_err = await follow_resp.text()
                                            raise RuntimeError(f"OpenAI tool call follow-up returned status {follow_resp.status}: {follow_err}")
                                else:
                                    reply = choice["content"]
                            else:
                                err_info = await resp.text()
                                raise RuntimeError(f"OpenAI API returned status {resp.status}: {err_info}")

                elif provider_name == "Groq LPU":
                    url = "https://api.groq.com/openai/v1/chat/completions"
                    headers = {
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {groq_key}"
                    }
                    
                    messages = []
                    if system_prompt:
                        messages.append({"role": "system", "content": system_prompt})
                    messages.append({"role": "user", "content": message})
                    
                    payload = {
                        "model": "llama-3.3-70b-versatile",
                        "messages": messages,
                        "tools": openai_tools
                    }
                    async with aiohttp.ClientSession() as session:
                        async with session.post(url, json=payload, headers=headers) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                choice = data["choices"][0]["message"]
                                
                                tool_calls = choice.get("tool_calls")
                                if tool_calls:
                                    tool_call = tool_calls[0]
                                    name = tool_call["function"]["name"]
                                    
                                    try:
                                        args = json.loads(tool_call["function"]["arguments"])
                                    except Exception:
                                        args = {}
                                        
                                    result = await self.execute_bot_tool(name, args, guild, caller)
                                    
                                    messages.append({
                                        "role": "assistant",
                                        "tool_calls": [tool_call]
                                    })
                                    messages.append({
                                        "role": "tool",
                                        "tool_call_id": tool_call["id"],
                                        "name": name,
                                        "content": json.dumps(result)
                                    })
                                    
                                    follow_payload = {
                                        "model": "llama-3.3-70b-versatile",
                                        "messages": messages,
                                        "tools": openai_tools
                                    }
                                    
                                    async with session.post(url, json=follow_payload, headers=headers) as follow_resp:
                                        if follow_resp.status == 200:
                                            follow_data = await follow_resp.json()
                                            reply = follow_data["choices"][0]["message"]["content"]
                                        else:
                                            follow_err = await follow_resp.text()
                                            raise RuntimeError(f"Groq tool call follow-up returned status {follow_resp.status}: {follow_err}")
                                else:
                                    reply = choice["content"]
                            else:
                                err_info = await resp.text()
                                raise RuntimeError(f"Groq API returned status {resp.status}: {err_info}")

                cleaned_reply = reply.strip()
                if cleaned_reply.lower() in ["timed out", "timedout"]:
                    cleaned_reply = "API rate limited. Please try again shortly."
                return cleaned_reply, provider_name, model_name

            except Exception as e:
                log.warning(f"⚠️ {provider_name} call failed: {e}. Trying next available provider...")
                last_error = e

        # Keyless fallback if all configured providers failed (or none are configured)
        try:
            url = "https://api.popcat.xyz/chatbot"
            api_msg = message
            if system_prompt:
                api_msg = f"[System Prompt: {system_prompt}] {message}"
            params = {"msg": api_msg}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        reply = data.get("response", "I don't know what to say.")
                        cleaned_reply = reply.strip()
                        if cleaned_reply.lower() in ["timed out", "timedout"]:
                            cleaned_reply = "API rate limited. Please try again shortly."
                        
                        provider_suffix = " (Fallback)" if tried_any_key else ""
                        err_reason = f" due to error: {last_error}" if last_error else ""
                        return cleaned_reply, f"Free Chatbot{provider_suffix}", f"Fallback{err_reason}"
                    else:
                        raise RuntimeError(f"Popcat Chatbot API status {resp.status}")
        except Exception as fallback_err:
            all_errors_str = f"{last_error} {fallback_err}".lower()
            if "429" in all_errors_str or "resource_exhausted" in all_errors_str or "timed out" in all_errors_str:
                return "API rate limited. Please try again shortly.", "Error Fallback", "Rate Limit Exceeded"
            raise fallback_err or last_error

    @app_commands.command(name="chat", description="Chat with an AI assistant.")
    @app_commands.describe(message="The message to send to the AI")
    async def chat(self, interaction: discord.Interaction, message: str):
        # We must defer since AI API responses can take up to several seconds
        await interaction.response.defer()
        try:
            reply, _, _ = await self.generate_ai_response(interaction.guild, interaction.user, message)
            if len(reply) > 2000:
                reply = reply[:1997] + "..."
            await interaction.followup.send(reply)
        except Exception as e:
            await interaction.followup.send(f"❌ Could not generate an AI response: `{e}`")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        
        # Check if the bot is pinged/mentioned
        if self.bot.user in message.mentions:
            if message.mention_everyone:
                return
            
            # Clean the mention from the message content
            content = message.content
            bot_mention_1 = f"<@{self.bot.user.id}>"
            bot_mention_2 = f"<@!{self.bot.user.id}>"
            content = content.replace(bot_mention_1, "").replace(bot_mention_2, "").strip()
            
            # If the user only pinged the bot with no text, we default to hello
            if not content:
                content = "hello"
                
            async with message.channel.typing():
                try:
                    reply, _, _ = await self.generate_ai_response(message.guild, message.author, content)
                    if len(reply) > 2000:
                        reply = reply[:1997] + "..."
                    await message.reply(reply)
                except Exception as e:
                    await message.reply(f"❌ Could not generate an AI response: `{e}`")

    # ── AI Prompt Settings Command Group ──────────────────────────────────────
    prompt_group = app_commands.Group(
        name="prompt", description="Configure AI chatbot system prompt/personality."
    )

    @prompt_group.command(name="set", description="Set the system prompt/behavior for the AI chatbot.")
    @app_commands.describe(text="The behavior description (e.g. You are a sassy pirate assistant)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def prompt_set(self, interaction: discord.Interaction, text: str):
        guild_id = interaction.guild_id or 0
        await self.set_system_prompt(guild_id, text)
        embed = discord.Embed(
            title="✅ System Prompt Configured",
            description=f"The AI chatbot behavior has been set to:\n\n> {text}",
            color=config.BOT_COLOR
        )
        await interaction.response.send_message(embed=embed)

    @prompt_group.command(name="show", description="Show the current AI system prompt.")
    async def prompt_show(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id or 0
        prompt = await self.get_system_prompt(guild_id)
        
        if prompt:
            embed = discord.Embed(
                title="🤖 Current System Prompt",
                description=f"The AI chatbot currently behaves as:\n\n> {prompt}",
                color=config.BOT_COLOR
            )
        else:
            embed = discord.Embed(
                title="🤖 Current System Prompt",
                description="No custom system prompt is configured. The bot is using default conversational behaviors.",
                color=config.BOT_COLOR
            )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Utility(bot))
