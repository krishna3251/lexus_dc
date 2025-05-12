import os
import discord
import aiohttp
from dotenv import load_dotenv
from discord.ext import commands
from discord import app_commands
from typing import Optional
import logging

# Load environment variables
load_dotenv()
STRANGE_API_KEY = os.getenv("STRANGE_API_KEY")

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class StrangeAPI:
    """Helper class to handle Strange API requests"""
    BASE_URL = "https://strangeapi.hostz.me/api/"
    
    @staticmethod
    async def apply_effect(effect: str, avatar_url: str) -> Optional[bytes]:
        """
        Apply an effect to an avatar using Strange API
        
        Args:
            effect: The effect to apply (e.g., 'wanted', 'blur')
            avatar_url: The URL of the avatar to apply the effect to
            
        Returns:
            bytes: The image data if successful, None otherwise
        """
        endpoint = f"{StrangeAPI.BASE_URL}/{effect}"
        params = {
            "key": STRANGE_API_KEY,
            "avatar": avatar_url
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(endpoint, params=params) as response:
                    if response.status == 200:
                        return await response.read()
                    else:
                        logger.error(f"Strange API error: {response.status} - {await response.text()}")
                        return None
        except Exception as e:
            logger.error(f"Error calling Strange API: {e}")
            return None

class EffectButton(discord.ui.Button):
    """Button for each image effect"""
    def __init__(self, effect_name: str, effect_id: str, emoji: str = None):
        style = discord.ButtonStyle.secondary
        super().__init__(style=style, label=effect_name.title(), emoji=emoji, custom_id=f"effect:{effect_id}")
        self.effect_id = effect_id
        
    async def callback(self, interaction: discord.Interaction):
        # This will be handled by the view's interaction check
        pass

class ImageEffectsView(discord.ui.View):
    """UI View with buttons for each image effect"""
    def __init__(self, cog, user: discord.User, timeout: int = 60):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.user = user
        
        # Add buttons for each effect
        effects = [
            ("Wanted", "wanted", "🔍"),
            ("Greyscale", "greyscale", "⚪"),
            ("Trash", "trash", "🗑️"),
            ("Invert", "invert", "🔄"),
            ("Blur", "blur", "🌫️"),
            ("Pixelate", "pixelate", "🔲"),
            ("Sepia", "sepia", "🟤"),
            ("Triggered", "triggered", "😡"),
            ("Jail", "jail", "🔒"),
            ("Rainbow", "gay", "🌈"),
            ("Glass", "glass", "🔍"),
            ("Wasted", "wasted", "💀")
        ]
        
        # Create 3 rows of 4 buttons each
        for i, (name, effect_id, emoji) in enumerate(effects):
            button = EffectButton(name, effect_id, emoji)
            self.add_item(button)
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Handle button clicks"""
        if interaction.data["custom_id"].startswith("effect:"):
            effect = interaction.data["custom_id"].split(":")[1]
            await interaction.response.defer(thinking=True)
            await self.cog.process_effect(interaction, effect, self.user)
            return False  # Don't call the button's callback
        return True
        
    async def on_timeout(self):
        """Disable all buttons when the view times out"""
        for item in self.children:
            item.disabled = True

class ImageEffectsCog(commands.Cog):
    """Discord bot cog for applying various image effects to user avatars"""
    
    def __init__(self, bot):
        self.bot = bot
        self.effects = {
            "wanted": "Wanted Poster",
            "greyscale": "Black & White",
            "trash": "Thrown in the Trash",
            "invert": "Color Inversion",
            "blur": "Blurred",
            "pixelate": "Pixelated",
            "sepia": "Sepia Tone",
            "triggered": "Triggered Animation",
            "jail": "Behind Bars",
            "gay": "Rainbow Filter",
            "glass": "Glass Effect",
            "wasted": "GTA Wasted"
        }
        
    def get_help_embed(self):
        """Create a help embed for the image effects command"""
        embed = discord.Embed(
            title="🖼️ Image Effects Help",
            description="Apply various visual effects to your avatar or someone else's avatar.",
            color=0x7289DA
        )
        
        embed.add_field(
            name="Usage",
            value="`/imagefx [user]` or `!imagefx [user]`\nClick on the buttons to apply different effects.",
            inline=False
        )
        
        # Create effect descriptions
        effect_desc = ""
        for effect_id, effect_name in self.effects.items():
            effect_desc += f"• **{effect_name}**: `{effect_id}`\n"
        
        embed.add_field(
            name="Available Effects",
            value=effect_desc,
            inline=False
        )
        
        embed.set_footer(text="Powered by Strange API")
        return embed
        
    @commands.hybrid_command(
        name="imagefx",
        description="Apply visual effects to a user's avatar"
    )
    @app_commands.describe(
        user="The user whose avatar to apply effects to (defaults to you)",
        effect="The effect to apply immediately (optional)"
    )
    @app_commands.choices(effect=[
        app_commands.Choice(name="Wanted Poster", value="wanted"),
        app_commands.Choice(name="Black & White", value="greyscale"),
        app_commands.Choice(name="Thrown in the Trash", value="trash"),
        app_commands.Choice(name="Color Inversion", value="invert"),
        app_commands.Choice(name="Blurred", value="blur"),
        app_commands.Choice(name="Pixelated", value="pixelate"),
        app_commands.Choice(name="Sepia Tone", value="sepia"),
        app_commands.Choice(name="Triggered Animation", value="triggered"),
        app_commands.Choice(name="Behind Bars", value="jail"),
        app_commands.Choice(name="Rainbow Filter", value="gay"),
        app_commands.Choice(name="Glass Effect", value="glass"),
        app_commands.Choice(name="GTA Wasted", value="wasted"),
        app_commands.Choice(name="Help", value="help")
    ])
    async def imagefx(self, ctx, user: Optional[discord.Member] = None, effect: str = None):
        """
        Apply visual effects to a user's avatar
        
        Parameters:
        -----------
        user: discord.Member, optional
            The user whose avatar to apply effects to (defaults to the command user)
        effect: str, optional
            The effect to apply immediately (if not provided, shows UI buttons)
        """
        # Default to command author if no user is specified
        target_user = user or ctx.author
        
        # Handle the "help" effect option
        if effect == "help":
            embed = self.get_help_embed()
            await ctx.send(embed=embed)
            return
            
        # If an effect is specified, apply it directly
        if effect and effect in self.effects:
            await ctx.defer()
            await self.process_effect(ctx, effect, target_user)
            return
            
        # Otherwise, show the UI with buttons
        embed = discord.Embed(
            title="🖼️ Image Effects",
            description=f"Choose an effect to apply to {target_user.mention}'s avatar:",
            color=0x5865F2
        )
        
        # Set the user's avatar as the embed thumbnail
        embed.set_thumbnail(url=target_user.display_avatar.url)
        
        # Create a view with buttons for each effect
        view = ImageEffectsView(self, target_user)
        
        await ctx.send(embed=embed, view=view)
    
    async def process_effect(self, ctx, effect: str, user: discord.User):
        """Process the selected effect and send the resulting image"""
        # Get user's avatar URL (with size 1024 for better quality)
        avatar_url = user.display_avatar.with_size(1024).url
        
        # Apply the effect using the Strange API
        image_data = await StrangeAPI.apply_effect(effect, avatar_url)
        
        if not image_data:
            if isinstance(ctx, discord.Interaction):
                await ctx.followup.send("Sorry, something went wrong with the image effect. Please try again later.")
            else:
                await ctx.send("Sorry, something went wrong with the image effect. Please try again later.")
            return
            
        # Create an embed for the resulting image
        effect_name = self.effects.get(effect, effect.title())
        embed = discord.Embed(
            title=f"🖼️ {effect_name} Effect",
            description=f"Applied to {user.mention}'s avatar",
            color=0x5865F2
        )
        embed.set_footer(text="Powered by Strange API")
        
        # Create the file from the image data
        file = discord.File(fp=image_data, filename=f"{effect}_avatar.png")
        embed.set_image(url=f"attachment://{effect}_avatar.png")
        
        # Send the response
        if isinstance(ctx, discord.Interaction):
            await ctx.followup.send(embed=embed, file=file)
        else:
            await ctx.send(embed=embed, file=file)

async def setup(bot):
    """Add the cog to the bot"""
    await bot.add_cog(ImageEffectsCog(bot))
