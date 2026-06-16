import asyncio
import random
import discord
from discord import app_commands
from discord.ext import commands
from database.db import get_pool, ensure_economy, add_balance
from utils.embeds import success, error, info
import config


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

async def get_balance(guild_id: int, user_id: int) -> int:
    row = await ensure_economy(guild_id, user_id)
    return row["balance"]

async def get_currency(guild_id: int) -> tuple[str, str]:
    pool = get_pool()
    row  = await pool.fetchrow("SELECT currency_name, currency_emoji FROM guild_settings WHERE guild_id=$1", guild_id)
    if row:
        return row["currency_name"], row["currency_emoji"]
    return "coins", "🪙"


# ══════════════════════════════════════════════════════════════════════════════
#  BLACKJACK
# ══════════════════════════════════════════════════════════════════════════════

SUITS  = ["♠️", "♥️", "♦️", "♣️"]
RANKS  = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]

def new_deck():
    return [(r, s) for s in SUITS for r in RANKS]

def card_value(rank: str) -> int:
    if rank in ("J", "Q", "K"): return 10
    if rank == "A":              return 11
    return int(rank)

def hand_value(hand: list) -> int:
    total = sum(card_value(r) for r, _ in hand)
    aces  = sum(1 for r, _ in hand if r == "A")
    while total > 21 and aces:
        total -= 10
        aces  -= 1
    return total

def fmt_hand(hand: list, hide_second: bool = False) -> str:
    if hide_second:
        return f"`{hand[0][0]}{hand[0][1]}` `??`"
    return " ".join(f"`{r}{s}`" for r, s in hand)


class BlackjackView(discord.ui.View):
    def __init__(self, player_id: int, deck: list, player: list, dealer: list,
                 bet: int, guild_id: int):
        super().__init__(timeout=60)
        self.player_id = player_id
        self.deck      = deck
        self.player    = player
        self.dealer    = dealer
        self.bet       = bet
        self.guild_id  = guild_id
        self.doubled   = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.player_id:
            await interaction.response.send_message("This isn't your game!", ephemeral=True)
            return False
        return True

    def _embed(self, result: str = None) -> discord.Embed:
        pval = hand_value(self.player)
        dval = hand_value(self.dealer)
        hide = result is None

        color = (discord.Color.green() if result == "win"
                 else discord.Color.red() if result == "lose"
                 else discord.Color.gold() if result == "push"
                 else discord.Color.blurple())

        embed = discord.Embed(title="🃏 Blackjack", color=color)
        embed.add_field(
            name=f"Dealer {'??' if hide else f'({dval})'}",
            value=fmt_hand(self.dealer, hide_second=hide),
            inline=False,
        )
        embed.add_field(
            name=f"You ({pval})",
            value=fmt_hand(self.player),
            inline=False,
        )
        if result:
            outcomes = {
                "win":  f"✅ You win **{self.bet:,}** coins!",
                "bj":   f"🎉 Blackjack! You win **{int(self.bet * 1.5):,}** coins!",
                "lose": f"❌ You lose **{self.bet:,}** coins.",
                "push": "🤝 Push — bet returned.",
                "bust": f"💥 Bust! You lose **{self.bet:,}** coins.",
            }
            embed.add_field(name="Result", value=outcomes.get(result, ""), inline=False)
        else:
            embed.set_footer(text=f"Bet: {self.bet:,} coins")
        return embed

    async def _end(self, interaction: discord.Interaction, result: str):
        gains = {
            "win":  self.bet,
            "bj":   int(self.bet * 1.5),
            "lose": -self.bet,
            "push": 0,
            "bust": -self.bet,
        }
        change = gains.get(result, 0)
        if change != 0:
            await add_balance(self.guild_id, self.player_id, change)

        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(embed=self._embed(result), view=self)
        self.stop()

    async def _dealer_play(self) -> str:
        while hand_value(self.dealer) < 17:
            self.dealer.append(self.deck.pop())
        pval = hand_value(self.player)
        dval = hand_value(self.dealer)
        if dval > 21:   return "win"
        if pval > dval: return "win"
        if pval < dval: return "lose"
        return "push"

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.green, emoji="👊")
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.player.append(self.deck.pop())
        if hand_value(self.player) > 21:
            return await self._end(interaction, "bust")
        if hand_value(self.player) == 21:
            result = await self._dealer_play()
            return await self._end(interaction, result)
        await interaction.response.edit_message(embed=self._embed(), view=self)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.red, emoji="✋")
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        result = await self._dealer_play()
        await self._end(interaction, result)

    @discord.ui.button(label="Double Down", style=discord.ButtonStyle.blurple, emoji="⚡")
    async def double(self, interaction: discord.Interaction, button: discord.ui.Button):
        bal = await get_balance(self.guild_id, self.player_id)
        if bal < self.bet * 2:
            return await interaction.response.send_message(
                embed=error("Insufficient Funds", "Not enough coins to double down."), ephemeral=True
            )
        self.bet *= 2
        self.player.append(self.deck.pop())
        if hand_value(self.player) > 21:
            return await self._end(interaction, "bust")
        result = await self._dealer_play()
        await self._end(interaction, result)


