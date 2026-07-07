import wavelink
import discord
from discord import app_commands
from discord.ext import commands
from utils.embeds import error, success, info
import config


def fmt_duration(ms: int) -> str:
    seconds = ms // 1000
    h, r    = divmod(seconds, 3600)
    m, s    = divmod(r, 60)
    return f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}"

def progress_bar(position: int, duration: int, length: int = 15) -> str:
    if not duration:
        return "─" * length
    filled = int((position / duration) * length)
    return "▓" * filled + "░" * (length - filled)


class MusicView(discord.ui.View):
    def __init__(self, player: wavelink.Player):
        super().__init__(timeout=None)
        self.player = player

    async def _refresh(self, interaction: discord.Interaction):
        if not self.player.current:
            return await interaction.response.edit_message(
                embed=info("Nothing Playing", "The queue is empty."), view=None
            )
        await interaction.response.edit_message(embed=now_playing_embed(self.player), view=self)

    @discord.ui.button(emoji="⏸️", style=discord.ButtonStyle.secondary)
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.player.pause(not self.player.paused)
        button.emoji = "▶️" if self.player.paused else "⏸️"
        await self._refresh(interaction)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary)
    async def skip_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.player.skip()
        await self._refresh(interaction)

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger)
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.player.queue.clear()
        await self.player.stop()
        await self.player.disconnect()
        await interaction.response.edit_message(
            embed=success("Stopped", "Music stopped and disconnected."), view=None
        )

    @discord.ui.button(emoji="🔀", style=discord.ButtonStyle.secondary)
    async def shuffle_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.player.queue.shuffle()
        await interaction.response.send_message("Queue shuffled!", ephemeral=True)


def now_playing_embed(player: wavelink.Player) -> discord.Embed:
    track = player.current
    if not track:
        return info("Nothing Playing", "The queue is empty.")

    embed = discord.Embed(
        title="🎵 Now Playing",
        description=f"**[{track.title}]({track.uri})**",
        color=config.BOT_COLOR,
    )
    if track.artwork:
        embed.set_thumbnail(url=track.artwork)

    pos = player.position
    dur = track.length
    embed.add_field(
        name="Progress",
        value=f"`{fmt_duration(pos)}` {progress_bar(pos, dur)} `{fmt_duration(dur)}`",
        inline=False,
    )
    embed.add_field(name="Author",  value=track.author or "Unknown")
    embed.add_field(name="Volume",  value=f"`{player.volume}%`")
    loop_mode = player.queue.mode
    embed.add_field(
        name="Loop",
        value="🔂 Track" if loop_mode == wavelink.QueueMode.loop
        else "🔁 Queue" if loop_mode == wavelink.QueueMode.loop_all
        else "Off"
    )
    embed.add_field(name="Queue",   value=f"`{len(player.queue)}` track(s)")
    requester = getattr(track, "requester", None)
    if requester:
        embed.set_footer(text=f"Requested by {requester}")
    return embed


