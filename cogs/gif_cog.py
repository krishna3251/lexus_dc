import discord
from discord.ext import commands
import random
import aiohttp
import os
from typing import Optional

class GifCog(commands.Cog):
    """Send various GIFs and animated reactions"""
    
    def __init__(self, bot):
        self.bot = bot
        self.tenor_api_key = os.getenv("TENOR_API_KEY", "")
        self.giphy_api_key = os.getenv("GIPHY_API_KEY", "")
        
        # Fallback GIFs in case API key is not provided or API request fails
        self.fallback_gifs = {
            "hug": [
                "https://media.giphy.com/media/od5H3PmEG5EVq/giphy.gif",
                "https://media.giphy.com/media/lrr9rHuoJOE0w/giphy.gif",
                "https://media.giphy.com/media/ZQN9jsRWp1M76/giphy.gif"
            ],
            "slap": [
                "https://media.giphy.com/media/Zau0yrl17uzdK/giphy.gif",
                "https://media.giphy.com/media/xUO4t2gkWBxDi/giphy.gif",
                "https://media.giphy.com/media/uqSU9IEYEKAbS/giphy.gif"
            ],
            "kiss": [
                "https://media.giphy.com/media/G3va31oEEnIkM/giphy.gif",
                "https://media.giphy.com/media/bGm9FuBCGg4SY/giphy.gif",
                "https://media.giphy.com/media/hnNyVPIXgLdle/giphy.gif"
            ],
            "pat": [
                "https://media.giphy.com/media/ARSp9T7wwxNcs/giphy.gif",
                "https://media.giphy.com/media/109ltuoSQT212w/giphy.gif",
                "https://media.giphy.com/media/L2z7dnOduqEow/giphy.gif"
            ],
            "poke": [
                "https://media.giphy.com/media/WvVzZ9mCyMjsc/giphy.gif",
                "https://media.giphy.com/media/tFK6urY1CfQiI/giphy.gif",
                "https://media.giphy.com/media/pWd3gD577gOqs/giphy.gif"
            ],
            "dance": [
                "https://media.giphy.com/media/5xaOcLGvzHxDKjufnLW/giphy.gif",
                "https://media.giphy.com/media/l3q2Hy66w1hpDSWUE/giphy.gif",
                "https://media.giphy.com/media/l4Ep3mmmj7Bw3adWw/giphy.gif"
            ],
            "cry": [
                "https://media.giphy.com/media/L95W4wv8nnb9K/giphy.gif",
                "https://media.giphy.com/media/OPU6wzx8JrHna/giphy.gif",
                "https://media.giphy.com/media/d2lcHJTG5Tscg/giphy.gif"
            ],
            "laugh": [
                "https://media.giphy.com/media/wWue0rCDOphOE/giphy.gif",
                "https://media.giphy.com/media/3o7TKMt1VVNkHV2WaI/giphy.gif",
                "https://media.giphy.com/media/10jiIZ5AxZvpHW/giphy.gif"
            ],
            "facepalm": [
                "https://media.giphy.com/media/3og0INyCmHlNylks9O/giphy.gif",
                "https://media.giphy.com/media/6yRVg0HWzgS88/giphy.gif",
                "https://media.giphy.com/media/tnYri4n2Frnig/giphy.gif"
            ],
            "highfive": [
                "https://media.giphy.com/media/3oEjHV0z8S7WM4MwnK/giphy.gif",
                "https://media.giphy.com/media/Qwi6fEcn2JJeg/giphy.gif",
                "https://media.giphy.com/media/HX3lSnGXZnaWk/giphy.gif"
            ]
        }
        
        # Message templates for each action
        self.messages = {
            "hug": [
                "{user} gives {target} a big warm hug!",
                "{user} hugs {target} tightly!",
                "{user} wraps their arms around {target} in a comforting embrace!",
                "A wild {user} appears and hugs {target}!"
            ],
            "slap": [
                "{user} slaps {target}! Ouch!",
                "{user} gives {target} a reality check with a slap!",
                "{target} feels the wrath of {user}'s slap!",
                "{user} slaps {target} across the face!"
            ],
            "kiss": [
                "{user} gives {target} a sweet kiss!",
                "{user} plants a tender kiss on {target}!",
                "{user} and {target} share a romantic moment!",
                "{user} surprises {target} with a kiss!"
            ],
            "pat": [
                "{user} gently pats {target} on the head!",
                "{user} gives {target} comforting pats!",
                "{user} pats {target} for being good!",
                "{target} receives headpats from {user}!"
            ],
            "poke": [
                "{user} pokes {target}! Boop!",
                "{user} pokes {target} to get their attention!",
                "{user} can't resist poking {target}!",
                "{target} gets a surprise poke from {user}!"
            ],
            "dance": [
                "{user} busts out some moves with {target}!",
                "{user} and {target} hit the dance floor!",
                "{user} shows off their dancing skills to {target}!",
                "Dance battle between {user} and {target}!"
            ],
            "cry": [
                "{user} cries uncontrollably!",
                "{user} bursts into tears!",
                "{user} can't hold back the waterworks!",
                "Someone get {user} some tissues!"
            ],
            "laugh": [
                "{user} can't stop laughing!",
                "{user} laughs hysterically!",
                "{user} is in stitches!",
                "{user} laughs so hard they might pass out!"
            ],
            "facepalm": [
                "{user} facepalms at {target}'s antics!",
                "{user} can't believe what {target} just did!",
                "{user} is disappointed in {target}!",
                "{user} questions {target}'s life choices with a facepalm!"
            ],
            "highfive": [
                "{user} gives {target} an epic high five!",
                "{user} and {target} celebrate with a high five!",
                "{user} high fives {target}! That sounded like it hurt!",
                "{target} receives a powerful high five from {user}!"
            ]
        }
    
    async def fetch_gif(self, action):
        """Fetch a random GIF for the specified action"""
        # Try to use Tenor API first if key is available
        if self.tenor_api_key:
            try:
                async with aiohttp.ClientSession() as session:
                    search_term = f"anime {action}"
                    url = f"https://tenor.googleapis.com/v2/search?q={search_term}&key={self.tenor_api_key}&limit=10&media_filter=gif"
                    
                    async with session.get(url) as response:
                        if response.status == 200:
                            data = await response.json()
                            if data["results"]:
                                return data["results"][random.randint(0, len(data["results"])-1)]["media_formats"]["gif"]["url"]
            except Exception:
                pass
        
        # Try GIPHY API as fallback if key is available
        if self.giphy_api_key:
            try:
                async with aiohttp.ClientSession() as session:
                    search_term = f"anime {action}"
                    url = f"https://api.giphy.com/v1/gifs/search?api_key={self.giphy_api_key}&q={search_term}&limit=10"
                    
                    async with session.get(url) as response:
                        if response.status == 200:
                            data = await response.json()
                            if data["data"]:
                                return data["data"][random.randint(0, len(data["data"])-1)]["images"]["original"]["url"]
            except Exception:
                pass
        
        # Use fallback GIFs if both API requests fail or no keys are provided
        return random.choice(self.fallback_gifs.get(action, ["https://media.giphy.com/media/3o7TKuFYevgE2b6Mx2/giphy.gif"]))
    
    def create_action_embed(self, action, user, target, gif_url):
        """Create an embed for the action"""
        # Select a random message template
        message_templates = self.messages.get(action, ["{user} does something to {target}!"])
        message = random.choice(message_templates).format(user=user.display_name, target=target.display_name if target else "themselves")
        
        # Create the embed
        embed = discord.Embed(
            title=action.capitalize(),
            description=message,
            color=0x3a9efa
        )
        embed.set_image(url=gif_url)
        embed.set_footer(text="React with your own GIFs!")
        
        return embed
    
    # Generic action command methods
    async def perform_action(self, ctx, action, target=None):
        """Common method for performing any GIF action"""
        if target is None and action not in ["cry", "laugh"]:
            await ctx.send("You need to specify a target for this action!")
            return
            
        async with ctx.typing():
            # Fetch a GIF
            gif_url = await self.fetch_gif(action)
            
            # Create and send the embed
            embed = self.create_action_embed(action, ctx.author, target, gif_url)
            await ctx.send(embed=embed)
    
    # Define commands for each action
    @commands.command(name="hug")
    async def hug(self, ctx, *, target: discord.Member = None):
        """Give someone a hug!"""
        if target is None:
            target = ctx.author
        await self.perform_action(ctx, "hug", target)
    
    @commands.command(name="slap")
    async def slap(self, ctx, *, target: discord.Member = None):
        """Slap someone!"""
        if target is None:
            target = ctx.author
        await self.perform_action(ctx, "slap", target)
    
    @commands.command(name="kiss")
    async def kiss(self, ctx, *, target: discord.Member = None):
        """Kiss someone!"""
        if target is None:
            target = ctx.author
        await self.perform_action(ctx, "kiss", target)
    
    @commands.command(name="pat")
    async def pat(self, ctx, *, target: discord.Member = None):
        """Pat someone on the head!"""
        if target is None:
            target = ctx.author
        await self.perform_action(ctx, "pat", target)
    
    @commands.command(name="poke")
    async def poke(self, ctx, *, target: discord.Member = None):
        """Poke someone!"""
        if target is None:
            target = ctx.author
        await self.perform_action(ctx, "poke", target)
    
    @commands.command(name="dance")
    async def dance(self, ctx, *, target: discord.Member = None):
        """Dance with someone or by yourself!"""
        await self.perform_action(ctx, "dance", target or ctx.author)
    
    @commands.command(name="cry")
    async def cry(self, ctx):
        """Show that you're crying"""
        await self.perform_action(ctx, "cry", ctx.author)
    
    @commands.command(name="laugh")
    async def laugh(self, ctx):
        """Show that you're laughing"""
        await self.perform_action(ctx, "laugh", ctx.author)
    
    @commands.command(name="facepalm")
    async def facepalm(self, ctx, *, target: discord.Member = None):
        """Facepalm at someone's actions"""
        if target is None:
            target = ctx.author
        await self.perform_action(ctx, "facepalm", target)
    
    @commands.command(name="highfive")
    async def highfive(self, ctx, *, target: discord.Member = None):
        """Give someone a high five!"""
        if target is None:
            target = ctx.author
        await self.perform_action(ctx, "highfive", target)
    
    @commands.command(name="gif")
    async def gif(self, ctx, *, search_term: str):
        """Search for a GIF"""
        async with ctx.typing():
            gif_url = None
            
            # Try Tenor API first
            if self.tenor_api_key:
                try:
                    async with aiohttp.ClientSession() as session:
                        url = f"https://tenor.googleapis.com/v2/search?q={search_term}&key={self.tenor_api_key}&limit=20&media_filter=gif"
                        
                        async with session.get(url) as response:
                            if response.status == 200:
                                data = await response.json()
                                if data["results"]:
                                    gif_url = data["results"][random.randint(0, len(data["results"])-1)]["media_formats"]["gif"]["url"]
                except Exception:
                    pass
            
            # Try GIPHY API as fallback
            if not gif_url and self.giphy_api_key:
                try:
                    async with aiohttp.ClientSession() as session:
                        url = f"https://api.giphy.com/v1/gifs/search?api_key={self.giphy_api_key}&q={search_term}&limit=20"
                        
                        async with session.get(url) as response:
                            if response.status == 200:
                                data = await response.json()
                                if data["data"]:
                                    gif_url = data["data"][random.randint(0, len(data["data"])-1)]["images"]["original"]["url"]
                except Exception:
                    pass
            
            if gif_url:
                embed = discord.Embed(
                    title=f"GIF: {search_term}",
                    color=0x3a9efa
                )
                embed.set_image(url=gif_url)
                embed.set_footer(text=f"Requested by {ctx.author.display_name}")
                
                await ctx.send(embed=embed)
            else:
                await ctx.send(f"Couldn't find a GIF for '{search_term}'. Try a different search term.")
    
    @commands.command(name="gifhelp")
    async def gifhelp(self, ctx):
        """Show available GIF commands"""
        embed = discord.Embed(
            title="🎬 GIF Commands",
            description="Express yourself with animated GIFs!",
            color=0x3a9efa
        )
        
        # Action commands
        actions = ["hug", "slap", "kiss", "pat", "poke", "dance", "cry", "laugh", "facepalm", "highfive"]
        action_commands = "\n".join([f"**{ctx.prefix}{action} [@user]** - {action.capitalize()} someone!" for action in actions])
        
        embed.add_field(name="Action GIFs", value=action_commands, inline=False)
        
        # Search command
        embed.add_field(
            name="GIF Search",
            value=f"**{ctx.prefix}gif [search term]** - Search for a GIF with the given term",
            inline=False
        )
        
        embed.set_footer(text="Most commands can target another user or yourself!")
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(GifCog(bot))