# ══════════════════════════════════════════════════════════════════════════════
#  TIC TAC TOE
# ══════════════════════════════════════════════════════════════════════════════

class TicTacToeButton(discord.ui.Button):
    def __init__(self, row: int, col: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="‎", row=row)
        self.row_pos = row
        self.col_pos = col

    async def callback(self, interaction: discord.Interaction):
        view: TicTacToeView = self.view
        if interaction.user.id != view.current_player.id:
            return await interaction.response.send_message("It's not your turn!", ephemeral=True)

        self.label    = view.current_symbol
        self.style    = discord.ButtonStyle.danger if view.current_symbol == "❌" else discord.ButtonStyle.blurple
        self.disabled = True
        view.board[self.row_pos][self.col_pos] = view.current_symbol

        winner = view.check_winner()
        if winner:
            for item in view.children:
                item.disabled = True
            embed = discord.Embed(
                title="❌⭕ Tic Tac Toe",
                description=f"🎉 {view.current_player.mention} wins!",
                color=discord.Color.green(),
            )
            await interaction.response.edit_message(embed=embed, view=view)
            view.stop()
        elif all(view.board[r][c] for r in range(3) for c in range(3)):
            for item in view.children:
                item.disabled = True
            embed = discord.Embed(title="❌⭕ Tic Tac Toe", description="🤝 It's a draw!", color=discord.Color.gold())
            await interaction.response.edit_message(embed=embed, view=view)
            view.stop()
        else:
            view.current_player = view.player2 if view.current_player == view.player1 else view.player1
            view.current_symbol = "⭕" if view.current_symbol == "❌" else "❌"
            embed = discord.Embed(
                title="❌⭕ Tic Tac Toe",
                description=f"Turn: {view.current_player.mention} ({view.current_symbol})",
                color=discord.Color.blurple(),
            )
            await interaction.response.edit_message(embed=embed, view=view)


class TicTacToeView(discord.ui.View):
    def __init__(self, player1: discord.Member, player2: discord.Member):
        super().__init__(timeout=120)
        self.player1        = player1
        self.player2        = player2
        self.current_player = player1
        self.current_symbol = "❌"
        self.board          = [[None]*3 for _ in range(3)]
        for r in range(3):
            for c in range(3):
                self.add_item(TicTacToeButton(r, c))

    def check_winner(self) -> bool:
        b = self.board
        lines = (
            [b[r] for r in range(3)] +
            [[b[r][c] for r in range(3)] for c in range(3)] +
            [[b[i][i] for i in range(3)], [b[i][2-i] for i in range(3)]]
        )
        return any(all(c == self.current_symbol for c in line) for line in lines)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id not in (self.player1.id, self.player2.id):
            await interaction.response.send_message("You're not in this game!", ephemeral=True)
            return False
        return True


# ══════════════════════════════════════════════════════════════════════════════
#  CONNECT FOUR
# ══════════════════════════════════════════════════════════════════════════════

C4_ROWS, C4_COLS = 6, 7
C4_EMPTY, C4_RED, C4_YELLOW = "⬛", "🔴", "🟡"

