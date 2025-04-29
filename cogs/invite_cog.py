import discord
from discord.ext import commands
from discord import app_commands
import os

class InviteCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Get support server URL from environment variable
        self.support_server = os.getenv("SUPPORT_SERVER_URL", "")
        self.github_repo = os.getenv("GITHUB_REPO_URL", "")
    
    @commands.command(name="invite", help="Sends an invite link with an embedded message and buttons.")
    async def invite_command(self, ctx):
        await self.send_invite_embed(ctx)
    
    @app_commands.command(name="invite", description="Sends an invite link with an embedded message and buttons.")
    async def slash_invite_command(self, interaction: discord.Interaction):
        await self.send_invite_embed(interaction)
    
    async def send_invite_embed(self, ctx_or_interaction):
        """Create and send an embed with multiple buttons"""
        # Set up sensible default permissions instead of full admin
        permissions = discord.Permissions(
            send_messages=True,
            embed_links=True,
            attach_files=True,
            read_messages=True,
            read_message_history=True,
            add_reactions=True,
            use_external_emojis=True,
            manage_messages=True
        )
        
        # Get bot user based on context type
        if isinstance(ctx_or_interaction, commands.Context):
            bot_user = ctx_or_interaction.bot.user
        else:
            bot_user = ctx_or_interaction.client.user
            
        invite_link = discord.utils.oauth_url(bot_user.id, permissions=permissions)
        
        # Create a more visually appealing embed
        embed = discord.Embed(
            title="🚀 Add Our Bot to Your Server!",
            description="Enhance your Discord experience with powerful tools and features for your community!",
            color=discord.Color.blurple()
        )
        
        # Add bot avatar if available
        if bot_user.avatar:
            embed.set_thumbnail(url=bot_user.avatar.url)
        
        # Add more detailed feature sections
        embed.add_field(
            name="🛡️ Moderation & Administration",
            value="• Advanced auto-moderation\n• Custom warning system\n• Server analytics\n• Role management",
            inline=True
        )
        
        embed.add_field(
            name="🔍 Search Functionality",
            value="• Search the web directly\n• YouTube video search\n• Wikipedia articles\n• GitHub repositories",
            inline=True
        )
        
        embed.add_field(
            name="🎮 Fun & Engagement",
            value="• Games & trivia\n• Polls & surveys\n• Custom reaction roles\n• Community events",
            inline=False
        )
        
        embed.add_field(
            name="⚙️ Getting Started",
            value="After adding the bot, use `/help` to explore all available commands.",
            inline=False
        )
        
        # Create a view with multiple buttons
        view = discord.ui.View(timeout=None)
        
        # Main invite button (primary color)
        invite_button = discord.ui.Button(
            label="Add to Server", 
            url=invite_link, 
            style=discord.ButtonStyle.link,
            emoji="➕"
        )
        view.add_item(invite_button)
        
        # Support server button (if configured)
        if self.support_server:
            support_button = discord.ui.Button(
                label="Support Server", 
                url=self.support_server, 
                style=discord.ButtonStyle.link,
                emoji="🔧"
            )
            view.add_item(support_button)
        
        # GitHub repo button (if configured)
        if self.github_repo:
            github_button = discord.ui.Button(
                label="GitHub Repository", 
                url=self.github_repo, 
                style=discord.ButtonStyle.link,
                emoji="📂"
            )
            view.add_item(github_button)
        
        # Add vote button (example for top.gg)
        vote_url = f"https://top.gg/bot/{bot_user.id}/vote"
        vote_button = discord.ui.Button(
            label="Vote for Bot", 
            url=vote_url, 
            style=discord.ButtonStyle.link,
            emoji="⭐"
        )
        view.add_item(vote_button)
        
        # Send the embed with buttons
        if isinstance(ctx_or_interaction, commands.Context):
            await ctx_or_interaction.send(embed=embed, view=view)
        else:
            await ctx_or_interaction.response.send_message(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(InviteCog(bot))