import discord
from discord.ext import commands
import os
import aiohttp
import datetime
import random
import logging
from dotenv import load_dotenv

# Import centralized MongoDB helper
import mongo_helper

load_dotenv()
logger = logging.getLogger(__name__)


class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.perspective_api_key = os.getenv("PERSPECTIVE_API_KEY")
        self.moderation_enabled: dict = {}  # in-memory cache
        self.toxicity_threshold = 0.6

        # Roles to ignore (add your role IDs here)
        self.ignored_role_ids = {
            123456789012345678,
            987654321098765432,
            1405824212270321707,
            1437127567378481243,
        }

        self.enabled_attributes = [
            "TOXICITY",
            "SEVERE_TOXICITY",
            "INSULT",
            "THREAT",
        ]

    # -------------------- UTILS --------------------

    def has_ignored_role(self, member: discord.Member):
        return any(role.id in self.ignored_role_ids for role in member.roles)

    async def is_moderation_enabled(self, guild_id: int) -> bool:
        """Check if moderation is enabled for the guild (async, uses MongoDB)."""
        key = str(guild_id)
        if key in self.moderation_enabled:
            return self.moderation_enabled[key]

        col = mongo_helper.get_collection("perspective_guild_settings")
        if col is None:
            return True  # default to enabled when DB unavailable

        doc = await col.find_one({"guild_id": guild_id})
        if doc:
            enabled = doc.get("moderation_enabled", True)
            self.moderation_enabled[key] = enabled
            return enabled

        return True

    # -------------------- TOXICITY --------------------

    async def analyze_text_toxicity(self, text):
        if not self.perspective_api_key:
            return None, None

        url = (
            "https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze"
            f"?key={self.perspective_api_key}"
        )

        payload = {
            "comment": {"text": text},
            "languages": ["en"],
            "requestedAttributes": {a: {} for a in self.enabled_attributes},
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        return None, None

                    data = await resp.json()
                    scores = {
                        attr: data["attributeScores"][attr]["summaryScore"]["value"]
                        for attr in data.get("attributeScores", {})
                    }

                    return max(scores.values()), scores

        except Exception:
            return None, None

    # -------------------- KARMA (MongoDB) --------------------

    async def update_karma(self, message, is_toxic=False, toxicity_score=0.0):
        """Update karma record in MongoDB."""
        if not message.guild:
            return 0

        guild_id = message.guild.id
        user_id = message.author.id

        col = mongo_helper.get_collection("perspective_karma")
        if col is None:
            logger.warning("MongoDB not connected – skipping karma update")
            return 0

        doc = await col.find_one({"guild_id": guild_id, "user_id": user_id})
        karma = doc.get("karma_points", 0) if doc else 0
        pos = doc.get("positive_messages", 0) if doc else 0
        tox = doc.get("toxic_messages", 0) if doc else 0
        warns = doc.get("warnings", 0) if doc else 0

        if is_toxic:
            penalty = min(10, max(3, int(toxicity_score * 10)))
            karma -= penalty
            tox += 1
            warns += 1
        else:
            karma += random.randint(1, 3)
            pos += 1

        await col.update_one(
            {"guild_id": guild_id, "user_id": user_id},
            {
                "$set": {
                    "username": message.author.name,
                    "display_name": message.author.display_name,
                    "karma_points": karma,
                    "positive_messages": pos,
                    "toxic_messages": tox,
                    "warnings": warns,
                    "last_updated": datetime.datetime.now().isoformat(),
                }
            },
            upsert=True,
        )

        return warns

    # -------------------- PUNISHMENTS --------------------

    async def apply_punishment(self, message, warnings, score):
        user = message.author
        guild = message.guild

        # Hierarchy check
        if user.top_role >= guild.me.top_role or user.id == guild.owner_id:
            logger.warning(f"Cannot punish {user} — role hierarchy prevents action.")
            return

        action = "WARNING"
        try:
            if warnings >= 30:
                await user.ban(reason="30 warnings reached")
                action = "BANNED"
            elif warnings >= 20:
                await user.kick(reason="20 warnings reached")
                action = "KICKED"
            elif warnings >= 10:
                await user.timeout(datetime.timedelta(minutes=10))
                action = "10m TIMEOUT"
            elif warnings >= 5:
                await user.timeout(datetime.timedelta(minutes=1))
                action = "1m TIMEOUT"
        except discord.Forbidden:
            logger.warning(f"discord.Forbidden when trying to {action} {user} in {guild.name}")
            return
        except Exception as e:
            logger.error(f"Punishment error for {user}: {e}")
            return

        # Log the warning to MongoDB
        col = mongo_helper.get_collection("perspective_warnings")
        if col is not None:
            await col.insert_one(
                {
                    "guild_id": message.guild.id,
                    "user_id": user.id,
                    "moderator_id": self.bot.user.id,
                    "reason": "Toxic message",
                    "toxicity_score": score,
                    "timestamp": datetime.datetime.now().isoformat(),
                    "action_taken": action,
                }
            )

    # -------------------- LISTENER --------------------

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        # Ignore admins & mod roles
        if (
            message.author.guild_permissions.administrator
            or self.has_ignored_role(message.author)
        ):
            await self.update_karma(message, is_toxic=False)
            return

        if not await self.is_moderation_enabled(message.guild.id):
            await self.update_karma(message, is_toxic=False)
            return

        score, _ = await self.analyze_text_toxicity(message.content)

        if score is None:
            await self.update_karma(message, is_toxic=False)
            return

        if score >= self.toxicity_threshold:
            try:
                await message.delete()
            except discord.Forbidden:
                pass

            warnings = await self.update_karma(
                message, is_toxic=True, toxicity_score=score
            )
            await self.apply_punishment(message, warnings, score)
        else:
            await self.update_karma(message, is_toxic=False)


# -------------------- SETUP --------------------

async def setup(bot):
    await bot.add_cog(Moderation(bot))
