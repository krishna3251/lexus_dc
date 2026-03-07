import os
import discord
import aiohttp
import json
import datetime
from discord.ext import commands
from discord import app_commands
from discord.ui import Button, View
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
HELP_LOGGER_WEBHOOK = os.getenv("HELP_LOGGER_WEBHOOK")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Constants
WEATHER_ICONS = {
    "01d": "☀️", "01n": "🌙",  # clear sky
    "02d": "⛅", "02n": "☁️",  # few clouds
    "03d": "☁️", "03n": "☁️",  # scattered clouds
    "04d": "☁️", "04n": "☁️",  # broken clouds
    "09d": "🌧️", "09n": "🌧️",  # shower rain
    "10d": "🌦️", "10n": "🌧️",  # rain
    "11d": "⛈️", "11n": "⛈️",  # thunderstorm
    "13d": "❄️", "13n": "❄️",  # snow
    "50d": "🌫️", "50n": "🌫️",  # mist
}

class YoutubeView(View):
    def __init__(self, videos: List[Dict[str, Any]], author_id: int):
        super().__init__(timeout=60)
        self.videos = videos
        self.current_index = 0
        self.author_id = author_id
        
    @discord.ui.button(label="Previous", style=discord.ButtonStyle.gray, emoji="⬅️", disabled=True)
    async def previous_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("You cannot use these controls.", ephemeral=True)
            return
            
        self.current_index -= 1
        
        # Update button states
        self.previous_button.disabled = self.current_index == 0
        self.next_button.disabled = self.current_index == len(self.videos) - 1
        
        await interaction.response.edit_message(
            embed=self.create_embed(),
            view=self
        )
    
    @discord.ui.button(label="Next", style=discord.ButtonStyle.gray, emoji="➡️")
    async def next_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("You cannot use these controls.", ephemeral=True)
            return
            
        self.current_index += 1
        
        # Update button states
        self.previous_button.disabled = self.current_index == 0
        self.next_button.disabled = self.current_index == len(self.videos) - 1
        
        await interaction.response.edit_message(
            embed=self.create_embed(),
            view=self
        )
    
    @discord.ui.button(label="Watch", style=discord.ButtonStyle.green, emoji="▶️")
    async def watch_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("You cannot use these controls.", ephemeral=True)
            return
            
        video = self.videos[self.current_index]
        video_url = f"https://www.youtube.com/watch?v={video['id']['videoId']}"
        
        await interaction.response.send_message(f"Enjoy watching: {video_url}", ephemeral=True)
    
    def create_embed(self) -> discord.Embed:
        video = self.videos[self.current_index]
        
        embed = discord.Embed(
            title=video["snippet"]["title"],
            url=f"https://www.youtube.com/watch?v={video['id']['videoId']}",
            description=video["snippet"]["description"],
            color=0xFF0000  # YouTube red
        )
        
        # Add thumbnail from YouTube
        if "thumbnails" in video["snippet"] and "high" in video["snippet"]["thumbnails"]:
            embed.set_image(url=video["snippet"]["thumbnails"]["high"]["url"])
        
        # Add video info
        embed.add_field(
            name="Channel", 
            value=video["snippet"]["channelTitle"], 
            inline=True
        )
        
        # Format the published date
        published_at = datetime.datetime.fromisoformat(video["snippet"]["publishedAt"].replace("Z", "+00:00"))
        embed.add_field(
            name="Published", 
            value=f"<t:{int(published_at.timestamp())}:R>", 
            inline=True
        )
        
        embed.set_footer(text=f"Result {self.current_index + 1}/{len(self.videos)}")
        
        return embed