class ConnectFourView(discord.ui.View):
    def __init__(self, player1: discord.Member, player2: discord.Member):
        super().__init__(timeout=180)
        self.player1        = player1
        self.player2        = player2
        self.current_player = player1
        self.current_color  = C4_RED
        self.board          = [[C4_EMPTY]*C4_COLS for _ in range(C4_ROWS)]
        for col in range(C4_COLS):
            self.add_item(self._col_button(col))

    def _col_button(self, col: int) -> discord.ui.Button:
        btn          = discord.ui.Button(label=str(col+1), style=discord.ButtonStyle.secondary, row=0)
        btn.callback = self._make_callback(col)
        return btn

    def _make_callback(self, col: int):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.current_player.id:
                return await interaction.response.send_message("It's not your turn!", ephemeral=True)

            # Find lowest empty row
            row = next((r for r in range(C4_ROWS-1, -1, -1) if self.board[r][col] == C4_EMPTY), None)
            if row is None:
                return await interaction.response.send_message("That column is full!", ephemeral=True)

            self.board[row][col] = self.current_color

            if self._check_winner(row, col):
                for item in self.children:
                    item.disabled = True
                await interaction.response.edit_message(embed=self._embed(f"🎉 {self.current_player.mention} wins!"), view=self)
                self.stop()
            elif all(self.board[0][c] != C4_EMPTY for c in range(C4_COLS)):
                for item in self.children:
                    item.disabled = True
                await interaction.response.edit_message(embed=self._embed("🤝 Draw!"), view=self)
                self.stop()
            else:
                self.current_player = self.player2 if self.current_player == self.player1 else self.player1
                self.current_color  = C4_YELLOW if self.current_color == C4_RED else C4_RED
                await interaction.response.edit_message(embed=self._embed(), view=self)
        return callback

    def _embed(self, result: str = None) -> discord.Embed:
        board_str = "\n".join("".join(row) for row in self.board)
        board_str += "\n1️⃣2️⃣3️⃣4️⃣5️⃣6️⃣7️⃣"
        desc  = board_str
        desc += f"\n\n{result}" if result else f"\n\nTurn: {self.current_player.mention} ({self.current_color})"
        return discord.Embed(title="🔴 Connect Four", description=desc, color=discord.Color.blurple())

    def _check_winner(self, row: int, col: int) -> bool:
        color = self.current_color
        def count(dr, dc):
            r, c, n = row+dr, col+dc, 0
            while 0<=r<C4_ROWS and 0<=c<C4_COLS and self.board[r][c]==color:
                n+=1; r+=dr; c+=dc
            return n
        for dr, dc in [(0,1),(1,0),(1,1),(1,-1)]:
            if count(dr,dc)+count(-dr,-dc)+1 >= 4:
                return True
        return False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id not in (self.player1.id, self.player2.id):
            await interaction.response.send_message("You're not in this game!", ephemeral=True)
            return False
        return True


# ══════════════════════════════════════════════════════════════════════════════
#  HIGHER OR LOWER
# ══════════════════════════════════════════════════════════════════════════════

class HigherLowerView(discord.ui.View):
    def __init__(self, player_id: int, number: int, low: int, high: int, attempts: int):
        super().__init__(timeout=60)
        self.player_id = player_id
        self.number    = number
        self.low       = low
        self.high      = high
        self.attempts  = attempts

    async def interaction_check(self, i: discord.Interaction) -> bool:
        if i.user.id != self.player_id:
            await i.response.send_message("Not your game!", ephemeral=True)
            return False
        return True

    def _embed(self, msg: str = None) -> discord.Embed:
        embed = discord.Embed(title="🎯 Higher or Lower", color=discord.Color.blurple())
        embed.add_field(name="Range",    value=f"`{self.low}` — `{self.high}`")
        embed.add_field(name="Attempts", value=f"`{self.attempts}`")
        if msg:
            embed.add_field(name="Hint", value=msg, inline=False)
        return embed

    @discord.ui.button(label="Lower", emoji="⬇️", style=discord.ButtonStyle.red)
    async def lower(self, i: discord.Interaction, b: discord.ui.Button):
        self.high     = self.number - 1
        self.number   = random.randint(self.low, self.high) if self.low <= self.high else self.number
        self.attempts += 1
        await i.response.edit_message(embed=self._embed("New number set! Is it higher or lower?"), view=self)

    @discord.ui.button(label="Higher", emoji="⬆️", style=discord.ButtonStyle.green)
    async def higher(self, i: discord.Interaction, b: discord.ui.Button):
        self.low      = self.number + 1
        self.number   = random.randint(self.low, self.high) if self.low <= self.high else self.number
        self.attempts += 1
        await i.response.edit_message(embed=self._embed("New number set! Is it higher or lower?"), view=self)

    @discord.ui.button(label="Guess!", emoji="🎯", style=discord.ButtonStyle.blurple)
    async def guess(self, i: discord.Interaction, b: discord.ui.Button):
        await i.response.send_modal(GuessModal(self))


class GuessModal(discord.ui.Modal, title="Guess the Number"):
    guess = discord.ui.TextInput(label="Your Guess", placeholder="Enter a number...")

    def __init__(self, view: HigherLowerView):
        super().__init__()
        self.game_view = view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = int(self.guess.value)
        except ValueError:
            return await interaction.response.send_message("Enter a valid number!", ephemeral=True)

        if val == self.game_view.number:
            for item in self.game_view.children:
                item.disabled = True
            embed = discord.Embed(
                title="🎯 Higher or Lower",
                description=f"🎉 Correct! The number was **{self.game_view.number}**!\nSolved in **{self.game_view.attempts}** attempts.",
                color=discord.Color.green(),
            )
            await interaction.response.edit_message(embed=embed, view=self.game_view)
            self.game_view.stop()
        elif val < self.game_view.number:
            self.game_view.attempts += 1
            await interaction.response.edit_message(
                embed=self.game_view._embed(f"**{val}** is too low! ⬆️"), view=self.game_view
            )
        else:
            self.game_view.attempts += 1
            await interaction.response.edit_message(
                embed=self.game_view._embed(f"**{val}** is too high! ⬇️"), view=self.game_view
            )


