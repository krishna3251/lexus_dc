import discord
from discord.ext import commands
import os
import aiohttp
import datetime
import sqlite3
import random
from dotenv import load_dotenv

load_dotenv()

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.perspective_api_key = os.getenv("PERSPECTIVE_API_KEY")
        self.moderation_enabled = {}
        self.toxicity_threshold = 0.6

        # 👉 ROLES TO IGNORE (ADD YOUR ROLE IDS HERE)
        self.ignored_role_ids = {
            123456789012345678,  # Moderator role ID
            987654321098765432,
            1405824212270321707,# Admin role ID
        }

        self.enabled_attributes = [
            "TOXICITY",
            "SEVERE_TOXICITY",
            "INSULT",
            "THREAT"
        ]

        self.setup_database()

    # -------------------- UTILS --------------------

    def has_ignored_role(self, member: discord.Member):
        return any(role.id in self.ignored_role_ids for role in member.roles)

    def get_db_connection(self):
        db_path = os.path.join(os.path.dirname(__file__), "moderation.db")
        return sqlite3.connect(db_path)

    def is_moderation_enabled(self, guild_id):
        if str(guild_id) in self.moderation_enabled:
            return self.moderation_enabled[str(guild_id)]

        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT moderation_enabled FROM guild_settings WHERE guild_id = ?",
            (str(guild_id),)
        )
        result = cursor.fetchone()
        conn.close()

        if result:
            self.moderation_enabled[str(guild_id)] = bool(result[0])
            return bool(result[0])

        return True

    # -------------------- DATABASE --------------------

    def setup_database(self):
        conn = self.get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS karma (
            guild_id TEXT,
            user_id TEXT,
            username TEXT,
            display_name TEXT,
            karma_points INTEGER DEFAULT 0,
            positive_messages INTEGER DEFAULT 0,
            toxic_messages INTEGER DEFAULT 0,
            warnings INTEGER DEFAULT 0,
            last_updated TEXT,
            PRIMARY KEY (guild_id, user_id)
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS warnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id TEXT,
            user_id TEXT,
            moderator_id TEXT,
            reason TEXT,
            toxicity_score REAL,
            timestamp TEXT,
            action_taken TEXT
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id TEXT PRIMARY KEY,
            moderation_enabled INTEGER DEFAULT 1,
            toxicity_threshold REAL DEFAULT 0.6
        )
        """)

        conn.commit()
        conn.close()

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
            "requestedAttributes": {a: {} for a in self.enabled_attributes}
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

    # -------------------- KARMA --------------------

    async def update_karma(self, message, is_toxic=False, toxicity_score=0.0):
        if not message.guild:
            return 0

        conn = self.get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
        SELECT karma_points, positive_messages, toxic_messages, warnings
        FROM karma WHERE guild_id = ? AND user_id = ?
        """, (str(message.guild.id), str(message.author.id)))

        row = cursor.fetchone()
        karma, pos, tox, warns = row if row else (0, 0, 0, 0)

        if is_toxic:
            penalty = min(10, max(3, int(toxicity_score * 10)))
            karma -= penalty
            tox += 1
            warns += 1
        else:
            karma += random.randint(1, 3)
            pos += 1

        cursor.execute("""
        INSERT OR REPLACE INTO karma
        (guild_id, user_id, username, display_name,
         karma_points, positive_messages, toxic_messages,
         warnings, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(message.guild.id),
            str(message.author.id),
            message.author.name,
            message.author.display_name,
            karma, pos, tox, warns,
            datetime.datetime.now().isoformat()
        ))

        conn.commit()
        conn.close()
        return warns

    # -------------------- PUNISHMENTS --------------------

    async def apply_punishment(self, message, warnings, score):
        user = message.author

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
        else:
            action = "WARNING"

        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO warnings
        (guild_id, user_id, moderator_id, reason,
         toxicity_score, timestamp, action_taken)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            str(message.guild.id),
            str(user.id),
            str(self.bot.user.id),
            "Toxic message",
            score,
            datetime.datetime.now().isoformat(),
            action
        ))
        conn.commit()
        conn.close()

    # -------------------- LISTENER --------------------

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        if not message.guild:
            return

        # 🚫 IGNORE ADMINS & MOD ROLES
        if (
            message.author.guild_permissions.administrator
            or self.has_ignored_role(message.author)
        ):
            # optional karma reward
            await self.update_karma(message, is_toxic=False)
            return

        if not self.is_moderation_enabled(message.guild.id):
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