class GoogleView(View):
    def __init__(self, results: List[Dict[str, Any]], author_id: int):
        super().__init__(timeout=60)
        self.results = results
        self.current_index = 0
        self.author_id = author_id
        
    @discord.ui.button(label="Previous", style=discord.ButtonStyle.gray, emoji="⬅️", disabled=True)
    async def previous_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("You cannot use these controls.", ephemeral=True)
            return
            
        self.current_index -= 1
        
        # Update button states
        self.previous_button.disabled = self.current_index == 0
        self.next_button.disabled = self.current_index == len(self.results) - 1
        
        await interaction.response.edit_message(
            embed=self.create_embed(),
            view=self
        )
    
    @discord.ui.button(label="Next", style=discord.ButtonStyle.gray, emoji="➡️")
    async def next_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("You cannot use these controls.", ephemeral=True)
            return
            
        self.current_index += 1
        
        # Update button states
        self.previous_button.disabled = self.current_index == 0
        self.next_button.disabled = self.current_index == len(self.results) - 1
        
        await interaction.response.edit_message(
            embed=self.create_embed(),
            view=self
        )
    
    @discord.ui.button(label="Visit", style=discord.ButtonStyle.url, emoji="🔗")
    async def visit_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("You cannot use these controls.", ephemeral=True)
            return
        
        # This doesn't actually get called for URL buttons - Discord handles them directly
        pass
    
    def create_embed(self) -> discord.Embed:
        result = self.results[self.current_index]
        
        embed = discord.Embed(
            title=result["title"],
            url=result["link"],
            description=result["snippet"],
            color=0x4285F4  # Google blue
        )
        
        # Add thumbnail if available
        if "pagemap" in result and "cse_thumbnail" in result["pagemap"]:
            embed.set_thumbnail(url=result["pagemap"]["cse_thumbnail"][0]["src"])
        
        embed.set_footer(text=f"Result {self.current_index + 1}/{len(self.results)}")
        
        return embed

