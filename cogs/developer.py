import io
import os
import sys
import time
import traceback
import textwrap
import contextlib
import subprocess
import logging
import discord
from discord import app_commands
from discord.ext import commands
from utils.checks import is_owner
from utils.embeds import success, error, info
import config

log = logging.getLogger("bot")


class Developer(commands.Cog):
    """Owner-only developer tools and administrative utilities (Prefix & Slash)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._last_result = None  # Store last eval result for reuse

    def cog_check(self, ctx: commands.Context) -> bool:
        """All prefix commands in this cog are owner-only."""
        return ctx.author.id in config.OWNER_IDS

    # ── Prefix: eval ──────────────────────────────────────────────────────────
    @commands.command(name="eval", aliases=["e"])
    async def _eval(self, ctx: commands.Context, *, code: str):
        """Evaluate Python code. Use \\`\\`\\` code blocks or inline."""
        if code.startswith("```") and code.endswith("```"):
            code = "\n".join(code.split("\n")[1:-1])
        code = code.strip("`").strip()

        env = {
            "bot":     self.bot,
            "ctx":     ctx,
            "guild":   ctx.guild,
            "channel": ctx.channel,
            "author":  ctx.author,
            "db":      __import__("database.db", fromlist=["db"]),
            "_":       self._last_result,
            "discord": discord,
        }
        env.update(globals())

        stdout = io.StringIO()
        to_compile = f"async def func():\n{textwrap.indent(code, '  ')}"

        try:
            exec(to_compile, env)
        except SyntaxError as e:
            return await ctx.send(f"```py\n{e}\n```")

        func = env["func"]
        try:
            with contextlib.redirect_stdout(stdout):
                start = time.perf_counter()
                result = await func()
                elapsed = (time.perf_counter() - start) * 1000
        except Exception:
            output = stdout.getvalue()
            tb = traceback.format_exc()
            return await ctx.send(f"```py\n{output}{tb}\n```"[:2000])

        self._last_result = result
        output = stdout.getvalue()

        if result is None:
            value = output or "*(no output)*"
        else:
            value = f"{output}{result}"

        embed = discord.Embed(title="✅ Eval", color=discord.Color.green())
        embed.add_field(name="Input",  value=f"```py\n{code[:900]}\n```", inline=False)
        embed.add_field(name="Output", value=f"```py\n{str(value)[:900]}\n```", inline=False)
        embed.set_footer(text=f"Took {elapsed:.2f}ms")
        await ctx.send(embed=embed)

    # ── Prefix: reload ────────────────────────────────────────────────────────
    @commands.command(name="reload", aliases=["rl"])
    async def reload_prefix(self, ctx: commands.Context, cog: str = None):
        """Reload one or all cogs without restarting."""
        if cog:
            ext = f"cogs.{cog}" if not cog.startswith("cogs.") else cog
            try:
                await self.bot.reload_extension(ext)
                await ctx.send(embed=success("Reloaded", f"`{ext}`"))
            except Exception as e:
                await ctx.send(embed=error("Reload Failed", f"```{e}```"))
        else:
            results = []
            for ext in list(self.bot.extensions):
                try:
                    await self.bot.reload_extension(ext)
                    results.append(f"✅ `{ext}`")
                except Exception as e:
                    results.append(f"❌ `{ext}` — {e}")

            embed = discord.Embed(title="🔄 Reload All", description="\n".join(results), color=config.BOT_COLOR)
            await ctx.send(embed=embed)

    # ── Prefix: load ──────────────────────────────────────────────────────────
    @commands.command(name="load")
    async def load(self, ctx: commands.Context, cog: str):
        """Load a cog."""
        ext = f"cogs.{cog}" if not cog.startswith("cogs.") else cog
        try:
            await self.bot.load_extension(ext)
            await ctx.send(embed=success("Loaded", f"`{ext}`"))
        except Exception as e:
            await ctx.send(embed=error("Load Failed", f"```{e}```"))

    # ── Prefix: unload ────────────────────────────────────────────────────────
    @commands.command(name="unload")
    async def unload(self, ctx: commands.Context, cog: str):
        """Unload a cog."""
        ext = f"cogs.{cog}" if not cog.startswith("cogs.") else cog
        try:
            await self.bot.unload_extension(ext)
            await ctx.send(embed=success("Unloaded", f"`{ext}`"))
        except Exception as e:
            await ctx.send(embed=error("Unload Failed", f"```{e}```"))

    # ── Prefix: sync ──────────────────────────────────────────────────────────
    @commands.command(name="sync")
    async def sync(self, ctx: commands.Context, scope: str = "guild"):
        """Sync slash commands. scope: guild | global | clear"""
        msg = await ctx.send("⏳ Syncing...")

        if scope == "guild":
            if not ctx.guild:
                return await msg.edit(content="Run this in a server.")
            guild = discord.Object(id=ctx.guild.id)
            self.bot.tree.copy_global_to(guild=guild)
            synced = await self.bot.tree.sync(guild=guild)
            await msg.edit(embed=success("Guild Sync", f"Synced **{len(synced)}** commands to this server."))

        elif scope == "global":
            synced = await self.bot.tree.sync()
            await msg.edit(embed=success("Global Sync", f"Synced **{len(synced)}** commands globally. May take up to 1 hour."))

        elif scope == "clear":
            self.bot.tree.clear_commands(guild=None)
            await self.bot.tree.sync()
            if ctx.guild:
                guild = discord.Object(id=ctx.guild.id)
                self.bot.tree.clear_commands(guild=guild)
                await self.bot.tree.sync(guild=guild)
            await msg.edit(embed=success("Cleared", "All slash commands cleared."))

        else:
            await msg.edit(embed=error("Unknown Scope", "Use `guild`, `global`, or `clear`."))

    # ── Prefix: presence status ───────────────────────────────────────────────
    @commands.command(name="status")
    async def status(self, ctx: commands.Context, kind: str, *, text: str):
        """Change the bot's presence. kind: watching|playing|listening|streaming"""
        kinds = {
            "watching":  discord.ActivityType.watching,
            "playing":   discord.ActivityType.playing,
            "listening": discord.ActivityType.listening,
            "streaming": discord.ActivityType.streaming,
        }
        activity_type = kinds.get(kind.lower())
        if not activity_type:
            return await ctx.send(embed=error("Invalid Type", f"Choose from: {', '.join(kinds)}"))

        await self.bot.change_presence(activity=discord.Activity(type=activity_type, name=text))
        await ctx.send(embed=success("Status Updated", f"{kind.title()} **{text}**"))

    # ── Prefix: sql ───────────────────────────────────────────────────────────
    @commands.command(name="sql")
    async def sql(self, ctx: commands.Context, *, query: str):
        """Run a raw SQL query against the database."""
        from database.db import get_pool
        try:
            start   = time.perf_counter()
            results = await get_pool().fetch(query)
            elapsed = (time.perf_counter() - start) * 1000

            if not results:
                return await ctx.send(embed=info("SQL", f"Query returned no rows.\n`{elapsed:.2f}ms`"))

            headers = list(results[0].keys())
            rows    = [list(map(str, r.values())) for r in results[:10]]
            col_w   = [max(len(h), max((len(r[i]) for r in rows), default=0)) for i, h in enumerate(headers)]
            header  = " | ".join(h.ljust(col_w[i]) for i, h in enumerate(headers))
            divider = "-+-".join("-" * w for w in col_w)
            lines   = [header, divider] + [" | ".join(c.ljust(col_w[i]) for i, c in enumerate(r)) for r in rows]
            table   = "\n".join(lines)

            embed = discord.Embed(title="🗄️ SQL Result", color=config.BOT_COLOR)
            embed.description = f"```\n{table[:3800]}\n```"
            embed.set_footer(text=f"{len(results)} row(s) • {elapsed:.2f}ms")
            await ctx.send(embed=embed)

        except Exception as e:
            await ctx.send(embed=error("SQL Error", f"```{e}```"))

    # ── Prefix: servers ───────────────────────────────────────────────────────
    @commands.command(name="servers")
    async def servers(self, ctx: commands.Context):
        """List all servers the bot is in."""
        guilds = sorted(self.bot.guilds, key=lambda g: g.member_count, reverse=True)
        lines  = [f"`{g.id}` **{g.name}** — {g.member_count} members" for g in guilds[:20]]
        embed  = discord.Embed(
            title=f"🌐 {len(guilds)} Servers",
            description="\n".join(lines),
            color=config.BOT_COLOR,
        )
        await ctx.send(embed=embed)

    # ── Prefix: botstats ──────────────────────────────────────────────────────
    @commands.command(name="botstats")
    async def botstats(self, ctx: commands.Context):
        """Show detailed bot statistics."""
        import platform
        import psutil
        process = psutil.Process(os.getpid())

        embed = discord.Embed(title="🤖 Bot Stats", color=config.BOT_COLOR)
        embed.add_field(name="Servers",    value=str(len(self.bot.guilds)))
        embed.add_field(name="Users",      value=str(sum(g.member_count for g in self.bot.guilds)))
        embed.add_field(name="Cogs",       value=str(len(self.bot.cogs)))
        embed.add_field(name="Commands",   value=str(len(self.bot.commands)))
        embed.add_field(name="Latency",    value=f"{round(self.bot.latency * 1000)}ms")
        embed.add_field(name="Python",     value=platform.python_version())
        embed.add_field(name="discord.py", value=discord.__version__)
        embed.add_field(name="RAM",        value=f"{process.memory_info().rss / 1024 / 1024:.1f} MB")

        await ctx.send(embed=embed)

    # ── Prefix: dm ────────────────────────────────────────────────────────────
    @commands.command(name="dm")
    async def dm(self, ctx: commands.Context, user: discord.User, *, message: str):
        """DM a user directly."""
        try:
            await user.send(message)
            await ctx.send(embed=success("DM Sent", f"Sent to `{user}`."))
        except discord.Forbidden:
            await ctx.send(embed=error("Failed", "User has DMs disabled."))

    # ── Prefix: shutdown ──────────────────────────────────────────────────────
    @commands.command(name="shutdown", aliases=["die", "kill"])
    async def shutdown_prefix(self, ctx: commands.Context):
        """Shut down the bot."""
        await ctx.send(embed=info("Shutting down...", "Goodbye 👋"))
        await self.bot.close()

    # ── Slash: Restart Command ─────────────────────────────────────────────────
    @app_commands.command(name="restart", description="Restart the bot process.")
    @is_owner()
    async def restart(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=success(
                "Restarting", "The bot is restarting... Please wait a few seconds."
            ),
            ephemeral=True,
        )
        log.info("🔄 Bot restart initiated by owner.")
        # Spawns a new bot process
        subprocess.Popen([sys.executable] + sys.argv)
        # Exits the current process
        os._exit(0)

    # ── Slash: Reload Command ──────────────────────────────────────────────────
    @app_commands.command(name="reload", description="Reload a bot cog extension.")
    @app_commands.describe(
        cog_name="The name of the cog to reload (e.g. general, customcmds)"
    )
    @is_owner()
    async def reload(self, interaction: discord.Interaction, cog_name: str):
        full_cog_name = cog_name.strip()
        if not full_cog_name.startswith("cogs."):
            full_cog_name = f"cogs.{full_cog_name}"

        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.reload_extension(full_cog_name)
            log.info(f"🔄 Reloaded extension: {full_cog_name}")
            await interaction.followup.send(
                embed=success("Extension Reloaded", f"Successfully reloaded `{full_cog_name}`.")
            )
        except Exception as e:
            log.error(f"❌ Failed to reload extension {full_cog_name}: {e}")
            await interaction.followup.send(
                embed=error(
                    "Reload Failed", f"Failed to reload `{full_cog_name}`:\n```py\n{e}\n```"
                )
            )

    # ── Slash: Shutdown Command ────────────────────────────────────────────────
    @app_commands.command(name="shutdown", description="Safely shut down the bot.")
    @is_owner()
    async def shutdown(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=success("Shutting Down", "The bot is shutting down safely."),
            ephemeral=True,
        )
        log.info("🔌 Bot shutdown initiated by owner.")
        await self.bot.close()


async def setup(bot: commands.Bot):
    await bot.add_cog(Developer(bot))
