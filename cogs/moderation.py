import discord
from discord.ext import commands
import os
import aiohttp
import datetime
import sqlite3
import random
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.perspective_api_key = os.getenv("PERSPECTIVE_API_KEY")
        # Dictionary to store per-guild moderation state
        self.moderation_enabled = {}
        self.toxicity_threshold = 0.7
        
        # Set up database for karma system
        self.setup_database()
        
        # Perspective API attributes we want to check
        self.enabled_attributes = ["TOXICITY"]

    def setup_database(self):
        """Set up SQLite database for karma tracking"""
        db_path = os.path.join(os.path.dirname(__file__), 'karma.db')
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Create karma table if it doesn't exist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS karma (
                guild_id TEXT,
                user_id TEXT,
                username TEXT,
                karma_points INTEGER DEFAULT 0,
                positive_messages INTEGER DEFAULT 0,
                toxic_messages INTEGER DEFAULT 0,
                last_updated TIMESTAMP,
                PRIMARY KEY (guild_id, user_id)
            )
        ''')
        
        # Create settings table for per-guild settings
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id TEXT PRIMARY KEY,
                moderation_enabled BOOLEAN DEFAULT 1,
                toxicity_threshold REAL DEFAULT 0.7
            )
        ''')
        
        conn.commit()
        conn.close()

    def get_db_connection(self):
        """Get a connection to the SQLite database"""
        db_path = os.path.join(os.path.dirname(__file__), 'karma.db')
        return sqlite3.connect(db_path)

    async def analyze_text_toxicity(self, text):
        """Analyze text using Google's Perspective API"""
        if not self.perspective_api_key:
            return None, None  # API key not configured

        url = f"https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze?key={self.perspective_api_key}"
        
        # Build requested attributes dictionary
        requested_attributes = {attr: {} for attr in self.enabled_attributes}
        
        payload = {
            "comment": {"text": text},
            "languages": ["en"],
            "requestedAttributes": requested_attributes
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        results = {}
                        
                        # Extract scores for each attribute
                        for attr in self.enabled_attributes:
                            if attr in data.get("attributeScores", {}):
                                results[attr] = data["attributeScores"][attr]["summaryScore"]["value"]
                        
                        # Return highest score among all attributes, along with all scores
                        if results:
                            highest_score = max(results.values())
                            return highest_score, results
                        return None, None
                    else:
                        print(f"Perspective API error: {response.status}")
                        return None, None
        except Exception as e:
            print(f"Error analyzing toxicity: {e}")
            return None, None

    def is_moderation_enabled(self, guild_id):
        """Check if moderation is enabled for a guild"""
        # First check in-memory cache
        if str(guild_id) in self.moderation_enabled:
            return self.moderation_enabled[str(guild_id)]
            
        # If not in cache, check database
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT moderation_enabled FROM guild_settings WHERE guild_id = ?", (str(guild_id),))
        result = cursor.fetchone()
        conn.close()
        
        # If found in database, cache it and return
        if result:
            self.moderation_enabled[str(guild_id)] = bool(result[0])
            return bool(result[0])
            
        # Default to enabled if not set
        return True

    async def update_karma(self, message, is_toxic=False, toxicity_score=0.0):
        """Update karma points for a user based on their message"""
        if not message.guild:
            return  # Only track karma in guilds
            
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Get current user stats
        cursor.execute(
            "SELECT karma_points, positive_messages, toxic_messages FROM karma WHERE guild_id = ? AND user_id = ?", 
            (str(message.guild.id), str(message.author.id))
        )
        result = cursor.fetchone()
        
        if result:
            karma_points, positive_messages, toxic_messages = result
        else:
            karma_points, positive_messages, toxic_messages = 0, 0, 0
            
        # Update karma
        if is_toxic:
            # Penalize toxic messages (-2 to -5 points based on toxicity)
            penalty = min(5, max(2, int(toxicity_score * 5)))
            karma_points -= penalty
            toxic_messages += 1
        else:
            # Reward positive messages (random +1 to +3)
            reward = random.randint(1, 3)
            karma_points += reward
            positive_messages += 1
            
        # Insert or update user record
        cursor.execute(
            """
            INSERT OR REPLACE INTO karma 
            (guild_id, user_id, username, karma_points, positive_messages, toxic_messages, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(message.guild.id),
                str(message.author.id),
                message.author.name,
                karma_points,
                positive_messages,
                toxic_messages,
                datetime.datetime.now().isoformat()
            )
        )
        
        conn.commit()
        conn.close()

    @commands.group(name="mod", help="Moderation controls", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def mod(self, ctx):
        """Base command for moderation controls"""
        await ctx.send("Please use `lx mod on`, `lx mod off`, or `lx mod status`")

    @mod.command(name="on", help="Enable moderation for this server")
    @commands.has_permissions(manage_guild=True)
    async def mod_on(self, ctx):
        """Enable moderation for this guild"""
        guild_id = str(ctx.guild.id)
        self.moderation_enabled[guild_id] = True
        
        # Update database
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO guild_settings (guild_id, moderation_enabled) VALUES (?, 1)",
            (guild_id,)
        )
        conn.commit()
        conn.close()
        
        embed = discord.Embed(
            title="✅ Moderation Enabled",
            description="Toxic message detection is now active.",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @mod.command(name="off", help="Disable moderation for this server")
    @commands.has_permissions(manage_guild=True)
    async def mod_off(self, ctx):
        """Disable moderation for this guild"""
        guild_id = str(ctx.guild.id)
        self.moderation_enabled[guild_id] = False
        
        # Update database
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO guild_settings (guild_id, moderation_enabled) VALUES (?, 0)",
            (guild_id,)
        )
        conn.commit()
        conn.close()
        
        embed = discord.Embed(
            title="🚫 Moderation Disabled",
            description="Toxic message detection is now inactive.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)

    @mod.command(name="status", help="Check moderation status for this server")
    async def mod_status(self, ctx):
        """Check moderation status for this guild"""
        guild_id = str(ctx.guild.id)
        status = self.is_moderation_enabled(guild_id)
        
        embed = discord.Embed(
            title="🔍 Moderation Status",
            color=discord.Color.blue()
        )
        
        status_text = "✅ Enabled" if status else "❌ Disabled"
        embed.add_field(name="Current Status", value=status_text, inline=False)
        embed.add_field(name="Toxicity Threshold", value=f"{self.toxicity_threshold}", inline=False)
        
        await ctx.send(embed=embed)

    @commands.group(name="karma", help="Karma system commands", invoke_without_command=True)
    async def karma(self, ctx):
        """Base command for karma system"""
        await ctx.send("Please use `lx karma check` or `lx karma leaderboard`")

    @karma.command(name="check", help="Check karma for a user")
    async def karma_check(self, ctx, member: discord.Member = None):
        """Check karma for a user"""
        target = member or ctx.author
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT karma_points, positive_messages, toxic_messages FROM karma WHERE guild_id = ? AND user_id = ?",
            (str(ctx.guild.id), str(target.id))
        )
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            karma_points, positive_messages, toxic_messages = 0, 0, 0
        else:
            karma_points, positive_messages, toxic_messages = result
            
        # Standard embed
        embed = discord.Embed(
            title="Karma Profile",
            description=f"Karma data for {target.mention}",
            color=discord.Color.blue()
        )
        
        # Calculate purity percentage
        total_messages = positive_messages + toxic_messages
        purity_percent = 100 if total_messages == 0 else round((positive_messages / total_messages) * 100)
        
        embed.add_field(name="Karma Points", value=f"{karma_points}", inline=False)
        embed.add_field(name="Positive Messages", value=f"{positive_messages}", inline=True)
        embed.add_field(name="Toxic Messages", value=f"{toxic_messages}", inline=True)
        embed.add_field(name="Purity", value=f"{purity_percent}%", inline=False)
        
        embed.set_thumbnail(url=target.avatar.url if target.avatar else None)
        
        await ctx.send(embed=embed)

    @karma.command(name="leaderboard", aliases=["lb"], help="Show karma leaderboard")
    async def karma_leaderboard(self, ctx, limit: int = 10):
        """Show karma leaderboard"""
        if limit < 1:
            await ctx.send("⚠️ Please specify a positive number")
            return
            
        if limit > 25:
            limit = 25  # Cap at 25 to prevent abuse
            
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT user_id, username, karma_points, positive_messages, toxic_messages 
            FROM karma 
            WHERE guild_id = ? 
            ORDER BY karma_points DESC
            LIMIT ?
            """,
            (str(ctx.guild.id), limit)
        )
        results = cursor.fetchall()
        conn.close()
        
        if not results:
            await ctx.send("⚠️ No karma data found for this server yet!")
            return
            
        # Create embed
        embed = discord.Embed(
            title="🌐 Karma Leaderboard",
            description="Top users ranked by karma points",
            color=discord.Color.blue()
        )
        
        # Add each user's data
        leaderboard_text = ""
        for i, (user_id, username, karma, positive, toxic) in enumerate(results, 1):
            # Calculate purity percentage
            total = positive + toxic
            purity = 100 if total == 0 else round((positive / total) * 100)
            
            # Format ranking
            if i == 1:
                rank = "🥇"
            elif i == 2:
                rank = "🥈"
            elif i == 3:
                rank = "🥉"
            else:
                rank = f"{i}."
                
            leaderboard_text += f"{rank} **{username}** - {karma} points ({purity}% positive)\n"
                
        embed.add_field(name="Rankings", value=leaderboard_text, inline=False)
        
        # Add footer
        now = datetime.datetime.now()
        embed.set_footer(text=f"Updated: {now.strftime('%Y-%m-%d %H:%M:%S')}")
        
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignore messages from bots
        if message.author.bot:
            return
            
        # Check if message is in a guild and if moderation is enabled
        if not message.guild or not self.is_moderation_enabled(message.guild.id):
            # Just update karma positively if moderation is disabled
            await self.update_karma(message, is_toxic=False)
            return
            
        # Analyze message content for toxicity
        try:
            toxicity_score, all_scores = await self.analyze_text_toxicity(message.content)
            
            # If we couldn't get a score, return
            if toxicity_score is None:
                # Just update karma positively as we can't check
                await self.update_karma(message, is_toxic=False)
                return
                
            # If content exceeds threshold, handle as toxic
            if toxicity_score >= self.toxicity_threshold:
                # Delete toxic message
                try:
                    await message.delete()
                    
                    # Send warning
                    warning = await message.channel.send(
                        f"⚠️ {message.author.mention}, your message was removed for containing toxic content. "
                        f"(Score: {toxicity_score:.2f})"
                    )
                    
                    # Delete warning after a few seconds
                    await warning.delete(delay=5)
                    
                    # Update karma negatively
                    await self.update_karma(message, is_toxic=True, toxicity_score=toxicity_score)
                except Exception as e:
                    print(f"Error handling toxic message: {e}")
            else:
                # Update karma positively
                await self.update_karma(message, is_toxic=False)
        except Exception as e:
            print(f"Error in message processing: {e}")
            # Update karma positively as we couldn't check properly
            await self.update_karma(message, is_toxic=False)

async def setup(bot):
    await bot.add_cog(Moderation(bot))