class WeatherView(View):
    def __init__(self, weather_data: Dict[str, Any], forecast_data: Dict[str, Any], author_id: int):
        super().__init__(timeout=120)
        self.weather_data = weather_data
        self.forecast_data = forecast_data
        self.showing_current = True
        self.forecast_day = 0
        self.author_id = author_id
        
    @discord.ui.button(label="Current", style=discord.ButtonStyle.primary, disabled=True)
    async def current_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("You cannot use these controls.", ephemeral=True)
            return
            
        self.showing_current = True
        
        # Update button states
        self.current_button.disabled = True
        self.forecast_button.disabled = False
        self.previous_day_button.disabled = True
        self.next_day_button.disabled = True
        
        await interaction.response.edit_message(
            embed=self.create_embed(),
            view=self
        )
    
    @discord.ui.button(label="Forecast", style=discord.ButtonStyle.primary)
    async def forecast_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("You cannot use these controls.", ephemeral=True)
            return
            
        self.showing_current = False
        self.forecast_day = 0
        
        # Update button states
        self.current_button.disabled = False
        self.forecast_button.disabled = True
        self.previous_day_button.disabled = True
        self.next_day_button.disabled = False
        
        await interaction.response.edit_message(
            embed=self.create_embed(),
            view=self
        )
    
    @discord.ui.button(label="Previous Day", style=discord.ButtonStyle.gray, emoji="⬅️", disabled=True, row=1)
    async def previous_day_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("You cannot use these controls.", ephemeral=True)
            return
            
        self.forecast_day -= 1
        
        # Update button states
        self.previous_day_button.disabled = self.forecast_day == 0
        self.next_day_button.disabled = self.forecast_day == 4  # 5-day forecast (0-4)
        
        await interaction.response.edit_message(
            embed=self.create_embed(),
            view=self
        )
    
    @discord.ui.button(label="Next Day", style=discord.ButtonStyle.gray, emoji="➡️", disabled=True, row=1)
    async def next_day_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("You cannot use these controls.", ephemeral=True)
            return
            
        self.forecast_day += 1
        
        # Update button states
        self.previous_day_button.disabled = self.forecast_day == 0
        self.next_day_button.disabled = self.forecast_day == 4  # 5-day forecast (0-4)
        
        await interaction.response.edit_message(
            embed=self.create_embed(),
            view=self
        )
    
    def create_embed(self) -> discord.Embed:
        if self.showing_current:
            return self.create_current_weather_embed()
        else:
            return self.create_forecast_embed()
    
    def create_current_weather_embed(self) -> discord.Embed:
        weather = self.weather_data
        
        # Get weather icon
        weather_icon = WEATHER_ICONS.get(weather["weather"][0]["icon"], "🌡️")
        
        # Create embed
        embed = discord.Embed(
            title=f"{weather_icon} Weather in {weather['name']}, {weather['sys']['country']}",
            description=f"**{weather['weather'][0]['description'].capitalize()}**",
            color=0x00AAFF,
            timestamp=datetime.datetime.utcfromtimestamp(weather["dt"])
        )
        
        # Main weather info
        embed.add_field(
            name="Temperature", 
            value=f"🌡️ {weather['main']['temp']}°C / {(weather['main']['temp'] * 9/5) + 32:.1f}°F", 
            inline=True
        )
        embed.add_field(
            name="Feels Like", 
            value=f"🌡️ {weather['main']['feels_like']}°C / {(weather['main']['feels_like'] * 9/5) + 32:.1f}°F", 
            inline=True
        )
        embed.add_field(
            name="Humidity", 
            value=f"💧 {weather['main']['humidity']}%", 
            inline=True
        )
        
        # Additional info
        embed.add_field(
            name="Wind", 
            value=f"🌬️ {weather['wind']['speed']} m/s", 
            inline=True
        )
        embed.add_field(
            name="Pressure", 
            value=f"🔍 {weather['main']['pressure']} hPa", 
            inline=True
        )
        embed.add_field(
            name="Visibility", 
            value=f"👁️ {weather.get('visibility', 'N/A') / 1000:.1f} km", 
            inline=True
        )
        
        # Sunrise and sunset
        sunrise = datetime.datetime.utcfromtimestamp(weather['sys']['sunrise'])
        sunset = datetime.datetime.utcfromtimestamp(weather['sys']['sunset'])
        
        embed.add_field(
            name="Sunrise", 
            value=f"🌅 <t:{int(sunrise.timestamp())}:t>", 
            inline=True
        )
        embed.add_field(
            name="Sunset", 
            value=f"🌇 <t:{int(sunset.timestamp())}:t>", 
            inline=True
        )
        
        # Add weather icon as thumbnail
        embed.set_thumbnail(url=f"http://openweathermap.org/img/wn/{weather['weather'][0]['icon']}@2x.png")
        
        embed.set_footer(text="Current Weather • Data from OpenWeatherMap")
        
        return embed
    
    def create_forecast_embed(self) -> discord.Embed:
        daily_forecast = []
        current_day = None
        
        # Group forecast by day (OpenWeatherMap gives 3-hour forecasts)
        for item in self.forecast_data["list"]:
            date = datetime.datetime.utcfromtimestamp(item["dt"]).strftime("%Y-%m-%d")
            
            if date != current_day:
                current_day = date
                daily_forecast.append({
                    "date": date,
                    "forecasts": [item]
                })
            else:
                daily_forecast[-1]["forecasts"].append(item)
        
        # Get specific day forecast
        if self.forecast_day >= len(daily_forecast):
            self.forecast_day = len(daily_forecast) - 1
            
        day_data = daily_forecast[self.forecast_day]
        forecasts = day_data["forecasts"]
        
        # Get date in readable format
        date_obj = datetime.datetime.strptime(day_data["date"], "%Y-%m-%d")
        date_readable = date_obj.strftime("%A, %B %d")
        
        # Create embed
        embed = discord.Embed(
            title=f"Forecast for {self.forecast_data['city']['name']}, {self.forecast_data['city']['country']}",
            description=f"**{date_readable}**",
            color=0x00AAFF
        )
        
        # Add forecasts for the day
        for forecast in forecasts:
            time = datetime.datetime.utcfromtimestamp(forecast["dt"]).strftime("%H:%M")
            weather_desc = forecast["weather"][0]["description"].capitalize()
            temp = forecast["main"]["temp"]
            temp_f = (temp * 9/5) + 32
            weather_icon = WEATHER_ICONS.get(forecast["weather"][0]["icon"], "🌡️")
            
            embed.add_field(
                name=f"{weather_icon} {time}",
                value=f"{weather_desc}\n{temp:.1f}°C / {temp_f:.1f}°F\n💧 {forecast['main']['humidity']}% | 🌬️ {forecast['wind']['speed']} m/s",
                inline=True
            )
        
        # Add day indicator to footer
        embed.set_footer(text=f"5-Day Forecast • Day {self.forecast_day + 1}/5 • Data from OpenWeatherMap")
        
        return embed

