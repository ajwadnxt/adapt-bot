import random
import discord
from discord import app_commands
from discord.ext import commands
from utils.embeds import success, error, info


# ── Time Bomb Game ──────────────────────────────────────────────────────────

class TimeBombView(discord.ui.View):
    def __init__(self, author: discord.Member, opponent: discord.Member | None = None):
        super().__init__(timeout=60)
        self.author = author
        self.opponent = opponent
        self.turn = author

        self.wires = {
            "Red 🔴": discord.ButtonStyle.danger,
            "Blue 🔵": discord.ButtonStyle.primary,
            "Green 🟢": discord.ButtonStyle.success,
            "Yellow 🟡": discord.ButtonStyle.secondary,
            "Purple 🟣": discord.ButtonStyle.secondary,
        }

        wire_names = list(self.wires.keys())
        self.detonate_wire = random.choice(wire_names)
        wire_names.remove(self.detonate_wire)
        self.defuse_wire = random.choice(wire_names)

        self.cut_wires = []
        self.game_over = False

        for wire, style in self.wires.items():
            button = discord.ui.Button(label=wire, style=style, custom_id=wire)
            button.callback = self.make_button_callback(wire)
            self.add_item(button)

    def make_button_callback(self, wire: str):
        async def callback(interaction: discord.Interaction):
            if self.opponent:
                if interaction.user.id != self.turn.id:
                    await interaction.response.send_message(
                        "It's not your turn!", ephemeral=True
                    )
                    return
            else:
                if interaction.user.id != self.author.id:
                    await interaction.response.send_message(
                        "This isn't your bomb!", ephemeral=True
                    )
                    return

            for item in self.children:
                if isinstance(item, discord.ui.Button) and item.custom_id == wire:
                    item.disabled = True
                    break

            self.cut_wires.append(wire)

            if wire == self.detonate_wire:
                self.game_over = True
                for item in self.children:
                    if isinstance(item, discord.ui.Button):
                        item.disabled = True
                        if item.custom_id == self.detonate_wire:
                            item.style = discord.ButtonStyle.danger
                            item.label = f"{wire} (BOOM!)"

                embed = error(
                    "💥 BOOM! The Bomb Exploded!",
                    f"**{interaction.user.mention}** cut the wrong wire ({wire}) and detonated the bomb!\n\n"
                    f"🟢 Defuse wire was: **{self.defuse_wire}**\n"
                    f"🔴 Detonate wire was: **{self.detonate_wire}**",
                )
                await interaction.response.edit_message(embed=embed, view=self)
                self.stop()
                return

            elif wire == self.defuse_wire:
                self.game_over = True
                for item in self.children:
                    if isinstance(item, discord.ui.Button):
                        item.disabled = True
                        if item.custom_id == self.defuse_wire:
                            item.style = discord.ButtonStyle.success
                            item.label = f"{wire} (DEFUSED!)"

                embed = success(
                    "🔒 Bomb Defused!",
                    f"**{interaction.user.mention}** successfully cut the defusal wire ({wire})!\n\n"
                    f"🟢 Defuse wire was: **{self.defuse_wire}**\n"
                    f"🔴 Detonate wire was: **{self.detonate_wire}**",
                )
                await interaction.response.edit_message(embed=embed, view=self)
                self.stop()
                return

            else:
                if self.opponent:
                    self.turn = (
                        self.opponent if self.turn == self.author else self.author
                    )
                    turn_str = f"It is now **{self.turn.mention}**'s turn to cut a wire!"
                else:
                    turn_str = "You cut a safe wire! Pick another wire to cut."

                embed = info(
                    "⏳ Tick, tock... Cut a wire!",
                    f"**{interaction.user.mention}** cut a safe wire ({wire})!\n\n"
                    f"{turn_str}\n\n"
                    f"Cut Wires: {', '.join(self.cut_wires)}",
                )
                await interaction.response.edit_message(embed=embed, view=self)

        return callback

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.opponent:
            if interaction.user.id not in (self.author.id, self.opponent.id):
                await interaction.response.send_message(
                    "This game is only for the players!", ephemeral=True
                )
                return False
        else:
            if interaction.user.id != self.author.id:
                await interaction.response.send_message(
                    "Start your own game with `/timebomb`!", ephemeral=True
                )
                return False
        return True


# ── Tic-Tac-Toe Game ────────────────────────────────────────────────────────

class RematchButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.success, label="Rematch 🔄", row=4)

    async def callback(self, interaction: discord.Interaction):
        assert self.view is not None
        view: TicTacToeView = self.view

        user = interaction.user
        if user.id not in (view.player_x.id, view.player_o.id):
            await interaction.response.send_message(
                "You are not part of this game!", ephemeral=True
            )
            return

        if view.rematch_requested_by is None:
            view.rematch_requested_by = user
            self.label = "Accept Rematch (1/2) 🔄"
            self.style = discord.ButtonStyle.primary

            other_player = view.player_o if user.id == view.player_x.id else view.player_x
            content = f"{interaction.message.content}\n\n🔄 **{user.display_name}** wants a rematch! **{other_player.mention}**, click **Accept Rematch** to play again."
            await interaction.response.edit_message(content=content, view=view)
        else:
            if user.id == view.rematch_requested_by.id:
                await interaction.response.send_message(
                    "You already requested a rematch! Wait for your opponent.",
                    ephemeral=True,
                )
                return

            # Reset game state and swap players so the other goes first
            view.player_x, view.player_o = view.player_o, view.player_x
            view.current_player = view.player_x
            view.board = [
                [0, 0, 0],
                [0, 0, 0],
                [0, 0, 0],
            ]
            view.rematch_requested_by = None

            view.clear_items()
            for y in range(3):
                for x in range(3):
                    view.add_item(TicTacToeButton(x, y))

            content = (
                f"❌ **{view.player_x.mention}** challenged **{view.player_o.mention}** (O) to a game of Tic-Tac-Toe!\n\n"
                f"It is **{view.player_x.mention}**'s turn (X)."
            )
            await interaction.response.edit_message(content=content, view=view)


