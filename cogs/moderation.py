import discord
from discord.ext import commands
import os
import aiohttp
import json
from dotenv import load_dotenv

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
                muted_role = msg.mentions[0]
                self.muted_role = muted_role  # Store for future use
                await ctx.send(f"✅ **Muted role set to:** {muted_role.mention}")
            except Exception:
                await ctx.send("⏳ **No response received.** Please try again and mention a valid role.")

        return muted_role

    async def analyze_text_toxicity(self, text):
        """Analyze text toxicity using Google's Perspective API"""
        if not self.perspective_api_key:
            return None  # API key not configured

        url = f"https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze?key={self.perspective_api_key}"
        
        payload = {
            "comment": {"text": text},
            "languages": ["en"],
            "requestedAttributes": {"TOXICITY": {}}
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        toxicity_score = data["attributeScores"]["TOXICITY"]["summaryScore"]["value"]
                        return toxicity_score
                    else:
                        error_text = await response.text()
                        print(f"Perspective API error: {response.status} - {error_text}")
                        return None
        except Exception as e:
            print(f"Error analyzing toxicity: {e}")
            return None

    def is_moderation_enabled(self, guild_id):
        """Check if moderation is enabled for a guild"""
        # Default to enabled if not set
        return self.moderation_enabled.get(str(guild_id), True)

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

    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignore messages from bots
        if message.author.bot:
            return
            
        # Make sure commands still work
        await self.bot.process_commands(message)
        
        # Check if message is in a guild and if moderation is enabled
        if not message.guild or not self.is_moderation_enabled(message.guild.id):
            return
            
        # Analyze message content for toxicity
        try:
            toxicity_score = await self.analyze_text_toxicity(message.content)
            
            # If we couldn't get a score or the content is safe, return
            if toxicity_score is None or toxicity_score < self.toxicity_threshold:
                return
                
            # Delete toxic message
            await message.delete()
            
            # Send warning
            warning = await message.channel.send(
                f"⚠️ {message.author.mention}, your message was removed for containing toxic content. "
                f"(Toxicity score: {toxicity_score:.2f})"
            )
            
            # Delete warning after a few seconds
            await warning.delete(delay=5)
            
        except Exception as e:
            print(f"Error processing message moderation: {e}")

async def setup(bot):
    await bot.add_cog(Moderation(bot))