class SearchFeatures(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = None
    
    async def cog_load(self):
        self.session = aiohttp.ClientSession()
        
    async def cog_unload(self):
        if self.session:
            await self.session.close()
    
    @commands.hybrid_command(
        name="weather",
        description="Get the current weather and forecast for a location"
    )
    @app_commands.describe(location="The city or location to get weather for")
    async def weather(self, ctx, *, location: str):
        # Log the command usage
        await self.log_command_usage(ctx, f"Weather command used for '{location}'")
        
        # Show typing indicator
        async with ctx.typing():
            try:
                # Get current weather
                current_weather_url = f"https://api.openweathermap.org/data/2.5/weather?q={location}&appid={OPENWEATHER_API_KEY}&units=metric"
                async with self.session.get(current_weather_url) as response:
                    if response.status != 200:
                        await ctx.reply(f"❌ Couldn't find weather data for '{location}'. Please check the spelling and try again.")
                        return
                    
                    current_weather = await response.json()
                
                # Get 5-day forecast
                forecast_url = f"https://api.openweathermap.org/data/2.5/forecast?q={location}&appid={OPENWEATHER_API_KEY}&units=metric"
                async with self.session.get(forecast_url) as response:
                    if response.status != 200:
                        await ctx.reply(f"❌ Couldn't find forecast data for '{location}'. Please check the spelling and try again.")
                        return
                    
                    forecast_data = await response.json()
                
                # Create view with buttons
                view = WeatherView(current_weather, forecast_data, ctx.author.id)
                
                # Send initial embed
                await ctx.reply(embed=view.create_embed(), view=view)
                
            except Exception as e:
                await ctx.reply(f"❌ An error occurred: {str(e)}")
                raise e
    
    @commands.hybrid_command(
        name="youtube",
        description="Search for videos on YouTube"
    )
    @app_commands.describe(query="The search term for YouTube videos")
    async def youtube(self, ctx, *, query: str):
        # Log the command usage
        await self.log_command_usage(ctx, f"YouTube search for '{query}'")
        
        # Show typing indicator
        async with ctx.typing():
            try:
                # Search YouTube API
                search_url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&maxResults=10&q={query}&type=video&key={YOUTUBE_API_KEY}"
                
                async with self.session.get(search_url) as response:
                    if response.status != 200:
                        await ctx.reply(f"❌ Failed to search YouTube. Status code: {response.status}")
                        return
                    
                    data = await response.json()
                
                # Check if we have results
                if not data.get("items"):
                    await ctx.reply(f"❌ No YouTube videos found for '{query}'.")
                    return
                
                # Create view with buttons
                view = YoutubeView(data["items"], ctx.author.id)
                
                # Send initial embed
                await ctx.reply(embed=view.create_embed(), view=view)
                
            except Exception as e:
                await ctx.reply(f"❌ An error occurred: {str(e)}")
                raise e
    
    @commands.hybrid_command(
        name="google",
        description="Search Google for information"
    )
    @app_commands.describe(query="The search term for Google")
    async def google(self, ctx, *, query: str):
        # Log the command usage
        await self.log_command_usage(ctx, f"Google search for '{query}'")
        
        # Show typing indicator
        async with ctx.typing():
            try:
                # Search Google API
                search_url = f"https://www.googleapis.com/customsearch/v1?q={query}&cx={GOOGLE_CSE_ID}&key={GOOGLE_API_KEY}"
                
                async with self.session.get(search_url) as response:
                    if response.status != 200:
                        await ctx.reply(f"❌ Failed to search Google. Status code: {response.status}")
                        return
                    
                    data = await response.json()
                
                # Check if we have results
                if not data.get("items"):
                    await ctx.reply(f"❌ No Google search results found for '{query}'.")
                    return
                
                # Create view with buttons
                view = GoogleView(data["items"], ctx.author.id)
                
                # Send initial embed
                await ctx.reply(embed=view.create_embed(), view=view)
                
            except Exception as e:
                await ctx.reply(f"❌ An error occurred: {str(e)}")
                raise e
                
    async def log_command_usage(self, ctx, message):
        """Log command usage to the specified webhook"""
        if not HELP_LOGGER_WEBHOOK:
            return
            
        try:
            webhook = discord.Webhook.from_url(HELP_LOGGER_WEBHOOK, session=self.session)
            
            embed = discord.Embed(
                title="Command Used",
                description=message,
                color=0x5865F2,
                timestamp=datetime.datetime.now()
            )
            
            embed.add_field(
                name="User", 
                value=f"{ctx.author} ({ctx.author.id})", 
                inline=True
            )
            
            embed.add_field(
                name="Channel", 
                value=f"{ctx.channel} ({ctx.channel.id})", 
                inline=True
            )
            
            if ctx.guild:
                embed.add_field(
                    name="Server", 
                    value=f"{ctx.guild.name} ({ctx.guild.id})", 
                    inline=True
                )
            
            await webhook.send(embed=embed)
        except Exception:
            # Silently fail if webhook logging doesn't work
            pass

async def setup(bot):
    await bot.add_cog(SearchFeatures(bot))
