import discord
from discord.ext import commands
import os
import aiohttp
import json
import datetime
import asyncio
from dotenv import load_dotenv
import sqlite3
import random

# Load environment variables
load_dotenv()

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.muted_role = None  # Store the muted role
        self.perspective_api_key = os.getenv("PERSPECTIVE_API_KEY")
        # Dictionary to store per-guild moderation state (guild_id: bool)
        self.moderation_enabled = {}
        self.toxicity_threshold = 0.7
        
        # Set up database for karma system
        self.setup_database()
        
        # List of all perspective API attributes we can check
        self.perspective_attributes = [
            "TOXICITY",
            "SEVERE_TOXICITY",
            "INSULT",
            "PROFANITY",
            "THREAT",
            "SEXUALLY_EXPLICIT",
            "FLIRTATION"
        ]
        
        # Attributes that are enabled by default
        self.enabled_attributes = ["TOXICITY"]

    def setup_database(self):
        """Set up SQLite database for karma tracking"""
        db_path = os.path.join(os.path.dirname(__file__), 'karma.db')
        
        # Create connection
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
                karma_enabled BOOLEAN DEFAULT 1,
                toxicity_threshold REAL DEFAULT 0.7
            )
        ''')
        
        conn.commit()
        conn.close()

    def get_db_connection(self):
        """Get a connection to the SQLite database"""
        db_path = os.path.join(os.path.dirname(__file__), 'karma.db')
        return sqlite3.connect(db_path)

    async def get_or_ask_muted_role(self, ctx):
        """Check for an existing Muted role or ask the user to specify one."""
        if self.muted_role:
            return self.muted_role

        muted_role = discord.utils.get(ctx.guild.roles, name="Muted")

        if not muted_role:
            await ctx.send("❓ No 'Muted' role found. Please mention the role you want to use for muting.")

            def check(m):
                return m.author == ctx.author and m.mentions and isinstance(m.channel, discord.TextChannel)

            try:
                msg = await ctx.bot.wait_for("message", check=check, timeout=30)
                muted_role = msg.role_mentions[0] if msg.role_mentions else None
                if muted_role:
                    self.muted_role = muted_role  # Store for future use
                    await ctx.send(f"✅ **Muted role set to:** {muted_role.mention}")
                else:
                    await ctx.send("❌ No valid role mentioned.")
            except asyncio.TimeoutError:
                await ctx.send("⏳ **No response received.** Please try again and mention a valid role.")
                return None

        return muted_role

    async def analyze_text_toxicity(self, text):
        """Analyze text using Google's Perspective API with multiple attributes"""
        if not self.perspective_api_key:
            return None, None  # API key not configured

        url = f"https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze?key={self.perspective_api_key}"
        
        # Build requested attributes dictionary
        requested_attributes = {}
        for attr in self.perspective_attributes:
            if attr in self.enabled_attributes:
                requested_attributes[attr] = {}
        
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
                        error_text = await response.text()
                        print(f"Perspective API error: {response.status} - {error_text}")
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
        
        # Check if karma is enabled for this guild
        cursor.execute("SELECT karma_enabled FROM guild_settings WHERE guild_id = ?", (str(message.guild.id),))
        result = cursor.fetchone()
        karma_enabled = True if not result else bool(result[0])
        
        if not karma_enabled:
            conn.close()
            return
        
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
        
        # Get enabled attributes from memory
        attributes_text = ", ".join(self.enabled_attributes)
        
        embed = discord.Embed(
            title="🔍 Moderation Status",
            color=discord.Color.blue()
        )
        
        status_text = "✅ Enabled" if status else "❌ Disabled"
        embed.add_field(name="Current Status", value=status_text, inline=False)
        embed.add_field(name="Toxicity Threshold", value=f"{self.toxicity_threshold}", inline=False)
        embed.add_field(name="Enabled Attributes", value=attributes_text or "None", inline=False)
        
        await ctx.send(embed=embed)
        
    @mod.command(name="attributes", help="Set which toxicity attributes to check")
    @commands.has_permissions(manage_guild=True)
    async def mod_attributes(self, ctx, *attributes):
        """Set which toxicity attributes to enable"""
        valid_attributes = []
        invalid_attributes = []
        
        # If no attributes provided, show current setup
        if not attributes:
            attr_text = "\n".join([f"✓ {attr}" if attr in self.enabled_attributes else f"✗ {attr}" 
                                for attr in self.perspective_attributes])
            
            embed = discord.Embed(
                title="📊 Available Toxicity Attributes",
                description="Currently checking for:",
                color=discord.Color.blue()
            )
            embed.add_field(name="Attributes", value=attr_text, inline=False)
            embed.add_field(
                name="Usage", 
                value=f"`lx mod attributes TOXICITY INSULT`\nEnable specific attributes\n\n"
                      f"`lx mod attributes all`\nEnable all attributes\n\n"
                      f"`lx mod attributes reset`\nReset to default (TOXICITY only)",
                inline=False
            )
            await ctx.send(embed=embed)
            return
            
        if "all" in [attr.lower() for attr in attributes]:
            # Enable all attributes
            self.enabled_attributes = self.perspective_attributes.copy()
            
            embed = discord.Embed(
                title="✅ All Attributes Enabled",
                description="Now checking for all toxicity categories.",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
            return
            
        if "reset" in [attr.lower() for attr in attributes]:
            # Reset to default
            self.enabled_attributes = ["TOXICITY"]
            
            embed = discord.Embed(
                title="🔄 Reset to Default",
                description="Now checking for TOXICITY only.",
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed)
            return
            
        # Process requested attributes
        for attr in attributes:
            attr_upper = attr.upper()
            if attr_upper in self.perspective_attributes:
                valid_attributes.append(attr_upper)
            else:
                invalid_attributes.append(attr)
                
        if valid_attributes:
            self.enabled_attributes = valid_attributes
                
        # Report results
        embed = discord.Embed(
            title="📊 Toxicity Attributes Updated",
            color=discord.Color.green()
        )
        
        embed.add_field(
            name="Enabled Attributes", 
            value="\n".join(f"✓ {attr}" for attr in self.enabled_attributes) or "None",
            inline=False
        )
        
        if invalid_attributes:
            embed.add_field(
                name="Invalid Attributes", 
                value="\n".join(invalid_attributes),
                inline=False
            )
            
        await ctx.send(embed=embed)

    @mod.command(name="threshold", help="Set toxicity threshold (0.0-1.0)")
    @commands.has_permissions(manage_guild=True)
    async def mod_threshold(self, ctx, threshold: float):
        """Set the toxicity threshold"""
        if not 0.0 <= threshold <= 1.0:
            await ctx.send("❌ Threshold must be between 0.0 and 1.0")
            return
            
        self.toxicity_threshold = threshold
        
        # Update database
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO guild_settings (guild_id, toxicity_threshold) VALUES (?, ?)",
            (str(ctx.guild.id), threshold)
        )
        conn.commit()
        conn.close()
        
        embed = discord.Embed(
            title="📏 Threshold Updated",
            description=f"Toxicity threshold set to {threshold}",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)

    @commands.command(name="warn", help="Warns a member.")
    @commands.has_permissions(manage_messages=True)
    async def warn(self, ctx, member: discord.Member, *, reason: str):
        embed = discord.Embed(
            title="⚠️ Warning", 
            description=f"{member.mention} has been warned.", 
            color=discord.Color.red()
        )
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.set_footer(text=f"Warned by {ctx.author.display_name}")
        await ctx.send(embed=embed)

    @commands.command(name="purge", help="Deletes messages.")
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx, amount: int):
        if amount <= 0:
            await ctx.send("❌ Please specify a positive number.")
            return
        deleted = await ctx.channel.purge(limit=amount)
        await ctx.send(f"🗑️ Deleted {len(deleted)} messages.", delete_after=5)

    @commands.command(name="kick", help="Kicks a member from the server.")
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason="No reason provided"):
        await member.kick(reason=reason)
        embed = discord.Embed(
            title="🚨 Member Kicked",
            description=f"**{member.name}** has been kicked.",
            color=discord.Color.orange()
        )
        embed.add_field(name="👮‍♂️ Moderator", value=ctx.author.mention, inline=True)
        embed.add_field(name="📜 Reason", value=reason, inline=True)
        embed.set_thumbnail(url=member.avatar.url if member.avatar else None)
        await ctx.send(embed=embed)

    @commands.command(name="ban", help="Bans a member from the server.")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason="No reason provided"):
        await member.ban(reason=reason)
        embed = discord.Embed(
            title="⛔ Member Banned",
            description=f"**{member.name}** has been banned.",
            color=discord.Color.red()
        )
        embed.add_field(name="👮‍♂️ Moderator", value=ctx.author.mention, inline=True)
        embed.add_field(name="📜 Reason", value=reason, inline=True)
        embed.set_thumbnail(url=member.avatar.url if member.avatar else None)
        await ctx.send(embed=embed)

    @commands.command(name="mute", help="Mutes a member in the server.")
    @commands.has_permissions(manage_roles=True)
    async def mute(self, ctx, member: discord.Member):
        muted_role = await self.get_or_ask_muted_role(ctx)
        
        if muted_role and muted_role not in member.roles:
            await member.add_roles(muted_role)
            embed = discord.Embed(
                title="🔇 Member Muted",
                description=f"**{member.name}** has been muted.",
                color=discord.Color.dark_gray()
            )
            embed.add_field(name="👮‍♂️ Moderator", value=ctx.author.mention, inline=True)
            embed.set_thumbnail(url=member.avatar.url if member.avatar else None)
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"⚠ {member.name} is already muted or role is missing!")

    @commands.command(name="unmute", help="Unmutes a member in the server.")
    @commands.has_permissions(manage_roles=True)
    async def unmute(self, ctx, member: discord.Member):
        muted_role = await self.get_or_ask_muted_role(ctx)

        if muted_role and muted_role in member.roles:
            await member.remove_roles(muted_role)
            embed = discord.Embed(
                title="🔊 Member Unmuted",
                description=f"**{member.name}** has been unmuted.",
                color=discord.Color.green()
            )
            embed.add_field(name="👮‍♂️ Moderator", value=ctx.author.mention, inline=True)
            embed.set_thumbnail(url=member.avatar.url if member.avatar else None)
            await ctx.send(embed=embed)
        else:
            await ctx.send("⚠ User is not muted or muted role is missing!")

    @commands.group(name="karma", help="Karma system commands", invoke_without_command=True)
    async def karma(self, ctx):
        """Base command for karma system"""
        await ctx.send("Please use `lx karma check`, `lx karma leaderboard`, or `lx karma reset`")

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
        embed.set_footer(text="Karma System")
        
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

    @karma.command(name="reset", help="Reset karma for a user")
    @commands.has_permissions(manage_guild=True)
    async def karma_reset(self, ctx, member: discord.Member):
        """Reset karma for a specific user"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM karma WHERE guild_id = ? AND user_id = ?",
            (str(ctx.guild.id), str(member.id))
        )
        conn.commit()
        conn.close()
        
        embed = discord.Embed(
            title="🧹 Karma Reset",
            description=f"Karma data for {member.mention} has been reset.",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)

    @karma.command(name="on", help="Enable karma system")
    @commands.has_permissions(manage_guild=True)
    async def karma_on(self, ctx):
        """Enable karma system for this guild"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO guild_settings (guild_id, karma_enabled) VALUES (?, 1)",
            (str(ctx.guild.id),)
        )
        conn.commit()
        conn.close()
        
        embed = discord.Embed(
            title="✅ Karma System Enabled",
            description="Karma tracking is now active.",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @karma.command(name="off", help="Disable karma system")
    @commands.has_permissions(manage_guild=True)
    async def karma_off(self, ctx):
        """Disable karma system for this guild"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO guild_settings (guild_id, karma_enabled) VALUES (?, 0)",
            (str(ctx.guild.id),)
        )
        conn.commit()
        conn.close()
        
        embed = discord.Embed(
            title="🚫 Karma System Disabled",
            description="Karma tracking is now inactive.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignore messages from bots
        if message.author.bot:
            return
            
        # Make sure commands still work
        await self.bot.process_commands(message)
        
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
                    
                    # Prepare detailed score information
                    score_details = ""
                    if all_scores:
                        for attr, score in all_scores.items():
                            score_details += f"\n• {attr}: {score:.2f}"
                    
                    # Send warning
                    warning = await message.channel.send(
                        f"⚠️ {message.author.mention}, your message was removed for containing toxic content. "
                        f"(Score: {toxicity_score:.2f}){score_details}"
                    )
                    
                    # Delete warning after a few seconds
                    await warning.delete(delay=10)
                    
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

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """Handle command errors"""
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ **You don't have permission to use this command!**")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ **Missing required argument:** {error.param.name}")
        elif isinstance(error, commands.BadArgument):
            await ctx.send(f"❌ **Invalid argument:** {error}")
        else:
            print(f"Command error: {error}")

def setup(bot):
    bot.add_cog(Moderation(bot))