class TicTacToeButton(discord.ui.Button):
    def __init__(self, x: int, y: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="\u200b", row=y)
        self.x = x
        self.y = y

    async def callback(self, interaction: discord.Interaction):
        assert self.view is not None
        view: TicTacToeView = self.view
        state = view.board[self.y][self.x]
        if state != 0:
            return

        if interaction.user.id != view.current_player.id:
            await interaction.response.send_message(
                "It's not your turn!", ephemeral=True
            )
            return

        if view.current_player == view.player_x:
            self.style = discord.ButtonStyle.danger
            self.label = "X"
            view.board[self.y][self.x] = 1
            view.current_player = view.player_o
            content = f"It is now **{view.player_o.mention}**'s turn (O)."
        else:
            self.style = discord.ButtonStyle.primary
            self.label = "O"
            view.board[self.y][self.x] = -1
            view.current_player = view.player_x
            content = f"It is now **{view.player_x.mention}**'s turn (X)."

        self.disabled = True
        winner = view.check_winner()
        if winner is not None:
            if winner == 1:
                content = f"🎉 **{view.player_x.mention}** won the game!"
            elif winner == -1:
                content = f"🎉 **{view.player_o.mention}** won the game!"
            else:
                content = "👔 It's a tie!"

            for child in view.children:
                if isinstance(child, TicTacToeButton):
                    child.disabled = True

            # Add the rematch button instead of stopping view
            view.add_item(RematchButton())

        await interaction.response.edit_message(content=content, view=view)


class TicTacToeView(discord.ui.View):
    def __init__(self, player_x: discord.Member, player_o: discord.Member):
        super().__init__(timeout=120)
        self.player_x = player_x
        self.player_o = player_o
        self.current_player = player_x
        self.rematch_requested_by = None
        self.board = [
            [0, 0, 0],
            [0, 0, 0],
            [0, 0, 0],
        ]

        for y in range(3):
            for x in range(3):
                self.add_item(TicTacToeButton(x, y))

    def check_winner(self):
        for row in self.board:
            row_sum = sum(row)
            if row_sum == 3:
                return 1
            elif row_sum == -3:
                return -1

        for col in range(3):
            col_sum = self.board[0][col] + self.board[1][col] + self.board[2][col]
            if col_sum == 3:
                return 1
            elif col_sum == -3:
                return -1

        diag1 = self.board[0][0] + self.board[1][1] + self.board[2][2]
        diag2 = self.board[0][2] + self.board[1][1] + self.board[2][0]
        if diag1 == 3 or diag2 == 3:
            return 1
        elif diag1 == -3 or diag2 == -3:
            return -1

        if all(self.board[y][x] != 0 for y in range(3) for x in range(3)):
            return 0

        return None


# ── Games Cog Class ──────────────────────────────────────────────────────────

class Games(commands.Cog):
    """Fun interactive games using Discord's modern UI."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── Time Bomb Command ──────────────────────────────────────────────────────
    @app_commands.command(
        name="timebomb", description="Play a game of Time Bomb defusal."
    )
    @app_commands.describe(
        opponent="Optionally invite another user to take turns cutting wires"
    )
    async def timebomb(
        self, interaction: discord.Interaction, opponent: discord.Member | None = None
    ):
        if opponent and opponent.bot:
            await interaction.response.send_message(
                "You cannot play against a bot!", ephemeral=True
            )
            return
        if opponent and opponent == interaction.user:
            await interaction.response.send_message(
                "You cannot play against yourself!", ephemeral=True
            )
            return

        view = TimeBombView(interaction.user, opponent)

        if opponent:
            turn_str = f"It is **{interaction.user.mention}**'s turn to cut a wire."
            desc = (
                f"A ticking bomb has been armed! 💣\n\n"
                f"There are **5 colored wires**.\n"
                f"- 🟢 One wire is the **Defusal** wire.\n"
                f"- 🔴 One wire is the **Detonation** wire.\n\n"
                f"Take turns cutting wires.\n\n"
                f"{turn_str}"
            )
        else:
            desc = (
                "A ticking bomb has been armed! 💣\n\n"
                "There are **5 colored wires**.\n"
                "- 🟢 One wire is the **Defusal** wire.\n"
                "- 🔴 One wire is the **Detonation** wire.\n\n"
                "Cut a wire to begin defusing!"
            )

        embed = info("⏳ Tick, tock... Cut a wire!", desc)
        await interaction.response.send_message(embed=embed, view=view)

    # ── Tic-Tac-Toe Command ────────────────────────────────────────────────────
    @app_commands.command(
        name="tictactoe", description="Play a game of Tic-Tac-Toe against another member."
    )
    @app_commands.describe(opponent="The member you want to challenge")
    async def tictactoe(self, interaction: discord.Interaction, opponent: discord.Member):
        if opponent.bot:
            await interaction.response.send_message(
                "You cannot play against a bot!", ephemeral=True
            )
            return
        if opponent == interaction.user:
            await interaction.response.send_message(
                "You cannot play against yourself!", ephemeral=True
            )
            return

        view = TicTacToeView(interaction.user, opponent)
        await interaction.response.send_message(
            f"❌ **{interaction.user.mention}** challenged **{opponent.mention}** (O) to a game of Tic-Tac-Toe!\n\n"
            f"It is **{interaction.user.mention}**'s turn (X).",
            view=view,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Games(bot))
