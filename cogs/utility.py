import discord
from discord import app_commands
from discord.ext import commands
import config


class Utility(commands.Cog):
    """Handy utility commands for getting info about users and the server."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot


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


async def setup(bot: commands.Bot):
    await bot.add_cog(Utility(bot))