class Music(commands.Cog):
    """Full music system powered by Wavelink + Lavalink."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        """Connect to Lavalink nodes with automatic fallback."""
        import logging
        log = logging.getLogger("music")

        # Primary node from config/env vars
        # Backup nodes tried in order if primary fails
        node_list = [
            # Primary — set via LAVALINK_URI env var
            {"uri": config.LAVALINK_URI,           "password": config.LAVALINK_PASSWORD},
            # Backup nodes (public free nodes)
            {"uri": "http://lavalinkv4.serenetia.com:80",  "password": "https://dsc.gg/ajidevserver"},
            {"uri": "http://lavalink.clxud.dev:2333",    "password": "youshallnotpass"},
            {"uri": "http://lavalink.devamop.in:80",     "password": "DevamOP"},
        ]

        # Deduplicate in case primary matches a backup
        seen  = set()
        nodes = []
        for n in node_list:
            key = n["uri"]
            if key not in seen:
                seen.add(key)
                nodes.append(wavelink.Node(uri=n["uri"], password=n["password"]))

        connected = 0
        for node in nodes:
            try:
                await wavelink.Pool.connect(nodes=[node], client=self.bot, cache_capacity=100)
                log.info(f"✅  Connected to Lavalink node: {node.uri}")
                connected += 1
            except Exception as e:
                log.warning(f"⚠️  Could not connect to Lavalink node {node.uri}: {e}")

        if connected == 0:
            log.error("❌  No Lavalink nodes could be connected. Music will not work.")
        else:
            log.info(f"🎵  {connected} Lavalink node(s) connected.")

    async def _ensure_voice(self, interaction: discord.Interaction):
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message(
                embed=error("Not in Voice", "You need to be in a voice channel."), ephemeral=True
            )
            return None

        player: wavelink.Player = interaction.guild.voice_client

        if not player:
            try:
                player = await interaction.user.voice.channel.connect(cls=wavelink.Player)
                player.autoplay = wavelink.AutoPlayMode.partial
            except Exception as e:
                await interaction.response.send_message(
                    embed=error("Connection Failed", f"Could not join voice: `{e}`"), ephemeral=True
                )
                return None
        elif player.channel != interaction.user.voice.channel:
            await interaction.response.send_message(
                embed=error("Wrong Channel", f"I'm already in {player.channel.mention}."), ephemeral=True
            )
            return None

        return player

    @app_commands.command(name="play", description="Play a song or add it to the queue.")
    @app_commands.describe(query="Song name or URL (YouTube, Spotify, SoundCloud)")
    async def play(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()
        player = await self._ensure_voice(interaction)
        if not player:
            return

        try:
            tracks = await wavelink.Playable.search(query)
        except Exception as e:
            return await interaction.followup.send(embed=error("Search Failed", f"`{e}`"))

        if not tracks:
            return await interaction.followup.send(embed=error("No Results", f"No results for `{query}`."))

        if isinstance(tracks, wavelink.Playlist):
            for track in tracks:
                track.requester = str(interaction.user)
                await player.queue.put_wait(track)
            embed = success("Playlist Added", f"Added **{len(tracks)}** tracks from **{tracks.name}**.")
        else:
            track = tracks[0]
            track.requester = str(interaction.user)
            await player.queue.put_wait(track)
            embed = discord.Embed(title="✅ Added to Queue", description=f"**[{track.title}]({track.uri})**", color=discord.Color.green())
            embed.add_field(name="Duration", value=fmt_duration(track.length))
            embed.add_field(name="Position", value=f"`#{len(player.queue)}`")
            if track.artwork:
                embed.set_thumbnail(url=track.artwork)

        await interaction.followup.send(embed=embed)
        if not player.playing:
            await player.play(player.queue.get())

    @app_commands.command(name="skip", description="Skip the current track.")
    @app_commands.describe(amount="Number of tracks to skip (default 1)")
    async def skip(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 10] = 1):
        player: wavelink.Player = interaction.guild.voice_client
        if not player or not player.playing:
            return await interaction.response.send_message(embed=error("Nothing Playing"), ephemeral=True)
        for _ in range(amount - 1):
            if player.queue:
                player.queue.get()
        await player.skip()
        await interaction.response.send_message(embed=success("Skipped", f"Skipped **{amount}** track(s)."), ephemeral=True)

    @app_commands.command(name="stop", description="Stop music and disconnect the bot.")
    async def stop(self, interaction: discord.Interaction):
        player: wavelink.Player = interaction.guild.voice_client
        if not player:
            return await interaction.response.send_message(embed=error("Not Connected"), ephemeral=True)
        player.queue.clear()
        await player.stop()
        await player.disconnect()
        await interaction.response.send_message(embed=success("Stopped", "Music stopped and disconnected."))

    @app_commands.command(name="pause", description="Pause the current track.")
    async def pause(self, interaction: discord.Interaction):
        player: wavelink.Player = interaction.guild.voice_client
        if not player or not player.playing:
            return await interaction.response.send_message(embed=error("Nothing Playing"), ephemeral=True)
        if player.paused:
            return await interaction.response.send_message(embed=error("Already Paused"), ephemeral=True)
        await player.pause(True)
        await interaction.response.send_message(embed=success("Paused", "Use `/resume` to continue."))

    @app_commands.command(name="resume", description="Resume the paused track.")
    async def resume(self, interaction: discord.Interaction):
        player: wavelink.Player = interaction.guild.voice_client
        if not player or not player.paused:
            return await interaction.response.send_message(embed=error("Not Paused"), ephemeral=True)
        await player.pause(False)
        await interaction.response.send_message(embed=success("Resumed", "Music resumed!"))

    @app_commands.command(name="nowplaying", description="Show the currently playing track.")
    async def nowplaying(self, interaction: discord.Interaction):
        player: wavelink.Player = interaction.guild.voice_client
        if not player or not player.current:
            return await interaction.response.send_message(embed=error("Nothing Playing"), ephemeral=True)
        await interaction.response.send_message(embed=now_playing_embed(player), view=MusicView(player))

    @app_commands.command(name="queue", description="Show the current queue.")
    async def queue(self, interaction: discord.Interaction):
        player: wavelink.Player = interaction.guild.voice_client
        if not player or (not player.current and not player.queue):
            return await interaction.response.send_message(embed=info("Empty Queue", "Nothing in the queue."), ephemeral=True)

        embed = discord.Embed(title="🎵 Music Queue", color=config.BOT_COLOR)
        if player.current:
            embed.add_field(
                name="Now Playing",
                value=f"🎵 **[{player.current.title}]({player.current.uri})** `{fmt_duration(player.current.length)}`",
                inline=False,
            )
        if player.queue:
            lines = []
            for i, track in enumerate(list(player.queue)[:10], start=1):
                lines.append(f"`{i}.` **{track.title}** `{fmt_duration(track.length)}`")
            if len(player.queue) > 10:
                lines.append(f"*...and {len(player.queue) - 10} more*")
            embed.add_field(name=f"Up Next ({len(player.queue)})", value="\n".join(lines), inline=False)
        total = sum(t.length for t in player.queue)
        embed.set_footer(text=f"Total queue time: {fmt_duration(total)}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="volume", description="Set the player volume.")
    @app_commands.describe(volume="Volume level (1-100)")
    async def volume(self, interaction: discord.Interaction, volume: app_commands.Range[int, 1, 100]):
        player: wavelink.Player = interaction.guild.voice_client
        if not player:
            return await interaction.response.send_message(embed=error("Not Connected"), ephemeral=True)
        await player.set_volume(volume)
        emoji = "🔇" if volume < 10 else "🔈" if volume < 40 else "🔉" if volume < 70 else "🔊"
        await interaction.response.send_message(embed=success("Volume Set", f"{emoji} Volume set to **{volume}%**"))

    @app_commands.command(name="seek", description="Seek to a position in the current track.")
    @app_commands.describe(position="Position in seconds or mm:ss format")
    async def seek(self, interaction: discord.Interaction, position: str):
        player: wavelink.Player = interaction.guild.voice_client
        if not player or not player.current:
            return await interaction.response.send_message(embed=error("Nothing Playing"), ephemeral=True)
        try:
            if ":" in position:
                parts   = position.split(":")
                seconds = int(parts[-1]) + int(parts[-2]) * 60
                if len(parts) == 3:
                    seconds += int(parts[0]) * 3600
            else:
                seconds = int(position)
        except ValueError:
            return await interaction.response.send_message(
                embed=error("Invalid Format", "Use `mm:ss` or seconds e.g. `1:30` or `90`."), ephemeral=True
            )
        ms = seconds * 1000
        if ms > player.current.length:
            return await interaction.response.send_message(
                embed=error("Out of Range", f"Track is only `{fmt_duration(player.current.length)}` long."), ephemeral=True
            )
        await player.seek(ms)
        await interaction.response.send_message(embed=success("Seeked", f"Jumped to `{fmt_duration(ms)}`."), ephemeral=True)

    @app_commands.command(name="loop", description="Set loop mode.")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Off",   value="off"),
        app_commands.Choice(name="Track", value="track"),
        app_commands.Choice(name="Queue", value="queue"),
    ])
    async def loop(self, interaction: discord.Interaction, mode: str):
        player: wavelink.Player = interaction.guild.voice_client
        if not player:
            return await interaction.response.send_message(embed=error("Not Connected"), ephemeral=True)
        modes = {"off": wavelink.QueueMode.normal, "track": wavelink.QueueMode.loop, "queue": wavelink.QueueMode.loop_all}
        icons = {"off": "➡️", "track": "🔂", "queue": "🔁"}
        player.queue.mode = modes[mode]
        await interaction.response.send_message(embed=success("Loop Mode", f"{icons[mode]} Loop set to **{mode.title()}**."))

    @app_commands.command(name="shuffle", description="Shuffle the queue.")
    async def shuffle(self, interaction: discord.Interaction):
        player: wavelink.Player = interaction.guild.voice_client
        if not player or not player.queue:
            return await interaction.response.send_message(embed=error("Empty Queue"), ephemeral=True)
        player.queue.shuffle()
        await interaction.response.send_message(embed=success("Shuffled", f"🔀 Shuffled **{len(player.queue)}** tracks."))

    @app_commands.command(name="remove", description="Remove a track from the queue by position.")
    @app_commands.describe(position="Position in the queue (1 = next track)")
    async def remove(self, interaction: discord.Interaction, position: app_commands.Range[int, 1, 100]):
        player: wavelink.Player = interaction.guild.voice_client
        if not player or not player.queue:
            return await interaction.response.send_message(embed=error("Empty Queue"), ephemeral=True)
        if position > len(player.queue):
            return await interaction.response.send_message(
                embed=error("Invalid Position", f"Queue only has `{len(player.queue)}` tracks."), ephemeral=True
            )
        track = player.queue[position - 1]
        del player.queue[position - 1]
        await interaction.response.send_message(embed=success("Removed", f"Removed **{track.title}** from the queue."))

    @app_commands.command(name="clearqueue", description="Clear all tracks from the queue.")
    async def clearqueue(self, interaction: discord.Interaction):
        player: wavelink.Player = interaction.guild.voice_client
        if not player or not player.queue:
            return await interaction.response.send_message(embed=error("Empty Queue"), ephemeral=True)
        count = len(player.queue)
        player.queue.clear()
        await interaction.response.send_message(embed=success("Queue Cleared", f"Removed **{count}** track(s)."))

    @app_commands.command(name="autoplay", description="Toggle autoplay mode.")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Off",     value="off"),
        app_commands.Choice(name="Partial", value="partial"),
        app_commands.Choice(name="Enabled", value="enabled"),
    ])
    async def autoplay(self, interaction: discord.Interaction, mode: str):
        player: wavelink.Player = interaction.guild.voice_client
        if not player:
            return await interaction.response.send_message(embed=error("Not Connected"), ephemeral=True)
        modes = {
            "off":     wavelink.AutoPlayMode.disabled,
            "partial": wavelink.AutoPlayMode.partial,
            "enabled": wavelink.AutoPlayMode.enabled,
        }
        descs = {
            "off":     "Bot will stop when queue ends.",
            "partial": "Plays related tracks only when queue is empty.",
            "enabled": "Continuously plays related tracks.",
        }
        player.autoplay = modes[mode]
        await interaction.response.send_message(embed=success("Autoplay", descs[mode]))

    @app_commands.command(name="join", description="Join your voice channel.")
    async def join(self, interaction: discord.Interaction):
        if not interaction.user.voice:
            return await interaction.response.send_message(embed=error("Not in Voice", "Join a voice channel first."), ephemeral=True)
        channel = interaction.user.voice.channel
        player  = interaction.guild.voice_client
        if player:
            await player.move_to(channel)
        else:
            await channel.connect(cls=wavelink.Player)
        await interaction.response.send_message(embed=success("Joined", f"Connected to {channel.mention}."))

    @app_commands.command(name="leave", description="Leave the voice channel.")
    async def leave(self, interaction: discord.Interaction):
        player: wavelink.Player = interaction.guild.voice_client
        if not player:
            return await interaction.response.send_message(embed=error("Not Connected"), ephemeral=True)
        await player.disconnect()
        await interaction.response.send_message(embed=success("Left", "Disconnected from voice."))

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        player = payload.player
        if not player:
            return
        if player.autoplay == wavelink.AutoPlayMode.disabled and not player.queue:
            await player.disconnect()

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        import logging
        logging.getLogger("music").info(f"Lavalink node ready: {payload.node.uri}")

    async def cog_app_command_error(self, interaction: discord.Interaction, err: app_commands.AppCommandError):
        msg = f"`{err}`"
        if interaction.response.is_done():
            await interaction.followup.send(embed=error("Error", msg), ephemeral=True)
        else:
            await interaction.response.send_message(embed=error("Error", msg), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
