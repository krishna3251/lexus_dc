"""
Economy Cog — Virtual currency system with daily rewards, balance,
pay, shop, and work commands. All data in MongoDB (economy collection).
"""

import discord
from discord.ext import commands
from discord import app_commands
import random
import time
import logging
import mongo_helper

logger = logging.getLogger(__name__)

DAILY_AMOUNT = 200
WORK_MIN = 50
WORK_MAX = 300
WORK_COOLDOWN = 3600  # 1 hour

DEFAULT_SHOP = [
    {"name": "Custom Role Color", "price": 5000, "description": "Change your role color"},
    {"name": "VIP Badge", "price": 10000, "description": "Exclusive VIP nickname badge"},
    {"name": "Double XP (1h)", "price": 3000, "description": "Double XP gain for 1 hour"},
]


class EconomyCog(commands.Cog, name="Economy"):
    """Virtual currency system."""

    def __init__(self, bot):
        self.bot = bot

    async def _get_wallet(self, guild_id: int, user_id: int) -> dict:
        return await mongo_helper.get_economy(guild_id, user_id)

    async def _update_balance(self, guild_id: int, user_id: int, amount: int, username: str = None):
        data = {"username": username} if username else {}
        await mongo_helper.inc_economy(guild_id, user_id, "balance", amount)
        if username:
            await mongo_helper.update_economy(guild_id, user_id, data)

    # ── /balance ───────────────────────────────────────────────────

    @app_commands.command(name="balance", description="Check your coin balance")
    @app_commands.describe(user="User to check (defaults to yourself)")
    async def balance(self, interaction: discord.Interaction, user: discord.Member = None):
        user = user or interaction.user
        wallet = await self._get_wallet(interaction.guild_id, user.id)
        bal = wallet.get("balance", 0)

        embed = discord.Embed(
            title=f"💰 {user.display_name}'s Wallet",
            color=discord.Color.gold(),
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="Coins", value=f"🪙 {bal:,}")
        await interaction.response.send_message(embed=embed)

    # ── /daily ─────────────────────────────────────────────────────

    @app_commands.command(name="daily", description="Claim your daily coins")
    async def daily(self, interaction: discord.Interaction):
        wallet = await self._get_wallet(interaction.guild_id, interaction.user.id)
        last_daily = wallet.get("last_daily", 0)

        now = time.time()
        if now - last_daily < 86400:
            remaining = int(last_daily + 86400 - now)
            h, m = divmod(remaining // 60, 60)
            await interaction.response.send_message(
                f"❌ You already claimed today. Next in **{h}h {m}m**.", ephemeral=True
            )
            return

        await mongo_helper.inc_economy(interaction.guild_id, interaction.user.id, "balance", DAILY_AMOUNT)
        await mongo_helper.update_economy(interaction.guild_id, interaction.user.id, {
            "last_daily": now,
            "username": str(interaction.user),
        })

        new_bal = wallet.get("balance", 0) + DAILY_AMOUNT
        await interaction.response.send_message(
            f"✅ You claimed **🪙 {DAILY_AMOUNT:,}** daily coins! Balance: **{new_bal:,}**"
        )

    # ── /work ──────────────────────────────────────────────────────

    @app_commands.command(name="work", description="Work to earn coins")
    async def work(self, interaction: discord.Interaction):
        wallet = await self._get_wallet(interaction.guild_id, interaction.user.id)
        last_work = wallet.get("last_work", 0)

        now = time.time()
        if now - last_work < WORK_COOLDOWN:
            remaining = int(last_work + WORK_COOLDOWN - now)
            m, s = divmod(remaining, 60)
            await interaction.response.send_message(
                f"❌ You're tired! Rest for **{m}m {s}s**.", ephemeral=True
            )
            return

        earned = random.randint(WORK_MIN, WORK_MAX)
        jobs = [
            f"You delivered packages and earned **🪙 {earned:,}**!",
            f"You wrote some code and earned **🪙 {earned:,}**!",
            f"You tutored students and earned **🪙 {earned:,}**!",
            f"You drove a cab and earned **🪙 {earned:,}**!",
            f"You fixed a server and earned **🪙 {earned:,}**!",
        ]

        await mongo_helper.inc_economy(interaction.guild_id, interaction.user.id, "balance", earned)
        await mongo_helper.update_economy(interaction.guild_id, interaction.user.id, {
            "last_work": now,
            "username": str(interaction.user),
        })

        await interaction.response.send_message(random.choice(jobs))

    # ── /pay ───────────────────────────────────────────────────────

    @app_commands.command(name="pay", description="Send coins to another user")
    @app_commands.describe(user="Who to pay", amount="Amount of coins")
    async def pay(self, interaction: discord.Interaction, user: discord.Member, amount: int):
        if amount <= 0:
            await interaction.response.send_message("❌ Amount must be positive.", ephemeral=True)
            return
        if user.id == interaction.user.id:
            await interaction.response.send_message("❌ You can't pay yourself.", ephemeral=True)
            return

        wallet = await self._get_wallet(interaction.guild_id, interaction.user.id)
        if wallet.get("balance", 0) < amount:
            await interaction.response.send_message("❌ Insufficient funds.", ephemeral=True)
            return

        await mongo_helper.inc_economy(interaction.guild_id, interaction.user.id, "balance", -amount)
        await mongo_helper.inc_economy(interaction.guild_id, user.id, "balance", amount)
        await interaction.response.send_message(
            f"✅ {interaction.user.mention} paid **🪙 {amount:,}** to {user.mention}"
        )

    # ── /shop ──────────────────────────────────────────────────────

    @app_commands.command(name="shop", description="View the server shop")
    async def shop(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🛒 Server Shop",
            color=discord.Color.green(),
        )
        for item in DEFAULT_SHOP:
            embed.add_field(
                name=f"{item['name']} — 🪙 {item['price']:,}",
                value=item["description"],
                inline=False,
            )
        embed.set_footer(text="Use /buy <item name> to purchase")
        await interaction.response.send_message(embed=embed)

    # ── /buy ───────────────────────────────────────────────────────

    @app_commands.command(name="buy", description="Buy an item from the shop")
    @app_commands.describe(item="Item name")
    async def buy(self, interaction: discord.Interaction, item: str):
        shop_item = None
        for s in DEFAULT_SHOP:
            if s["name"].lower() == item.lower():
                shop_item = s
                break

        if not shop_item:
            await interaction.response.send_message("❌ Item not found. Check `/shop`.", ephemeral=True)
            return

        wallet = await self._get_wallet(interaction.guild_id, interaction.user.id)
        if wallet.get("balance", 0) < shop_item["price"]:
            await interaction.response.send_message("❌ Insufficient funds.", ephemeral=True)
            return

        await mongo_helper.inc_economy(
            interaction.guild_id, interaction.user.id, "balance", -shop_item["price"]
        )

        # Track purchases
        col = mongo_helper.get_collection("economy")
        if col:
            await col.update_one(
                {"guild_id": interaction.guild_id, "user_id": interaction.user.id},
                {"$push": {"purchases": {"item": shop_item["name"], "time": time.time()}}},
            )

        await interaction.response.send_message(
            f"✅ You bought **{shop_item['name']}** for **🪙 {shop_item['price']:,}**!"
        )

    # ── /richest ───────────────────────────────────────────────────

    @app_commands.command(name="richest", description="See the richest members")
    async def richest(self, interaction: discord.Interaction):
        col = mongo_helper.get_collection("economy")
        if not col:
            await interaction.response.send_message("❌ Database unavailable.", ephemeral=True)
            return

        cursor = col.find({"guild_id": interaction.guild_id}).sort("balance", -1).limit(10)
        rows = await cursor.to_list(length=10)

        if not rows:
            await interaction.response.send_message("No economy data yet.", ephemeral=True)
            return

        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, row in enumerate(rows):
            medal = medals[i] if i < 3 else f"**{i+1}.**"
            member = interaction.guild.get_member(row["user_id"])
            name = member.display_name if member else row.get("username", "Unknown")
            lines.append(f"{medal} **{name}** — 🪙 {row.get('balance', 0):,}")

        embed = discord.Embed(
            title=f"💎 {interaction.guild.name} Richest",
            description="\n".join(lines),
            color=discord.Color.gold(),
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(EconomyCog(bot))
    logger.info("✅ Economy cog loaded")