# ══════════════════════════════════════════════════════════════════════════════
#  SNAKE
# ══════════════════════════════════════════════════════════════════════════════

GRID   = 6
EMPTY  = "⬛"
FOOD   = "🍎"
HEAD   = "🟩"
BODY   = "🟢"

class SnakeView(discord.ui.View):
    def __init__(self, player_id: int):
        super().__init__(timeout=120)
        self.player_id = player_id
        self.snake     = [(GRID//2, GRID//2)]
        self.direction = (0, 1)
        self.food      = self._place_food()
        self.score     = 0
        self.alive     = True

    def _place_food(self):
        empty = [(r,c) for r in range(GRID) for c in range(GRID) if (r,c) not in self.snake]
        return random.choice(empty) if empty else None

    def _render(self) -> str:
        grid = [[EMPTY]*GRID for _ in range(GRID)]
        for r, c in self.snake[1:]:
            grid[r][c] = BODY
        hr, hc = self.snake[0]
        grid[hr][hc] = HEAD
        if self.food:
            grid[self.food[0]][self.food[1]] = FOOD
        return "\n".join("".join(row) for row in grid)

    def _move(self, dr: int, dc: int) -> bool:
        self.direction = (dr, dc)
        hr, hc = self.snake[0]
        nr, nc = hr+dr, hc+dc
        if not (0<=nr<GRID and 0<=nc<GRID) or (nr,nc) in self.snake:
            return False
        self.snake.insert(0, (nr,nc))
        if (nr,nc) == self.food:
            self.score += 1
            self.food = self._place_food()
        else:
            self.snake.pop()
        return True

    def _embed(self, dead: bool = False) -> discord.Embed:
        color = discord.Color.red() if dead else discord.Color.green()
        embed = discord.Embed(
            title="🐍 Snake",
            description=self._render(),
            color=color,
        )
        embed.add_field(name="Score", value=f"`{self.score}`")
        if dead:
            embed.add_field(name="Game Over!", value="You hit a wall or yourself.")
        return embed

    async def _handle(self, interaction: discord.Interaction, dr: int, dc: int):
        if not self.alive:
            return await interaction.response.send_message("Game over!", ephemeral=True)
        if not self._move(dr, dc):
            self.alive = True
            for item in self.children:
                item.disabled = True
            await interaction.response.edit_message(embed=self._embed(dead=True), view=self)
            self.stop()
        else:
            await interaction.response.edit_message(embed=self._embed(), view=self)

    async def interaction_check(self, i: discord.Interaction) -> bool:
        if i.user.id != self.player_id:
            await i.response.send_message("Not your game!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="↑", style=discord.ButtonStyle.secondary, row=0)
    async def up(self, i, b):    await self._handle(i, -1,  0)

    @discord.ui.button(label="↓", style=discord.ButtonStyle.secondary, row=1)
    async def down(self, i, b):  await self._handle(i,  1,  0)

    @discord.ui.button(label="←", style=discord.ButtonStyle.secondary, row=1)
    async def left(self, i, b):  await self._handle(i,  0, -1)

    @discord.ui.button(label="→", style=discord.ButtonStyle.secondary, row=1)
    async def right(self, i, b): await self._handle(i,  0,  1)


# ══════════════════════════════════════════════════════════════════════════════
#  MINESWEEPER
# ══════════════════════════════════════════════════════════════════════════════

def generate_minesweeper(rows: int = 8, cols: int = 8, mines: int = 10) -> str:
    grid  = [[0]*cols for _ in range(rows)]
    bombs = set()
    while len(bombs) < mines:
        bombs.add((random.randint(0,rows-1), random.randint(0,cols-1)))

    for r, c in bombs:
        grid[r][c] = -1
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == -1:
                continue
            grid[r][c] = sum(
                1 for dr in [-1,0,1] for dc in [-1,0,1]
                if (r+dr, c+dc) in bombs
            )

    nums = ["0️⃣","1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣"]
    lines = []
    for r in range(rows):
        row = ""
        for c in range(cols):
            val = grid[r][c]
            cell = "💣" if val == -1 else nums[val]
            row += f"||{cell}||"
        lines.append(row)
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
#  HORSE RACING
# ══════════════════════════════════════════════════════════════════════════════

HORSES = ["🐴", "🦄", "🐎", "🏇"]
HORSE_NAMES = ["Shadowfax", "Lightning", "Blaze", "Thunder"]

class HorseRaceView(discord.ui.View):
    def __init__(self, player_id: int, bet: int, guild_id: int):
        super().__init__(timeout=30)
        self.player_id = player_id
        self.bet       = bet
        self.guild_id  = guild_id
        self.chosen    = None

        for i, (emoji, name) in enumerate(zip(HORSES, HORSE_NAMES)):
            btn          = discord.ui.Button(label=f"{emoji} {name}", style=discord.ButtonStyle.secondary, row=0)
            btn.callback = self._make_pick(i)
            self.add_item(btn)

    def _make_pick(self, idx: int):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.player_id:
                return await interaction.response.send_message("Not your race!", ephemeral=True)
            self.chosen = idx
            for item in self.children:
                item.disabled = True
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="🐴 Horse Racing",
                    description=f"You bet on **{HORSES[idx]} {HORSE_NAMES[idx]}**!\nRace starting...",
                    color=discord.Color.blurple(),
                ),
                view=self,
            )
            await asyncio.sleep(1)
            await self._run_race(interaction)
        return callback

    async def _run_race(self, interaction: discord.Interaction):
        positions = [0] * 4
        track_len = 10

        for _ in range(20):
            winner = next((i for i, p in enumerate(positions) if p >= track_len), None)
            if winner is not None:
                break
            for i in range(4):
                positions[i] += random.randint(0, 2)

            track = ""
            for i, (emoji, name, pos) in enumerate(zip(HORSES, HORSE_NAMES, positions)):
                bar   = "▓" * min(pos, track_len) + "░" * max(track_len - pos, 0)
                track += f"{emoji} `{bar}` {name}\n"

            try:
                await interaction.edit_original_response(
                    embed=discord.Embed(title="🐴 Horse Racing — 🏁", description=track, color=discord.Color.blurple())
                )
            except discord.HTTPException:
                pass
            await asyncio.sleep(0.8)

        winner = max(range(4), key=lambda i: positions[i])
        won    = winner == self.chosen
        change = self.bet * 3 if won else -self.bet
        if self.bet > 0:
            await add_balance(self.guild_id, self.player_id, change)

        result_embed = discord.Embed(
            title=f"🏆 {HORSES[winner]} {HORSE_NAMES[winner]} wins!",
            description=(
                f"{'🎉 You won! **+' if won else '💸 You lost. **-'}{abs(change):,}** coins."
                if self.bet > 0 else
                f"{'🎉 Your horse won!' if won else '💸 Your horse lost.'}"
            ),
            color=discord.Color.green() if won else discord.Color.red(),
        )
        try:
            await interaction.edit_original_response(embed=result_embed, view=None)
        except discord.HTTPException:
            pass

    async def interaction_check(self, i: discord.Interaction) -> bool:
        if i.user.id != self.player_id:
            await i.response.send_message("Not your race!", ephemeral=True)
            return False
        return True


# ══════════════════════════════════════════════════════════════════════════════
#  DICE DUEL
# ══════════════════════════════════════════════════════════════════════════════

class DiceDuelView(discord.ui.View):
    def __init__(self, challenger: discord.Member, opponent: discord.Member,
                 bet: int, guild_id: int):
        super().__init__(timeout=60)
        self.challenger = challenger
        self.opponent   = opponent
        self.bet        = bet
        self.guild_id   = guild_id
        self.rolls      = {}

    @discord.ui.button(label="Roll Dice 🎲", style=discord.ButtonStyle.green)
    async def roll(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in (self.challenger.id, self.opponent.id):
            return await interaction.response.send_message("You're not in this duel!", ephemeral=True)
        if interaction.user.id in self.rolls:
            return await interaction.response.send_message("You already rolled!", ephemeral=True)

        self.rolls[interaction.user.id] = random.randint(1, 6)

        if len(self.rolls) < 2:
            embed = discord.Embed(title="🎲 Dice Duel", color=discord.Color.blurple())
            embed.add_field(name=self.challenger.display_name,
                            value=f"🎲 {self.rolls.get(self.challenger.id, '?')}")
            embed.add_field(name=self.opponent.display_name,
                            value=f"🎲 {self.rolls.get(self.opponent.id, '?')}")
            embed.set_footer(text="Waiting for both players to roll...")
            return await interaction.response.edit_message(embed=embed, view=self)

        # Both rolled
        cr = self.rolls[self.challenger.id]
        or_ = self.rolls[self.opponent.id]
        for item in self.children:
            item.disabled = True

        if cr > or_:
            winner, loser = self.challenger, self.opponent
        elif or_ > cr:
            winner, loser = self.opponent, self.challenger
        else:
            winner, loser = None, None

        if self.bet > 0 and winner:
            await add_balance(self.guild_id, winner.id, self.bet)
            await add_balance(self.guild_id, loser.id, -self.bet)

        embed = discord.Embed(
            title="🎲 Dice Duel Result",
            color=discord.Color.green() if winner else discord.Color.gold(),
        )
        embed.add_field(name=self.challenger.display_name, value=f"🎲 **{cr}**")
        embed.add_field(name=self.opponent.display_name,   value=f"🎲 **{or_}**")
        embed.add_field(
            name="Result",
            value=f"🏆 {winner.mention} wins **{self.bet:,}** coins!" if winner and self.bet > 0
            else f"🏆 {winner.mention} wins!" if winner
            else "🤝 It's a tie!",
            inline=False,
        )
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()


# ══════════════════════════════════════════════════════════════════════════════
#  TRIVIA
# ══════════════════════════════════════════════════════════════════════════════

TRIVIA_QUESTIONS = [
    ("What is the capital of France?",           ["Paris", "London", "Berlin", "Madrid"],          0),
    ("How many sides does a hexagon have?",       ["5", "6", "7", "8"],                             1),
    ("What planet is closest to the Sun?",        ["Venus", "Earth", "Mercury", "Mars"],            2),
    ("What is 12 × 12?",                          ["124", "144", "134", "154"],                     1),
    ("Who wrote Romeo and Juliet?",               ["Dickens", "Shakespeare", "Tolkien", "Austen"],  1),
    ("What gas do plants absorb?",                ["Oxygen", "Nitrogen", "CO2", "Hydrogen"],        2),
    ("How many continents are there?",            ["5", "6", "7", "8"],                             2),
    ("What is the fastest land animal?",          ["Lion", "Cheetah", "Leopard", "Horse"],          1),
    ("In what year did WW2 end?",                 ["1943", "1944", "1945", "1946"],                 2),
    ("What is the chemical symbol for gold?",     ["Go", "Gd", "Au", "Ag"],                        2),
    ("How many bones in the human body?",         ["196", "206", "216", "226"],                     1),
    ("What is the largest ocean?",                ["Atlantic", "Indian", "Arctic", "Pacific"],      3),
    ("Who painted the Mona Lisa?",                ["Picasso", "Da Vinci", "Rembrandt", "Monet"],    1),
    ("What is the square root of 144?",           ["11", "12", "13", "14"],                         1),
    ("Which element has symbol 'O'?",             ["Gold", "Osmium", "Oxygen", "Oganesson"],        2),
    ("How many players in a soccer team?",        ["9", "10", "11", "12"],                          2),
    ("What is the longest river in the world?",   ["Amazon", "Yangtze", "Nile", "Mississippi"],     2),
    ("What language is most spoken worldwide?",   ["English", "Spanish", "Mandarin", "Hindi"],      2),
    ("What is the hardest natural substance?",    ["Gold", "Iron", "Diamond", "Quartz"],            2),
    ("Which planet has the most moons?",          ["Jupiter", "Saturn", "Uranus", "Neptune"],       1),
]

class TriviaView(discord.ui.View):
    def __init__(self, player_id: int, question: str, options: list[str],
                 answer: int, reward: int, guild_id: int):
        super().__init__(timeout=20)
        self.player_id = player_id
        self.answer    = answer
        self.reward    = reward
        self.guild_id  = guild_id
        self.answered  = False

        labels = ["🇦", "🇧", "🇨", "🇩"]
        for i, opt in enumerate(options):
            btn          = discord.ui.Button(label=f"{labels[i]} {opt}", style=discord.ButtonStyle.secondary, row=0)
            btn.callback = self._make_answer(i)
            self.add_item(btn)

    def _make_answer(self, idx: int):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.player_id:
                return await interaction.response.send_message("Not your question!", ephemeral=True)
            if self.answered:
                return await interaction.response.send_message("Already answered!", ephemeral=True)

            self.answered = True
            correct       = idx == self.answer

            for item in self.children:
                item.disabled = True
                if hasattr(item, 'callback'):
                    item.style = discord.ButtonStyle.secondary

            if correct and self.reward > 0:
                await add_balance(self.guild_id, self.player_id, self.reward)
                # Update trivia score
                try:
                    pool = get_pool()
                    await pool.execute(
                        """INSERT INTO trivia_scores (guild_id, user_id, correct)
                           VALUES ($1,$2,1) ON CONFLICT (guild_id, user_id)
                           DO UPDATE SET correct = trivia_scores.correct + 1""",
                        self.guild_id, self.player_id
                    )
                except Exception:
                    pass

            embed = discord.Embed(
                title="✅ Correct!" if correct else "❌ Wrong!",
                color=discord.Color.green() if correct else discord.Color.red(),
            )
            if correct and self.reward > 0:
                embed.description = f"You earned **{self.reward:,}** coins! 🎉"
            elif not correct:
                embed.description = f"The correct answer was option **{self.answer+1}**."

            await interaction.response.edit_message(view=self)
            await interaction.followup.send(embed=embed, ephemeral=True)
            self.stop()
        return callback

    async def interaction_check(self, i: discord.Interaction) -> bool:
        if i.user.id != self.player_id:
            await i.response.send_message("Not your question!", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


# ══════════════════════════════════════════════════════════════════════════════
#  COG
# ══════════════════════════════════════════════════════════════════════════════

class Games(commands.Cog):
    """Mini-games — some with economy integration."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── /blackjack ────────────────────────────────────────────────────────────
    @app_commands.command(name="blackjack", description="Play blackjack against the dealer.")
    @app_commands.describe(bet="Amount to bet (0 for free play)")
    async def blackjack(self, interaction: discord.Interaction, bet: app_commands.Range[int, 0, 100000] = 0):
        if bet > 0:
            bal = await get_balance(interaction.guild_id, interaction.user.id)
            if bet > bal:
                return await interaction.response.send_message(
                    embed=error("Insufficient Funds", f"You only have **{bal:,}** coins."), ephemeral=True
                )

        deck   = new_deck()
        random.shuffle(deck)
        player = [deck.pop(), deck.pop()]
        dealer = [deck.pop(), deck.pop()]

        view = BlackjackView(interaction.user.id, deck, player, dealer, bet, interaction.guild_id)

        # Check natural blackjack
        if hand_value(player) == 21:
            if bet > 0:
                await add_balance(interaction.guild_id, interaction.user.id, int(bet * 1.5))
            embed = view._embed("bj")
            return await interaction.response.send_message(embed=embed)

        await interaction.response.send_message(embed=view._embed(), view=view)

    # ── /dice ─────────────────────────────────────────────────────────────────
    @app_commands.command(name="dice", description="Challenge a member to a dice duel.")
    @app_commands.describe(member="Member to challenge", bet="Amount to bet (0 for fun)")
    async def dice(self, interaction: discord.Interaction, member: discord.Member,
                   bet: app_commands.Range[int, 0, 100000] = 0):
        if member == interaction.user or member.bot:
            return await interaction.response.send_message(embed=error("Invalid Target"), ephemeral=True)

        if bet > 0:
            bal = await get_balance(interaction.guild_id, interaction.user.id)
            if bet > bal:
                return await interaction.response.send_message(
                    embed=error("Insufficient Funds", f"You only have **{bal:,}** coins."), ephemeral=True
                )

        view  = DiceDuelView(interaction.user, member, bet, interaction.guild_id)
        embed = discord.Embed(
            title="🎲 Dice Duel",
            description=f"{interaction.user.mention} has challenged {member.mention}!\n"
                        f"{'Bet: **' + str(bet) + '** coins\n' if bet > 0 else ''}"
                        f"Both players press **Roll Dice** to roll!",
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, view=view)

    # ── /race ─────────────────────────────────────────────────────────────────
    @app_commands.command(name="race", description="Bet on a horse race!")
    @app_commands.describe(bet="Amount to bet (0 for free)")
    async def race(self, interaction: discord.Interaction, bet: app_commands.Range[int, 0, 100000] = 0):
        if bet > 0:
            bal = await get_balance(interaction.guild_id, interaction.user.id)
            if bet > bal:
                return await interaction.response.send_message(
                    embed=error("Insufficient Funds", f"You only have **{bal:,}** coins."), ephemeral=True
                )

        view  = HorseRaceView(interaction.user.id, bet, interaction.guild_id)
        embed = discord.Embed(
            title="🐴 Horse Racing",
            description=f"{'Bet: **' + str(bet) + '** coins — p' if bet > 0 else 'P'}ick your horse!",
            color=discord.Color.blurple(),
        )
        for emoji, name in zip(HORSES, HORSE_NAMES):
            embed.add_field(name=f"{emoji} {name}", value="Ready to race!", inline=True)
        await interaction.response.send_message(embed=embed, view=view)

    # ── /trivia ───────────────────────────────────────────────────────────────
    @app_commands.command(name="trivia", description="Answer a trivia question for coins.")
    @app_commands.describe(reward="Coin reward for correct answer (0 for fun)")
    async def trivia(self, interaction: discord.Interaction, reward: app_commands.Range[int, 0, 1000] = 50):
        q, options, answer = random.choice(TRIVIA_QUESTIONS)
        view  = TriviaView(interaction.user.id, q, options, answer, reward, interaction.guild_id)
        embed = discord.Embed(
            title="❓ Trivia",
            description=f"**{q}**",
            color=discord.Color.blurple(),
        )
        labels = ["🇦", "🇧", "🇨", "🇩"]
        for i, opt in enumerate(options):
            embed.add_field(name=f"{labels[i]}", value=opt, inline=True)
        embed.set_footer(text=f"{'Reward: ' + str(reward) + ' coins • ' if reward else ''}20 seconds to answer!")
        await interaction.response.send_message(embed=embed, view=view)

    # ── /tictactoe ────────────────────────────────────────────────────────────
    @app_commands.command(name="tictactoe", description="Play Tic Tac Toe against another member.")
    @app_commands.describe(member="Member to challenge")
    async def tictactoe(self, interaction: discord.Interaction, member: discord.Member):
        if member == interaction.user or member.bot:
            return await interaction.response.send_message(embed=error("Invalid Target"), ephemeral=True)

        view  = TicTacToeView(interaction.user, member)
        embed = discord.Embed(
            title="❌⭕ Tic Tac Toe",
            description=f"Turn: {interaction.user.mention} (❌)",
            color=discord.Color.blurple(),
        )
        embed.set_footer(text=f"{interaction.user.display_name} vs {member.display_name}")
        await interaction.response.send_message(embed=embed, view=view)

    # ── /connectfour ──────────────────────────────────────────────────────────
    @app_commands.command(name="connectfour", description="Play Connect Four against another member.")
    @app_commands.describe(member="Member to challenge")
    async def connectfour(self, interaction: discord.Interaction, member: discord.Member):
        if member == interaction.user or member.bot:
            return await interaction.response.send_message(embed=error("Invalid Target"), ephemeral=True)

        view  = ConnectFourView(interaction.user, member)
        await interaction.response.send_message(embed=view._embed(), view=view)

    # ── /minesweeper ──────────────────────────────────────────────────────────
    @app_commands.command(name="minesweeper", description="Generate a minesweeper board.")
    @app_commands.describe(difficulty="Board difficulty")
    @app_commands.choices(difficulty=[
        app_commands.Choice(name="Easy (6×6, 6 mines)",    value="easy"),
        app_commands.Choice(name="Medium (8×8, 10 mines)", value="medium"),
        app_commands.Choice(name="Hard (9×9, 15 mines)",   value="hard"),
    ])
    async def minesweeper(self, interaction: discord.Interaction, difficulty: str = "medium"):
        settings = {"easy": (6,6,6), "medium": (8,8,10), "hard": (9,9,15)}
        rows, cols, mines = settings[difficulty]
        board = generate_minesweeper(rows, cols, mines)
        embed = discord.Embed(
            title="💣 Minesweeper",
            description=board,
            color=discord.Color.blurple(),
        )
        embed.set_footer(text=f"{difficulty.title()} • {rows}×{cols} • {mines} mines • Click to reveal!")
        await interaction.response.send_message(embed=embed)

    # ── /higherorlower ────────────────────────────────────────────────────────
    @app_commands.command(name="higherorlower", description="Guess the number — higher or lower?")
    @app_commands.describe(maximum="The maximum number (default 100)")
    async def higherorlower(self, interaction: discord.Interaction,
                            maximum: app_commands.Range[int, 10, 10000] = 100):
        number = random.randint(1, maximum)
        view   = HigherLowerView(interaction.user.id, number, 1, maximum, 0)
        embed  = view._embed(f"I'm thinking of a number between **1** and **{maximum}**. Is it higher or lower than **{number}**?")
        await interaction.response.send_message(embed=embed, view=view)

    # ── /snake ────────────────────────────────────────────────────────────────
    @app_commands.command(name="snake", description="Play Snake!")
    async def snake(self, interaction: discord.Interaction):
        view  = SnakeView(interaction.user.id)
        embed = discord.Embed(
            title="🐍 Snake",
            description=view._render(),
            color=discord.Color.green(),
        )
        embed.add_field(name="Score", value="`0`")
        embed.set_footer(text="Use the buttons to move!")
        await interaction.response.send_message(embed=embed, view=view)

    # ── /triviastats ──────────────────────────────────────────────────────────
    @app_commands.command(name="triviastats", description="Check your trivia stats.")
    @app_commands.describe(member="Member to check (defaults to you)")
    async def triviastats(self, interaction: discord.Interaction, member: discord.Member | None = None):
        target = member or interaction.user
        try:
            pool = get_pool()
            row  = await pool.fetchrow(
                "SELECT * FROM trivia_scores WHERE guild_id=$1 AND user_id=$2",
                interaction.guild_id, target.id
            )
        except Exception:
            row = None

        if not row:
            return await interaction.response.send_message(
                embed=info("No Stats", f"{target.mention} hasn't played trivia yet."), ephemeral=True
            )

        total    = row["correct"] + row["wrong"]
        accuracy = round((row["correct"] / total) * 100) if total else 0
        embed    = discord.Embed(title=f"❓ Trivia Stats — {target.display_name}", color=config.BOT_COLOR)
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="✅ Correct", value=f"`{row['correct']}`")
        embed.add_field(name="❌ Wrong",   value=f"`{row['wrong']}`")
        embed.add_field(name="🎯 Accuracy", value=f"`{accuracy}%`")
        await interaction.response.send_message(embed=embed)

    # ── Error handler ─────────────────────────────────────────────────────────
    async def cog_app_command_error(self, interaction: discord.Interaction, err: app_commands.AppCommandError):
        msg = f"`{err}`"
        if interaction.response.is_done():
            await interaction.followup.send(embed=error("Error", msg), ephemeral=True)
        else:
            await interaction.response.send_message(embed=error("Error", msg), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Games(bot))
