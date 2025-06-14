import discord
from discord.ext import commands
import os
import aiohttp
import datetime
import sqlite3
import random
import asyncio
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.perspective_api_key = os.getenv("PERSPECTIVE_API_KEY")
        # Dictionary to store per-guild moderation state
        self.moderation_enabled = {}
        self.toxicity_threshold = 0.6  # Made stricter
        
        # Set up database for karma and warning system
        self.setup_database()
        
        # Perspective API attributes we want to check
        self.enabled_attributes = ["TOXICITY", "SEVERE_TOXICITY", "INSULT", "THREAT"]

    def setup_database(self):
        """Set up SQLite database for karma and warning tracking"""
        db_path = os.path.join(os.path.dirname(__file__), 'moderation.db')
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Create karma table with enhanced tracking
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS karma (
                guild_id TEXT,
                user_id TEXT,
                username TEXT,
                display_name TEXT,
                karma_points INTEGER DEFAULT 0,
                positive_messages INTEGER DEFAULT 0,
                toxic_messages INTEGER DEFAULT 0,
                warnings INTEGER DEFAULT 0,
                timeouts INTEGER DEFAULT 0,
                kicks INTEGER DEFAULT 0,
                last_updated TIMESTAMP,
                PRIMARY KEY (guild_id, user_id)
            )
        ''')
        
        # Create warnings table for detailed warning tracking
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT,
                user_id TEXT,
                moderator_id TEXT,
                reason TEXT,
                toxicity_score REAL,
                timestamp TIMESTAMP,
                action_taken TEXT
            )
        ''')
        
        # Create settings table for per-guild settings
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id TEXT PRIMARY KEY,
                moderation_enabled BOOLEAN DEFAULT 1,
                toxicity_threshold REAL DEFAULT 0.6,
                warning_thresholds TEXT DEFAULT '{"timeout_1": 5, "timeout_2": 10, "kick": 20, "ban": 30}'
            )
        ''')
        
        conn.commit()
        conn.close()

    def get_db_connection(self):
        """Get a connection to the SQLite database"""
        db_path = os.path.join(os.path.dirname(__file__), 'moderation.db')
        return sqlite3.connect(db_path)

    async def analyze_text_toxicity(self, text):
        """Analyze text using Google's Perspective API with multiple attributes"""
        if not self.perspective_api_key:
            return None, None

        url = f"https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze?key={self.perspective_api_key}"
        
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
                        
                        for attr in self.enabled_attributes:
                            if attr in data.get("attributeScores", {}):
                                results[attr] = data["attributeScores"][attr]["summaryScore"]["value"]
                        
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
        if str(guild_id) in self.moderation_enabled:
            return self.moderation_enabled[str(guild_id)]
            
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT moderation_enabled FROM guild_settings WHERE guild_id = ?", (str(guild_id),))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            self.moderation_enabled[str(guild_id)] = bool(result[0])
            return bool(result[0])
            
        return True

    async def add_warning(self, message, toxicity_score, action_taken="Warning"):
        """Add a warning to the database and return warning count"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Add warning record
        cursor.execute(
            """
            INSERT INTO warnings (guild_id, user_id, moderator_id, reason, toxicity_score, timestamp, action_taken)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(message.guild.id),
                str(message.author.id),
                str(self.bot.user.id),
                "Toxic message detected",
                toxicity_score,
                datetime.datetime.now().isoformat(),
                action_taken
            )
        )
        
        # Update user karma and warning count
        cursor.execute(
            "SELECT warnings FROM karma WHERE guild_id = ? AND user_id = ?",
            (str(message.guild.id), str(message.author.id))
        )
        result = cursor.fetchone()
        warning_count = (result[0] if result else 0) + 1
        
        conn.commit()
        conn.close()
        
        return warning_count

    async def apply_punishment(self, message, warning_count, toxicity_score):
        """Apply appropriate punishment based on warning count"""
        user = message.author
        guild = message.guild
        
        try:
            if warning_count >= 30:
                # Ban user
                await user.ban(reason=f"Exceeded warning limit (30 warnings)")
                action = "🚫 **BANNED**"
                punishment_msg = f"{user.mention} has been **banned** for exceeding 30 warnings!"
                
            elif warning_count >= 20:
                # Kick user
                await user.kick(reason=f"Exceeded warning limit (20 warnings)")
                action = "👢 **KICKED**"
                punishment_msg = f"{user.mention} has been **kicked** for reaching 20 warnings!"
                
            elif warning_count >= 10:
                # 10 minute timeout
                timeout_duration = datetime.timedelta(minutes=10)
                await user.timeout(timeout_duration, reason=f"10 warnings reached")
                action = "⏰ **10-MIN TIMEOUT**"
                punishment_msg = f"{user.mention} has been **timed out for 10 minutes** (10 warnings reached)"
                
            elif warning_count >= 5:
                # 1 minute timeout
                timeout_duration = datetime.timedelta(minutes=1)
                await user.timeout(timeout_duration, reason=f"5 warnings reached")
                action = "⏰ **1-MIN TIMEOUT**"
                punishment_msg = f"{user.mention} has been **timed out for 1 minute** (5 warnings reached)"
                
            else:
                action = "⚠️ **WARNING**"
                punishment_msg = f"⚠️ {user.mention}, warning #{warning_count} for toxic content (Score: {toxicity_score:.2f})"
            
            # Update warning count in karma table
            await self.add_warning(message, toxicity_score, action)
            
            # Send punishment message
            punishment_embed = discord.Embed(
                title="🚨 Moderation Action",
                description=punishment_msg,
                color=discord.Color.red() if warning_count >= 5 else discord.Color.orange()
            )
            punishment_embed.add_field(name="Total Warnings", value=f"{warning_count}", inline=True)
            punishment_embed.add_field(name="Toxicity Score", value=f"{toxicity_score:.2f}", inline=True)
            punishment_embed.set_footer(text=f"User ID: {user.id}")
            
            msg = await message.channel.send(embed=punishment_embed)
            await msg.delete(delay=10)  # Delete after 10 seconds
            
        except discord.Forbidden:
            await message.channel.send(f"⚠️ I don't have permission to punish {user.mention}!")
        except Exception as e:
            print(f"Error applying punishment: {e}")

    async def update_karma(self, message, is_toxic=False, toxicity_score=0.0):
        """Update karma points for a user based on their message"""
        if not message.guild:
            return
            
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Get current user stats
        cursor.execute(
            """SELECT karma_points, positive_messages, toxic_messages, warnings 
               FROM karma WHERE guild_id = ? AND user_id = ?""", 
            (str(message.guild.id), str(message.author.id))
        )
        result = cursor.fetchone()
        
        if result:
            karma_points, positive_messages, toxic_messages, warnings = result
        else:
            karma_points, positive_messages, toxic_messages, warnings = 0, 0, 0, 0
            
        # Update karma
        if is_toxic:
            penalty = min(10, max(3, int(toxicity_score * 10)))  # Stricter penalties
            karma_points -= penalty
            toxic_messages += 1
            warnings += 1
        else:
            reward = random.randint(1, 3)
            karma_points += reward
            positive_messages += 1
            
        # Insert or update user record
        cursor.execute(
            """
            INSERT OR REPLACE INTO karma 
            (guild_id, user_id, username, display_name, karma_points, positive_messages, 
             toxic_messages, warnings, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(message.guild.id),
                str(message.author.id),
                message.author.name,
                message.author.display_name,
                karma_points,
                positive_messages,
                toxic_messages,
                warnings,
                datetime.datetime.now().isoformat()
            )
        )
        
        conn.commit()
        conn.close()
        
        return warnings

    @commands.group(name="mod", help="Moderation controls", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def mod(self, ctx):
        """Base command for moderation controls"""
        embed = discord.Embed(
            title="🛡️ Moderation Commands",
            description="Available moderation commands:",
            color=discord.Color.blue()
        )
        embed.add_field(name="`lx mod on`", value="Enable moderation", inline=False)
        embed.add_field(name="`lx mod off`", value="Disable moderation", inline=False)
        embed.add_field(name="`lx mod status`", value="Check moderation status", inline=False)
        embed.add_field(name="`lx mod warnings <user>`", value="Check user warnings", inline=False)
        await ctx.send(embed=embed)

    @mod.command(name="on", help="Enable moderation for this server")
    @commands.has_permissions(manage_guild=True)
    async def mod_on(self, ctx):
        """Enable moderation for this guild"""
        guild_id = str(ctx.guild.id)
        self.moderation_enabled[guild_id] = True
        
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
            description="Enhanced toxic message detection is now active with strict punishment system.",
            color=discord.Color.green()
        )
        embed.add_field(name="Warning System", value="5 warnings = 1min timeout\n10 warnings = 10min timeout\n20 warnings = kick\n30 warnings = ban", inline=False)
        await ctx.send(embed=embed)

    @mod.command(name="off", help="Disable moderation for this server")
    @commands.has_permissions(manage_guild=True)
    async def mod_off(self, ctx):
        """Disable moderation for this guild"""
        guild_id = str(ctx.guild.id)
        self.moderation_enabled[guild_id] = False
        
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
            color=discord.Color.green() if status else discord.Color.red()
        )
        
        status_text = "✅ **ACTIVE**" if status else "❌ **INACTIVE**"
        embed.add_field(name="Status", value=status_text, inline=True)
        embed.add_field(name="Toxicity Threshold", value=f"{self.toxicity_threshold}", inline=True)
        embed.add_field(name="Attributes Checked", value=", ".join(self.enabled_attributes), inline=False)
        
        if status:
            embed.add_field(name="Punishment System", 
                          value="• 5 warnings → 1min timeout\n• 10 warnings → 10min timeout\n• 20 warnings → kick\n• 30 warnings → ban", 
                          inline=False)
        
        await ctx.send(embed=embed)

    @mod.command(name="warnings", help="Check warnings for a user")
    @commands.has_permissions(manage_messages=True)
    async def mod_warnings(self, ctx, member: discord.Member = None):
        """Check warnings for a user"""
        target = member or ctx.author
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Get user stats
        cursor.execute(
            "SELECT warnings, toxic_messages FROM karma WHERE guild_id = ? AND user_id = ?",
            (str(ctx.guild.id), str(target.id))
        )
        result = cursor.fetchone()
        warnings_count = result[0] if result else 0
        toxic_count = result[1] if result else 0
        
        # Get recent warnings
        cursor.execute(
            """SELECT reason, toxicity_score, timestamp, action_taken 
               FROM warnings WHERE guild_id = ? AND user_id = ? 
               ORDER BY timestamp DESC LIMIT 5""",
            (str(ctx.guild.id), str(target.id))
        )
        recent_warnings = cursor.fetchall()
        conn.close()
        
        embed = discord.Embed(
            title="⚠️ Warning Report",
            description=f"Warning data for {target.mention}",
            color=discord.Color.orange()
        )
        
        embed.add_field(name="Total Warnings", value=f"{warnings_count}", inline=True)
        embed.add_field(name="Toxic Messages", value=f"{toxic_count}", inline=True)
        embed.add_field(name="Next Punishment", value=self.get_next_punishment(warnings_count), inline=True)
        
        if recent_warnings:
            warning_text = ""
            for reason, score, timestamp, action in recent_warnings[:3]:
                dt = datetime.datetime.fromisoformat(timestamp)
                warning_text += f"• {action} - {dt.strftime('%m/%d %H:%M')} (Score: {score:.2f})\n"
            embed.add_field(name="Recent Warnings", value=warning_text, inline=False)
        
        embed.set_thumbnail(url=target.avatar.url if target.avatar else target.default_avatar.url)
        embed.set_footer(text=f"User ID: {target.id}")
        
        await ctx.send(embed=embed)

    def get_next_punishment(self, current_warnings):
        """Get the next punishment level"""
        if current_warnings >= 30:
            return "Already banned"
        elif current_warnings >= 20:
            return "Ban (30 warnings)"
        elif current_warnings >= 10:
            return "Kick (20 warnings)"
        elif current_warnings >= 5:
            return "10min timeout (10 warnings)"
        else:
            return f"1min timeout ({5 - current_warnings} more warnings)"

    @commands.group(name="karma", help="Karma system commands", invoke_without_command=True)
    async def karma(self, ctx):
        """Base command for karma system"""
        embed = discord.Embed(
            title="🌟 Karma Commands",
            description="Available karma commands:",
            color=discord.Color.blue()
        )
        embed.add_field(name="`lx karma check [@user]`", value="Check karma for yourself or another user", inline=False)
        embed.add_field(name="`lx karma leaderboard [limit]`", value="Show karma leaderboard (max 25)", inline=False)
        await ctx.send(embed=embed)

    @karma.command(name="check", help="Check karma for a user")
    async def karma_check(self, ctx, member: discord.Member = None):
        """Check karma for a user"""
        target = member or ctx.author
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT karma_points, positive_messages, toxic_messages, warnings 
               FROM karma WHERE guild_id = ? AND user_id = ?""",
            (str(ctx.guild.id), str(target.id))
        )
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            karma_points, positive_messages, toxic_messages, warnings = 0, 0, 0, 0
        else:
            karma_points, positive_messages, toxic_messages, warnings = result
            
        # Calculate stats
        total_messages = positive_messages + toxic_messages
        purity_percent = 100 if total_messages == 0 else round((positive_messages / total_messages) * 100)
        
        # Determine karma level and color
        if karma_points >= 100:
            level = "🌟 Saint"
            color = discord.Color.gold()
        elif karma_points >= 50:
            level = "😇 Angel"
            color = discord.Color.green()
        elif karma_points >= 0:
            level = "😊 Good"
            color = discord.Color.blue()
        elif karma_points >= -25:
            level = "😐 Neutral"
            color = discord.Color.orange()
        else:
            level = "😈 Toxic"
            color = discord.Color.red()
        
        embed = discord.Embed(
            title="🌟 Karma Profile",
            description=f"**{target.display_name}** ({target.name})",
            color=color
        )
        
        embed.add_field(name="Karma Points", value=f"**{karma_points}**", inline=True)
        embed.add_field(name="Level", value=level, inline=True)
        embed.add_field(name="Purity", value=f"**{purity_percent}%**", inline=True)
        
        embed.add_field(name="✅ Positive Messages", value=f"{positive_messages}", inline=True)
        embed.add_field(name="⚠️ Toxic Messages", value=f"{toxic_messages}", inline=True)
        embed.add_field(name="🚨 Warnings", value=f"{warnings}", inline=True)
        
        embed.set_thumbnail(url=target.avatar.url if target.avatar else target.default_avatar.url)
        embed.set_footer(text=f"User ID: {target.id} • Joined: {target.joined_at.strftime('%b %d, %Y')}")
        
        await ctx.send(embed=embed)

    @karma.command(name="leaderboard", aliases=["lb"], help="Show karma leaderboard")
    async def karma_leaderboard(self, ctx, limit: int = 10):
        """Show beautiful karma leaderboard"""
        if limit < 1:
            await ctx.send("⚠️ Please specify a positive number")
            return
            
        if limit > 25:
            limit = 25
            
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT user_id, username, display_name, karma_points, positive_messages, 
                   toxic_messages, warnings 
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
            embed = discord.Embed(
                title="📊 Karma Leaderboard",
                description="No karma data found for this server yet!",
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed)
            return
        
        # Create beautiful leaderboard embed
        embed = discord.Embed(
            title="🏆 Karma Leaderboard",
            description=f"Top {len(results)} users ranked by karma points",
            color=discord.Color.gold()
        )
        
        # Medal emojis for top 3
        medals = ["🥇", "🥈", "🥉"]
        
        leaderboard_text = ""
        for i, (user_id, username, display_name, karma, positive, toxic, warnings) in enumerate(results):
            # Get user object for avatar
            try:
                user = self.bot.get_user(int(user_id))
                if not user:
                    user = await self.bot.fetch_user(int(user_id))
            except:
                user = None
            
            # Calculate purity
            total = positive + toxic
            purity = 100 if total == 0 else round((positive / total) * 100)
            
            # Determine karma level emoji
            if karma >= 100:
                level_emoji = "🌟"
            elif karma >= 50:
                level_emoji = "😇"
            elif karma >= 0:
                level_emoji = "😊"
            elif karma >= -25:
                level_emoji = "😐"
            else:
                level_emoji = "😈"
            
            # Format ranking
            if i < 3:
                rank = medals[i]
            else:
                rank = f"`{i+1}.`"
            
            # Format names
            name_display = display_name if display_name != username else username
            
            leaderboard_text += f"{rank} **{name_display}** {level_emoji}\n"
            leaderboard_text += f"    ├ Karma: **{karma}** points\n"
            leaderboard_text += f"    ├ Purity: **{purity}%** ({positive}+/{toxic}-)\n"
            leaderboard_text += f"    └ Warnings: **{warnings}**\n\n"
        
        # Split into multiple fields if too long
        if len(leaderboard_text) > 1024:
            # Split at halfway point
            mid = len(results) // 2
            first_half = ""
            second_half = ""
            
            for i, (user_id, username, display_name, karma, positive, toxic, warnings) in enumerate(results):
                total = positive + toxic
                purity = 100 if total == 0 else round((positive / total) * 100)
                
                if karma >= 100:
                    level_emoji = "🌟"
                elif karma >= 50:
                    level_emoji = "😇"
                elif karma >= 0:
                    level_emoji = "😊"
                elif karma >= -25:
                    level_emoji = "😐"
                else:
                    level_emoji = "😈"
                
                rank = medals[i] if i < 3 else f"`{i+1}.`"
                name_display = display_name if display_name != username else username
                
                entry = f"{rank} **{name_display}** {level_emoji}\n    Karma: **{karma}** | Purity: **{purity}%** | Warnings: **{warnings}**\n\n"
                
                if i < mid:
                    first_half += entry
                else:
                    second_half += entry
            
            embed.add_field(name="🏆 Top Rankings", value=first_half, inline=False)
            if second_half:
                embed.add_field(name="📈 More Rankings", value=second_half, inline=False)
        else:
            embed.add_field(name="🏆 Rankings", value=leaderboard_text, inline=False)
        
        # Add server stats
        total_users = len(results)
        total_karma = sum(result[3] for result in results)
        avg_karma = total_karma // total_users if total_users > 0 else 0
        
        embed.add_field(name="📊 Server Stats", 
                       value=f"Total Users: **{total_users}**\nAverage Karma: **{avg_karma}**", 
                       inline=True)
        
        # Set footer with timestamp
        now = datetime.datetime.now()
        embed.set_footer(
            text=f"🕒 Updated: {now.strftime('%b %d, %Y at %H:%M')} • Use 'lx karma check' for detailed stats",
            icon_url=ctx.guild.icon.url if ctx.guild.icon else None
        )
        
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignore messages from bots
        if message.author.bot:
            return
            
        # Check if message is in a guild and if moderation is enabled
        if not message.guild or not self.is_moderation_enabled(message.guild.id):
            await self.update_karma(message, is_toxic=False)
            return
            
        # Analyze message content for toxicity
        try:
            toxicity_score, all_scores = await self.analyze_text_toxicity(message.content)
            
            if toxicity_score is None:
                await self.update_karma(message, is_toxic=False)
                return
                
            # If content exceeds threshold, handle as toxic
            if toxicity_score >= self.toxicity_threshold:
                try:
                    # Delete toxic message
                    await message.delete()
                    
                    # Update karma and get warning count
                    warning_count = await self.update_karma(message, is_toxic=True, toxicity_score=toxicity_score)
                    
                    # Apply appropriate punishment
                    await self.apply_punishment(message, warning_count, toxicity_score)
                    
                except discord.Forbidden:
                    # If can't delete message, just send warning
                    warning = await message.channel.send(
                        f"⚠️ {message.author.mention}, please keep your messages respectful! "
                        f"(Toxicity Score: {toxicity_score:.2f})"
                    )
                    await warning.delete(delay=8)
                except Exception as e:
                    print(f"Error handling toxic message: {e}")
            else:
                # Update karma positively
                await self.update_karma(message, is_toxic=False)
                
        except Exception as e:
            print(f"Error in message processing: {e}")
            await self.update_karma(message, is_toxic=False)

async def setup(bot):
    await bot.add_cog(Moderation(bot))
