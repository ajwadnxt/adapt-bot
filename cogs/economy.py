import datetime
import random
import discord
from discord import app_commands
from discord.ext import commands
from database import db
from utils.checks import is_admin
from utils.embeds import success, error, info
from utils.paginator import Paginator


WORK_RESPONSES = [
    "You worked as a chef and earned {amount} {currency}!",
    "You delivered packages and earned {amount} {currency}!",
    "You wrote code for 8 hours and earned {amount} {currency}!",
    "You drove a taxi and earned {amount} {currency}!",
    "You streamed games and earned {amount} {currency}!",
    "You sold handmade crafts and earned {amount} {currency}!",
    "You tutored students and earned {amount} {currency}!",
]

WORK_COOLDOWN  = 3600   # 1 hour
DAILY_COOLDOWN = 86400  # 24 hours


class Economy(commands.Cog):
    """Economy system — coins, daily, work, shop, leaderboard."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _get_cfg(self, guild_id: int):
        return await db.ensure_guild(guild_id)

    async def _ensure(self, guild_id: int, user_id: int):
        return await db.ensure_economy(guild_id, user_id)

    def _currency(self, cfg) -> str:
        return f"{cfg['currency_emoji']} {cfg['currency_name'].title()}"

    # ── /balance ──────────────────────────────────────────────────────────────
    @app_commands.command(name="balance", description="Check your or another member's balance.")
    @app_commands.describe(member="Member to check (defaults to you)")
    async def balance(self, interaction: discord.Interaction, member: discord.Member | None = None):
        cfg = await self._get_cfg(interaction.guild_id)
        if not cfg["economy_enabled"]:
            return await interaction.response.send_message(embed=error("Economy Disabled"), ephemeral=True)

        target = member or interaction.user
        row    = await self._ensure(interaction.guild_id, target.id)
        total  = row["balance"] + row["bank"]

        embed = discord.Embed(title=f"{cfg['currency_emoji']} {target.display_name}'s Balance", color=0xFFD700)
        embed.add_field(name="Wallet", value=f"`{row['balance']:,}` {cfg['currency_name']}")
        embed.add_field(name="Bank",   value=f"`{row['bank']:,}` {cfg['currency_name']}")
        embed.add_field(name="Total",  value=f"`{total:,}` {cfg['currency_name']}")
        embed.set_thumbnail(url=target.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    # ── /daily ────────────────────────────────────────────────────────────────
    @app_commands.command(name="daily", description="Claim your daily coins.")
    async def daily(self, interaction: discord.Interaction):
        cfg = await self._get_cfg(interaction.guild_id)
        if not cfg["economy_enabled"]:
            return await interaction.response.send_message(embed=error("Economy Disabled"), ephemeral=True)

        row = await self._ensure(interaction.guild_id, interaction.user.id)

        if row["last_daily"]:
            elapsed = (datetime.datetime.now(datetime.timezone.utc) - row["last_daily"]).total_seconds()
            if elapsed < DAILY_COOLDOWN:
                remaining = int(DAILY_COOLDOWN - elapsed)
                h, m = divmod(remaining // 60, 60)
                return await interaction.response.send_message(
                    embed=error("Already Claimed", f"Come back in **{h}h {m}m**."), ephemeral=True
                )

        amount = cfg["daily_amount"]
        await db.add_balance(interaction.guild_id, interaction.user.id, amount)
        await db.set_daily(interaction.guild_id, interaction.user.id)

        embed = success(
            "Daily Claimed!",
            f"You received **{amount:,}** {cfg['currency_emoji']} {cfg['currency_name']}!\nCome back in **24 hours**."
        )
        await interaction.response.send_message(embed=embed)

    # ── /work ─────────────────────────────────────────────────────────────────
    @app_commands.command(name="work", description="Work to earn coins (1 hour cooldown).")
    async def work(self, interaction: discord.Interaction):
        cfg = await self._get_cfg(interaction.guild_id)
        if not cfg["economy_enabled"]:
            return await interaction.response.send_message(embed=error("Economy Disabled"), ephemeral=True)

        row = await self._ensure(interaction.guild_id, interaction.user.id)

        if row["last_work"]:
            elapsed = (datetime.datetime.now(datetime.timezone.utc) - row["last_work"]).total_seconds()
            if elapsed < WORK_COOLDOWN:
                remaining = int(WORK_COOLDOWN - elapsed)
                m, s = divmod(remaining // 60, 60)
                return await interaction.response.send_message(
                    embed=error("Too Tired", f"You can work again in **{m}m {s}s**."), ephemeral=True
                )

        amount = random.randint(50, 200)
        await db.add_balance(interaction.guild_id, interaction.user.id, amount)
        await db.get_pool().execute(
            "UPDATE economy SET last_work=NOW() WHERE guild_id=$1 AND user_id=$2",
            interaction.guild_id, interaction.user.id,
        )

        msg = random.choice(WORK_RESPONSES).format(amount=f"{amount:,}", currency=cfg["currency_name"])
        await interaction.response.send_message(embed=success("💼 Work Complete", msg))

    # ── /deposit ──────────────────────────────────────────────────────────────
    @app_commands.command(name="deposit", description="Deposit coins into your bank.")
    @app_commands.describe(amount="Amount to deposit (or 'all')")
    async def deposit(self, interaction: discord.Interaction, amount: str):
        cfg = await self._get_cfg(interaction.guild_id)
        if not cfg["economy_enabled"]:
            return await interaction.response.send_message(embed=error("Economy Disabled"), ephemeral=True)

        row = await self._ensure(interaction.guild_id, interaction.user.id)
        amt = row["balance"] if amount.lower() == "all" else self._parse_amount(amount)

        if amt is None or amt <= 0:
            return await interaction.response.send_message(embed=error("Invalid Amount"), ephemeral=True)
        if amt > row["balance"]:
            return await interaction.response.send_message(
                embed=error("Insufficient Funds", f"You only have `{row['balance']:,}` in your wallet."), ephemeral=True
            )

        await db.get_pool().execute(
            "UPDATE economy SET balance=balance-$3, bank=bank+$3 WHERE guild_id=$1 AND user_id=$2",
            interaction.guild_id, interaction.user.id, amt,
        )
        await interaction.response.send_message(
            embed=success("Deposited", f"Deposited **{amt:,}** {cfg['currency_emoji']} into your bank.")
        )

    # ── /withdraw ─────────────────────────────────────────────────────────────
    @app_commands.command(name="withdraw", description="Withdraw coins from your bank.")
    @app_commands.describe(amount="Amount to withdraw (or 'all')")
    async def withdraw(self, interaction: discord.Interaction, amount: str):
        cfg = await self._get_cfg(interaction.guild_id)
        if not cfg["economy_enabled"]:
            return await interaction.response.send_message(embed=error("Economy Disabled"), ephemeral=True)

        row = await self._ensure(interaction.guild_id, interaction.user.id)
        amt = row["bank"] if amount.lower() == "all" else self._parse_amount(amount)

        if amt is None or amt <= 0:
            return await interaction.response.send_message(embed=error("Invalid Amount"), ephemeral=True)
        if amt > row["bank"]:
            return await interaction.response.send_message(
                embed=error("Insufficient Funds", f"You only have `{row['bank']:,}` in your bank."), ephemeral=True
            )

        await db.get_pool().execute(
            "UPDATE economy SET balance=balance+$3, bank=bank-$3 WHERE guild_id=$1 AND user_id=$2",
            interaction.guild_id, interaction.user.id, amt,
        )
        await interaction.response.send_message(
            embed=success("Withdrawn", f"Withdrawn **{amt:,}** {cfg['currency_emoji']} to your wallet.")
        )

    # ── /pay ──────────────────────────────────────────────────────────────────
    @app_commands.command(name="pay", description="Pay another member coins.")
    @app_commands.describe(member="Member to pay", amount="Amount to pay")
    async def pay(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        cfg = await self._get_cfg(interaction.guild_id)
        if not cfg["economy_enabled"]:
            return await interaction.response.send_message(embed=error("Economy Disabled"), ephemeral=True)
        if member == interaction.user or member.bot:
            return await interaction.response.send_message(embed=error("Invalid Target"), ephemeral=True)
        if amount <= 0:
            return await interaction.response.send_message(embed=error("Invalid Amount"), ephemeral=True)

        row = await self._ensure(interaction.guild_id, interaction.user.id)
        if amount > row["balance"]:
            return await interaction.response.send_message(
                embed=error("Insufficient Funds", f"You only have `{row['balance']:,}` in your wallet."), ephemeral=True
            )

        await db.add_balance(interaction.guild_id, interaction.user.id, -amount)
        await db.add_balance(interaction.guild_id, member.id, amount)
        await interaction.response.send_message(
            embed=success("Payment Sent", f"You paid {member.mention} **{amount:,}** {cfg['currency_emoji']}.")
        )

    # ── /shop ─────────────────────────────────────────────────────────────────
    @app_commands.command(name="shop", description="Browse the server shop.")
    async def shop(self, interaction: discord.Interaction):
        cfg = await self._get_cfg(interaction.guild_id)
        if not cfg["economy_enabled"]:
            return await interaction.response.send_message(embed=error("Economy Disabled"), ephemeral=True)

        items = await db.get_shop(interaction.guild_id)
        if not items:
            return await interaction.response.send_message(
                embed=info("Empty Shop", "No items in the shop yet. Admins can add items with `/additem`."), ephemeral=True
            )

        pages  = []
        chunks = [items[i:i+5] for i in range(0, len(items), 5)]
        for chunk in chunks:
            embed = discord.Embed(title=f"{cfg['currency_emoji']} Server Shop", color=0xFFD700)
            for item in chunk:
                stock = f"Stock: {item['stock']}" if item["stock"] is not None else "Unlimited"
                role  = f" • Gives <@&{item['role_id']}>" if item["role_id"] else ""
                embed.add_field(
                    name=f"`#{item['id']}` {item['name']} — {item['price']:,} {cfg['currency_name']}",
                    value=f"{item['description'] or 'No description'}\n{stock}{role}",
                    inline=False,
                )
            pages.append(embed)

        if len(pages) == 1:
            await interaction.response.send_message(embed=pages[0])
        else:
            await interaction.response.send_message(embed=pages[0], view=Paginator(pages, interaction.user.id))

    # ── /buy ──────────────────────────────────────────────────────────────────
    @app_commands.command(name="buy", description="Buy an item from the shop.")
    @app_commands.describe(item_id="The item ID from /shop")
    async def buy(self, interaction: discord.Interaction, item_id: int):
        cfg  = await self._get_cfg(interaction.guild_id)
        if not cfg["economy_enabled"]:
            return await interaction.response.send_message(embed=error("Economy Disabled"), ephemeral=True)

        item = await db.get_shop_item(item_id)
        if not item or item["guild_id"] != interaction.guild_id:
            return await interaction.response.send_message(embed=error("Item Not Found"), ephemeral=True)

        if item["stock"] is not None and item["stock"] <= 0:
            return await interaction.response.send_message(embed=error("Out of Stock"), ephemeral=True)

        row = await self._ensure(interaction.guild_id, interaction.user.id)
        if row["balance"] < item["price"]:
            return await interaction.response.send_message(
                embed=error("Insufficient Funds", f"You need **{item['price']:,}** but only have **{row['balance']:,}**."),
                ephemeral=True,
            )

        # Deduct balance
        await db.add_balance(interaction.guild_id, interaction.user.id, -item["price"])

        # Reduce stock
        if item["stock"] is not None:
            await db.get_pool().execute("UPDATE shop_items SET stock=stock-1 WHERE id=$1", item_id)

        # Add to inventory
        await db.get_pool().execute(
            "INSERT INTO inventory (guild_id, user_id, item_id, quantity) VALUES ($1,$2,$3,1) ON CONFLICT (guild_id, user_id, item_id) DO UPDATE SET quantity=inventory.quantity+1",
            interaction.guild_id, interaction.user.id, item_id,
        )

        # Give role if configured
        if item["role_id"]:
            role = interaction.guild.get_role(item["role_id"])
            if role:
                try:
                    await interaction.user.add_roles(role, reason=f"Purchased {item['name']} from shop")
                except discord.Forbidden:
                    pass

        await interaction.response.send_message(
            embed=success("Purchase Complete", f"You bought **{item['name']}** for **{item['price']:,}** {cfg['currency_emoji']}!")
        )

    # ── /additem ──────────────────────────────────────────────────────────────
    @app_commands.command(name="additem", description="Add an item to the shop.")
    @app_commands.describe(name="Item name", price="Price in coins", description="Item description", role="Role to give on purchase", stock="Stock limit (leave empty for unlimited)")
    @is_admin()
    async def additem(
        self,
        interaction: discord.Interaction,
        name: str,
        price: app_commands.Range[int, 1, 10000000],
        description: str = "No description",
        role: discord.Role | None = None,
        stock: int | None = None,
    ):
        item_id = await db.add_shop_item(
            interaction.guild_id, name, description, price,
            role_id=role.id if role else None, stock=stock,
        )
        await interaction.response.send_message(
            embed=success("Item Added", f"**{name}** added to the shop for **{price:,}** coins. (ID: `{item_id}`)"),
            ephemeral=True,
        )

    # ── /removeitem ───────────────────────────────────────────────────────────
    @app_commands.command(name="removeitem", description="Remove an item from the shop.")
    @app_commands.describe(item_id="The item ID to remove")
    @is_admin()
    async def removeitem(self, interaction: discord.Interaction, item_id: int):
        item = await db.get_shop_item(item_id)
        if not item or item["guild_id"] != interaction.guild_id:
            return await interaction.response.send_message(embed=error("Item Not Found"), ephemeral=True)

        await db.remove_shop_item(item_id)
        await interaction.response.send_message(
            embed=success("Item Removed", f"**{item['name']}** removed from the shop."), ephemeral=True
        )

    # ── /inventory ────────────────────────────────────────────────────────────
    @app_commands.command(name="inventory", description="View your inventory.")
    async def inventory(self, interaction: discord.Interaction):
        cfg  = await self._get_cfg(interaction.guild_id)
        rows = await db.get_pool().fetch(
            """SELECT i.quantity, s.name, s.description FROM inventory i
               JOIN shop_items s ON i.item_id = s.id
               WHERE i.guild_id=$1 AND i.user_id=$2""",
            interaction.guild_id, interaction.user.id,
        )
        if not rows:
            return await interaction.response.send_message(
                embed=info("Empty Inventory", "You haven't bought anything yet."), ephemeral=True
            )

        embed = discord.Embed(title=f"🎒 {interaction.user.display_name}'s Inventory", color=0xFFD700)
        for row in rows:
            embed.add_field(name=f"{row['name']} ×{row['quantity']}", value=row["description"] or "—", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /richlist ─────────────────────────────────────────────────────────────
    @app_commands.command(name="richlist", description="Show the richest members.")
    async def richlist(self, interaction: discord.Interaction):
        cfg  = await self._get_cfg(interaction.guild_id)
        if not cfg["economy_enabled"]:
            return await interaction.response.send_message(embed=error("Economy Disabled"), ephemeral=True)

        rows = await db.get_economy_leaderboard(interaction.guild_id, limit=30)
        if not rows:
            return await interaction.response.send_message(embed=info("Empty", "Nobody has any coins yet."), ephemeral=True)

        pages  = []
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        chunks = [rows[i:i+10] for i in range(0, len(rows), 10)]
        for chunk in chunks:
            embed = discord.Embed(title=f"{cfg['currency_emoji']} Rich List", color=0xFFD700)
            lines = []
            for i, row in enumerate(chunk, start=chunks.index(chunk) * 10 + 1):
                icon  = medals.get(i, f"`#{i}`")
                total = row["balance"] + row["bank"]
                lines.append(f"{icon} <@{row['user_id']}> — **{total:,}** {cfg['currency_name']}")
            embed.description = "\n".join(lines)
            pages.append(embed)

        if len(pages) == 1:
            await interaction.response.send_message(embed=pages[0])
        else:
            await interaction.response.send_message(embed=pages[0], view=Paginator(pages, interaction.user.id))

    # ── /givemoney ────────────────────────────────────────────────────────────
    @app_commands.command(name="givemoney", description="Give a member coins (admin only).")
    @app_commands.describe(member="Member to give coins to", amount="Amount to give")
    @is_admin()
    async def givemoney(self, interaction: discord.Interaction, member: discord.Member, amount: app_commands.Range[int, 1, 10000000]):
        await self._ensure(interaction.guild_id, member.id)
        await db.add_balance(interaction.guild_id, member.id, amount)
        cfg = await self._get_cfg(interaction.guild_id)
        await interaction.response.send_message(
            embed=success("Coins Given", f"Gave {member.mention} **{amount:,}** {cfg['currency_emoji']}."), ephemeral=True
        )

    # ── /takemoney ────────────────────────────────────────────────────────────
    @app_commands.command(name="takemoney", description="Take coins from a member (admin only).")
    @app_commands.describe(member="Member to take coins from", amount="Amount to take")
    @is_admin()
    async def takemoney(self, interaction: discord.Interaction, member: discord.Member, amount: app_commands.Range[int, 1, 10000000]):
        await self._ensure(interaction.guild_id, member.id)
        await db.add_balance(interaction.guild_id, member.id, -amount)
        cfg = await self._get_cfg(interaction.guild_id)
        await interaction.response.send_message(
            embed=success("Coins Taken", f"Took **{amount:,}** {cfg['currency_emoji']} from {member.mention}."), ephemeral=True
        )

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _parse_amount(self, value: str) -> int | None:
        try:
            return int(value.replace(",", ""))
        except ValueError:
            return None

    async def cog_app_command_error(self, interaction: discord.Interaction, err: app_commands.AppCommandError):
        msg = "You don't have permission." if isinstance(err, app_commands.MissingPermissions) else f"`{err}`"
        if interaction.response.is_done():
            await interaction.followup.send(embed=error("Error", msg), ephemeral=True)
        else:
            await interaction.response.send_message(embed=error("Error", msg), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Economy(bot))
