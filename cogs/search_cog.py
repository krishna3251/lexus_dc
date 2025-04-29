import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import json
import re
import urllib.parse
import asyncio
from typing import Optional, List, Dict, Any, Union
import os
import datetime

class PaginationView(discord.ui.View):
    """Custom view for pagination using buttons instead of reactions"""
    
    def __init__(self, pages, author_id):
        super().__init__(timeout=120)
        self.pages = pages
        self.author_id = author_id
        self.current_page = 0
        
    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, emoji="◀️")
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("You can't use these controls.", ephemeral=True)
            return
            
        if self.current_page > 0:
            self.current_page -= 1
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
        else:
            await interaction.response.defer()
    
    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, emoji="▶️")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("You can't use these controls.", ephemeral=True)
            return
            
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
        else:
            await interaction.response.defer()
    
    async def on_timeout(self):
        # Disable all buttons when the view times out
        for item in self.children:
            item.disabled = True

class SearchCog(commands.Cog):
    """Search the web directly from Discord"""
    
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        
        # API Keys - get from environment or use empty string
        self.google_api_key = os.getenv("GOOGLE_API_KEY", "")
        self.google_cx = os.getenv("GOOGLE_CSE_ID", "")  
        self.openweather_api_key = os.getenv("OPENWEATHER_API_KEY", "")
        self.youtube_api_key = os.getenv("YOUTUBE_API_KEY", "")
        self.github_token = os.getenv("GITHUB_TOKEN", "")
        self.news_api_key = os.getenv("NEWS_API_KEY", "")
        
        # Add cooldowns for slash commands
        self._cd = commands.CooldownMapping.from_cooldown(1, 5, commands.BucketType.user)
        self._cd_weather = commands.CooldownMapping.from_cooldown(1, 10, commands.BucketType.user)
    
    def cog_unload(self):
        """Clean up the aiohttp session when the cog is unloaded"""
        if self.session:
            self.bot.loop.create_task(self.session.close())
    
    async def make_request(self, url: str, headers: Dict[str, str] = None) -> Dict[str, Any]:
        """Make a request to the specified URL and return the JSON response"""
        try:
            async with self.session.get(url, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return {"error": f"Status {response.status}: {response.reason}"}
        except Exception as e:
            return {"error": str(e)}
    
    def create_embed_pages(self, items: List[Dict[str, Any]], title: str, formatter, color=0x3a9efa) -> List[discord.Embed]:
        """Create paginated embeds from a list of items using the provided formatter function"""
        pages = []
        items_per_page = 5
        
        for i in range(0, len(items), items_per_page):
            page_items = items[i:i+items_per_page]
            
            embed = discord.Embed(
                title=title,
                description=formatter(page_items),
                color=color
            )
            
            page_num = i // items_per_page + 1
            total_pages = (len(items) + items_per_page - 1) // items_per_page
            embed.set_footer(text=f"Page {page_num}/{total_pages} • Results provided as of {datetime.datetime.now().strftime('%Y-%m-%d')}")
            
            pages.append(embed)
        
        return pages
    
    async def send_paginated_results(self, ctx_or_interaction, pages):
        """Send results with button pagination"""
        is_interaction = isinstance(ctx_or_interaction, discord.Interaction)
        author_id = ctx_or_interaction.user.id if is_interaction else ctx_or_interaction.author.id
        
        if len(pages) == 1:
            if is_interaction:
                await ctx_or_interaction.response.send_message(embed=pages[0])
            else:
                await ctx_or_interaction.send(embed=pages[0])
            return
        
        # Create pagination view
        view = PaginationView(pages, author_id)
        
        if is_interaction:
            await ctx_or_interaction.response.send_message(embed=pages[0], view=view)
        else:
            await ctx_or_interaction.send(embed=pages[0], view=view)
    
    # Helper for checking cooldowns on slash commands
    def is_on_cooldown(self, interaction, weather=False):
        cd_mapping = self._cd_weather if weather else self._cd
        bucket = cd_mapping.get_bucket(interaction)
        retry_after = bucket.update_rate_limit()
        if retry_after:
            return True, retry_after
        return False, 0
    
    # Slash command group for all search commands
    search_group = app_commands.Group(name="search", description="Search for information online")
    
    # Google Search Commands
    @commands.command(name="google", aliases=["g"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def google(self, ctx, *, query: str):
        """Search Google for information"""
        await self._google_search(ctx, query)
    
    @search_group.command(name="google", description="Search Google for information")
    async def slash_google(self, interaction: discord.Interaction, query: str):
        """Slash command for Google search"""
        on_cd, retry_after = self.is_on_cooldown(interaction)
        if on_cd:
            await interaction.response.send_message(
                f"This command is on cooldown. Try again in {retry_after:.2f} seconds.", 
                ephemeral=True
            )
            return
        
        await interaction.response.defer()
        await self._google_search(interaction, query)
    
    async def _google_search(self, ctx_or_interaction, query: str):
        """Core Google search functionality for both command types"""
        is_interaction = isinstance(ctx_or_interaction, discord.Interaction)
        
        if not self.google_api_key or not self.google_cx:
            if is_interaction:
                await ctx_or_interaction.followup.send("⚠️ Google search is not configured. Please set up API keys.")
            else:
                await ctx_or_interaction.send("⚠️ Google search is not configured. Please set up API keys.")
            return
        
        # URL encode the query
        encoded_query = urllib.parse.quote(query)
        
        # Construct the API URL
        url = f"https://www.googleapis.com/customsearch/v1?key={self.google_api_key}&cx={self.google_cx}&q={encoded_query}"
        
        # Make the request
        result = await self.make_request(url)
        
        if "error" in result:
            if is_interaction:
                await ctx_or_interaction.followup.send(f"❌ Error: {result['error']}")
            else:
                await ctx_or_interaction.send(f"❌ Error: {result['error']}")
            return
        
        # Check if there are search results
        if "items" not in result or not result["items"]:
            if is_interaction:
                await ctx_or_interaction.followup.send(f"No results found for '{query}'")
            else:
                await ctx_or_interaction.send(f"No results found for '{query}'")
            return
        
        # Format the results into an embed
        items = result["items"][:10]  # Limit to 10 results
        
        def format_results(items):
            return "\n\n".join([
                f"**[{item.get('title', 'No Title')}]({item.get('link', '#')})**\n"
                f"{item.get('snippet', 'No description available')}"
                for item in items
            ])
        
        pages = self.create_embed_pages(
            items, 
            f"🔍 Google Search Results for '{query}'", 
            format_results
        )
        
        await self.send_paginated_results(ctx_or_interaction, pages)
    
    # YouTube Search Commands
    @commands.command(name="youtube", aliases=["yt"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def youtube(self, ctx, *, query: str):
        """Search YouTube for videos"""
        await self._youtube_search(ctx, query)
    
    @search_group.command(name="youtube", description="Search YouTube for videos")
    async def slash_youtube(self, interaction: discord.Interaction, query: str):
        """Slash command for YouTube search"""
        on_cd, retry_after = self.is_on_cooldown(interaction)
        if on_cd:
            await interaction.response.send_message(
                f"This command is on cooldown. Try again in {retry_after:.2f} seconds.", 
                ephemeral=True
            )
            return
        
        await interaction.response.defer()
        await self._youtube_search(interaction, query)
    
    async def _youtube_search(self, ctx_or_interaction, query: str):
        """Core YouTube search functionality for both command types"""
        is_interaction = isinstance(ctx_or_interaction, discord.Interaction)
        
        if not self.youtube_api_key:
            if is_interaction:
                await ctx_or_interaction.followup.send("⚠️ YouTube search is not configured. Please set up API keys.")
            else:
                await ctx_or_interaction.send("⚠️ YouTube search is not configured. Please set up API keys.")
            return
        
        # URL encode the query
        encoded_query = urllib.parse.quote(query)
        
        # Construct the API URL
        url = f"https://www.googleapis.com/youtube/v3/search?key={self.youtube_api_key}&part=snippet&type=video&q={encoded_query}&maxResults=10"
        
        # Make the request
        result = await self.make_request(url)
        
        if "error" in result:
            if is_interaction:
                await ctx_or_interaction.followup.send(f"❌ Error: {result['error']}")
            else:
                await ctx_or_interaction.send(f"❌ Error: {result['error']}")
            return
        
        # Check if there are search results
        if "items" not in result or not result["items"]:
            if is_interaction:
                await ctx_or_interaction.followup.send(f"No YouTube videos found for '{query}'")
            else:
                await ctx_or_interaction.send(f"No YouTube videos found for '{query}'")
            return
        
        # Format the results into an embed
        items = result["items"]
        
        def format_results(items):
            return "\n\n".join([
                f"**[{item['snippet'].get('title', 'No Title')}](https://www.youtube.com/watch?v={item['id']['videoId']})**\n"
                f"👤 {item['snippet'].get('channelTitle', 'Unknown channel')} | "
                f"📅 {item['snippet'].get('publishedAt', 'Unknown date')[:10]}\n"
                f"{item['snippet'].get('description', 'No description available')}"
                for item in items
            ])
        
        pages = self.create_embed_pages(
            items, 
            f"📺 YouTube Search Results for '{query}'", 
            format_results,
            color=0xFF0000  # YouTube red
        )
        
        await self.send_paginated_results(ctx_or_interaction, pages)
    
    # Wikipedia Search Commands
    @commands.command(name="wikipedia", aliases=["wiki"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def wikipedia(self, ctx, *, query: str):
        """Search Wikipedia for information"""
        await self._wikipedia_search(ctx, query)
    
    @search_group.command(name="wikipedia", description="Search Wikipedia for articles")
    async def slash_wikipedia(self, interaction: discord.Interaction, query: str):
        """Slash command for Wikipedia search"""
        on_cd, retry_after = self.is_on_cooldown(interaction)
        if on_cd:
            await interaction.response.send_message(
                f"This command is on cooldown. Try again in {retry_after:.2f} seconds.", 
                ephemeral=True
            )
            return
        
        await interaction.response.defer()
        await self._wikipedia_search(interaction, query)
    
    async def _wikipedia_search(self, ctx_or_interaction, query: str):
        """Core Wikipedia search functionality for both command types"""
        is_interaction = isinstance(ctx_or_interaction, discord.Interaction)
        
        # URL encode the query
        encoded_query = urllib.parse.quote(query)
        
        # First search for articles
        search_url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={encoded_query}&format=json"
        
        search_result = await self.make_request(search_url)
        
        if "error" in search_result:
            if is_interaction:
                await ctx_or_interaction.followup.send(f"❌ Error: {search_result['error']}")
            else:
                await ctx_or_interaction.send(f"❌ Error: {search_result['error']}")
            return
        
        # Check if there are search results
        if "query" not in search_result or "search" not in search_result["query"] or not search_result["query"]["search"]:
            if is_interaction:
                await ctx_or_interaction.followup.send(f"No Wikipedia articles found for '{query}'")
            else:
                await ctx_or_interaction.send(f"No Wikipedia articles found for '{query}'")
            return
        
        # Format multiple results with summaries
        search_results = search_result["query"]["search"][:7]  # Top 7 results
        
        # Get summary for each result and create pages
        all_pages = []
        
        for result in search_results:
            page_id = result["pageid"]
            
            # Get the full content of the article
            content_url = f"https://en.wikipedia.org/w/api.php?action=query&prop=extracts&exintro&explaintext&pageids={page_id}&format=json"
            
            # Make the request
            content_result = await self.make_request(content_url)
            
            if "error" in content_result or "query" not in content_result:
                continue
            
            # Extract the article content
            try:
                page = content_result["query"]["pages"][str(page_id)]
                title = page["title"]
                extract = page["extract"]
                
                # Truncate if too long
                if len(extract) > 2000:
                    extract = extract[:1997] + "..."
                
                # Create embed
                embed = discord.Embed(
                    title=title,
                    url=f"https://en.wikipedia.org/?curid={page_id}",
                    description=extract,
                    color=0x3a9efa
                )
                
                # Add search query context
                embed.set_author(name=f"Wikipedia Search: {query}")
                
                # Add a thumbnail if available through a different API
                embed.set_thumbnail(url=f"https://en.wikipedia.org/static/images/project-logos/enwiki.png")
                
                embed.set_footer(text=f"Source: Wikipedia • Page {len(all_pages) + 1}/{len(search_results)}")
                
                all_pages.append(embed)
                
            except Exception as e:
                continue
        
        if not all_pages:
            if is_interaction:
                await ctx_or_interaction.followup.send(f"Failed to retrieve Wikipedia articles for '{query}'")
            else:
                await ctx_or_interaction.send(f"Failed to retrieve Wikipedia articles for '{query}'")
            return
        
        # Send the paginated results
        author_id = ctx_or_interaction.user.id if is_interaction else ctx_or_interaction.author.id
        view = PaginationView(all_pages, author_id)
        
        if is_interaction:
            await ctx_or_interaction.followup.send(embed=all_pages[0], view=view)
        else:
            await ctx_or_interaction.send(embed=all_pages[0], view=view)
    
    # Urban Dictionary Commands
    @commands.command(name="urban", aliases=["ud"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def urban_dictionary(self, ctx, *, query: str):
        """Look up a term on Urban Dictionary"""
        await self._urban_search(ctx, query)
    
    @search_group.command(name="urban", description="Look up a term on Urban Dictionary (NSFW channels only)")
    async def slash_urban(self, interaction: discord.Interaction, query: str):
        """Slash command for Urban Dictionary search"""
        on_cd, retry_after = self.is_on_cooldown(interaction)
        if on_cd:
            await interaction.response.send_message(
                f"This command is on cooldown. Try again in {retry_after:.2f} seconds.", 
                ephemeral=True
            )
            return
        
        await interaction.response.defer()
        await self._urban_search(interaction, query)
    
    async def _urban_search(self, ctx_or_interaction, query: str):
        """Core Urban Dictionary search functionality for both command types"""
        is_interaction = isinstance(ctx_or_interaction, discord.Interaction)
        
        # Check if the channel is NSFW (Urban Dictionary can have mature content)
        channel = ctx_or_interaction.channel
        if not isinstance(channel, discord.DMChannel) and not channel.is_nsfw():
            if is_interaction:
                await ctx_or_interaction.followup.send("⚠️ This command can only be used in NSFW channels due to potentially mature content.")
            else:
                await ctx_or_interaction.send("⚠️ This command can only be used in NSFW channels due to potentially mature content.")
            return
        
        # URL encode the query
        encoded_query = urllib.parse.quote(query)
        
        # Construct the API URL
        url = f"https://api.urbandictionary.com/v0/define?term={encoded_query}"
        
        # Make the request
        result = await self.make_request(url)
        
        if "error" in result:
            if is_interaction:
                await ctx_or_interaction.followup.send(f"❌ Error: {result['error']}")
            else:
                await ctx_or_interaction.send(f"❌ Error: {result['error']}")
            return
        
        # Check if there are definitions
        if "list" not in result or not result["list"]:
            if is_interaction:
                await ctx_or_interaction.followup.send(f"No Urban Dictionary definitions found for '{query}'")
            else:
                await ctx_or_interaction.send(f"No Urban Dictionary definitions found for '{query}'")
            return
        
        # Format the results into an embed
        definitions = result["list"]
        
        def format_results(defs):
            return "\n\n".join([
                f"**Definition {i+1}:**\n"
                f"{self.clean_definition(d['definition'])}\n\n"
                f"**Example:**\n"
                f"{self.clean_definition(d['example'])}\n\n"
                f"👍 {d['thumbs_up']} | 👎 {d['thumbs_down']}"
                for i, d in enumerate(defs)
            ])
        
        pages = self.create_embed_pages(
            definitions, 
            f"📔 Urban Dictionary: {query}", 
            format_results,
            color=0x1D2439  # Urban Dictionary color
        )
        
        # Add the URL to the term
        for page in pages:
            page.add_field(
                name="Link",
                value=f"[View on Urban Dictionary](https://www.urbandictionary.com/define.php?term={encoded_query})",
                inline=False
            )
        
        await self.send_paginated_results(ctx_or_interaction, pages)
    
    def clean_definition(self, text: str) -> str:
        """Clean up Urban Dictionary formatting"""
        # Replace [bracketed] terms with italicized text
        text = re.sub(r'\[(.*?)\]', r'*\1*', text)
        
        # Truncate if too long
        if len(text) > 1000:
            text = text[:997] + "..."
            
        return text
    
    # GitHub Search Commands
    @commands.command(name="github", aliases=["gh"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def github(self, ctx, *, query: str):
        """Search GitHub repositories"""
        await self._github_search(ctx, query)
    
    @search_group.command(name="github", description="Search GitHub for repositories")
    async def slash_github(self, interaction: discord.Interaction, query: str):
        """Slash command for GitHub search"""
        on_cd, retry_after = self.is_on_cooldown(interaction)
        if on_cd:
            await interaction.response.send_message(
                f"This command is on cooldown. Try again in {retry_after:.2f} seconds.", 
                ephemeral=True
            )
            return
        
        await interaction.response.defer()
        await self._github_search(interaction, query)
    
    async def _github_search(self, ctx_or_interaction, query: str):
        """Core GitHub search functionality for both command types"""
        is_interaction = isinstance(ctx_or_interaction, discord.Interaction)
        
        # URL encode the query
        encoded_query = urllib.parse.quote(query)
        
        # Construct the API URL
        url = f"https://api.github.com/search/repositories?q={encoded_query}&sort=stars&order=desc"
        
        # Set up headers
        headers = {}
        if self.github_token:
            headers["Authorization"] = f"token {self.github_token}"
        
        # Make the request
        result = await self.make_request(url, headers)
        
        if "error" in result:
            if is_interaction:
                await ctx_or_interaction.followup.send(f"❌ Error: {result['error']}")
            else:
                await ctx_or_interaction.send(f"❌ Error: {result['error']}")
            return
        
        # Check if there are search results
        if "items" not in result or not result["items"]:
            if is_interaction:
                await ctx_or_interaction.followup.send(f"No GitHub repositories found for '{query}'")
            else:
                await ctx_or_interaction.send(f"No GitHub repositories found for '{query}'")
            return
        
        # Format the results into an embed
        repos = result["items"][:10]  # Limit to 10 results
        
        def format_results(repos):
            return "\n\n".join([
                f"**[{repo['full_name']}]({repo['html_url']})**\n"
                f"{repo.get('description', 'No description available')}\n"
                f"⭐ {repo['stargazers_count']} | 🍴 {repo['forks_count']} | "
                f"🔤 {repo['language'] or 'Unknown'} | "
                f"📅 Updated: {repo['updated_at'][:10]}"
                for repo in repos
            ])
        
        pages = self.create_embed_pages(
            repos, 
            f"📂 GitHub Search Results for '{query}'", 
            format_results,
            color=0x333333  # GitHub dark color
        )
        
        await self.send_paginated_results(ctx_or_interaction, pages)
    
    # Weather Commands
    @commands.command(name="weather", aliases=["wx"])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def weather(self, ctx, *, location: str):
        """Check the current weather for a location"""
        await self._weather_search(ctx, location)
    
    @search_group.command(name="weather", description="Get current weather information for a location")
    async def slash_weather(self, interaction: discord.Interaction, location: str):
        """Slash command for weather search"""
        on_cd, retry_after = self.is_on_cooldown(interaction, weather=True)
        if on_cd:
            await interaction.response.send_message(
                f"This command is on cooldown. Try again in {retry_after:.2f} seconds.", 
                ephemeral=True
            )
            return
        
        await interaction.response.defer()
        await self._weather_search(interaction, location)
    
    async def _weather_search(self, ctx_or_interaction, location: str):
        """Core weather search functionality for both command types"""
        is_interaction = isinstance(ctx_or_interaction, discord.Interaction)
        
        # Check if API key is configured
        if not self.openweather_api_key:
            error_embed = discord.Embed(
                title="⚠️ Weather Service Unavailable",
                description="The weather search feature is not configured. Please set up the OpenWeather API key.",
                color=0xFF5733  # Warning color
            )
            if is_interaction:
                await ctx_or_interaction.followup.send(embed=error_embed)
            else:
                await ctx_or_interaction.send(embed=error_embed)
            return
        
        # URL encode the location
        encoded_location = urllib.parse.quote(location)
        
        # Construct the API URL
        url = f"http://api.openweathermap.org/data/2.5/weather?q={encoded_location}&appid={self.openweather_api_key}&units=metric"
        
        try:
            # Make the request
            result = await self.make_request(url)
            
            # Handle API errors
            if "error" in result:
                error_embed = discord.Embed(
                    title="❌ Weather Search Error",
                    description=f"Error fetching weather data: {result['error']}",
                    color=0xFF0000  # Red color for errors
                )
                if is_interaction:
                    await ctx_or_interaction.followup.send(embed=error_embed)
                else:
                    await ctx_or_interaction.send(embed=error_embed)
                return
            
            # Check if the request was successful
            if result.get("cod") != 200:
                error_message = result.get('message', 'Unknown error')
                error_embed = discord.Embed(
                    title="❌ Weather Search Error",
                    description=f"Error from weather service: {error_message}",
                    color=0xFF0000
                )
                error_embed.add_field(
                    name="Troubleshooting",
                    value=f"• Check if '{location}' is a valid location\n• Try with city name and country code (e.g., 'London, UK')\n• Check if the OpenWeather service is currently available",
                    inline=False
                )
                if is_interaction:
                    await ctx_or_interaction.followup.send(embed=error_embed)
                else:
                    await ctx_or_interaction.send(embed=error_embed)
                return
            
            # Extract weather information
            city_name = result["name"]
            country = result["sys"]["country"]
            
            temp = result["main"]["temp"]
            temp_feels = result["main"]["feels_like"]
            humidity = result["main"]["humidity"]
            wind_speed = result["wind"]["speed"]
            pressure = result["main"]["pressure"]
            
            weather_main = result["weather"][0]["main"]
            weather_description = result["weather"][0]["description"].capitalize()
            weather_icon = result["weather"][0]["icon"]
            
            # Get sunrise and sunset times
            sunrise = datetime.datetime.fromtimestamp(result["sys"]["sunrise"])
            sunset = datetime.datetime.fromtimestamp(result["sys"]["sunset"])
            
            # Get the corresponding weather emoji
            weather_emojis = {
                "Clear": "☀️",
                "Clouds": "☁️",
                "Rain": "🌧️",
                "Drizzle": "🌦️",
                "Thunderstorm": "⛈️",
                "Snow": "❄️",
                "Mist": "🌫️",
                "Fog": "🌫️",
                "Haze": "🌫️",
                "Dust": "🌫️",
                "Smoke": "🌫️",
                "Tornado": "🌪️"
            }
            
            weather_emoji = weather_emojis.get(weather_main, "🌡️")
            
            # Create the embed
            embed = discord.Embed(
                title=f"Weather for {city_name}, {country}",
                description=f"{weather_emoji} **{weather_description}**",
                color=0x3a9efa,
                timestamp=datetime.datetime.now()
            )
            
            # Add weather info fields
            embed.add_field(name="Temperature", value=f"🌡️ {temp}°C (Feels like: {temp_feels}°C)", inline=False)
            embed.add_field(name="Humidity", value=f"💧 {humidity}%", inline=True)
            embed.add_field(name="Wind Speed", value=f"💨 {wind_speed} m/s", inline=True)
            embed.add_field(name="Pressure", value=f"📊 {pressure} hPa", inline=True)
            embed.add_field(name="Sunrise", value=f"🌅 {sunrise.strftime('%H:%M')}", inline=True)
