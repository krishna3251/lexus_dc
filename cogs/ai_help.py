import discord
from discord.ext import commands
from discord import app_commands
import os
import logging
import aiohttp
import urllib.parse
import asyncio
from datetime import datetime
import json
import random
import pytz
from io import BytesIO
import matplotlib.pyplot as plt
import matplotlib as mpl
from PIL import Image, ImageDraw, ImageFont
import base64

# Futuristic enhanced color scheme
COLORS = {
    "primary": discord.Color.from_rgb(114, 137, 218),  # Discord blurple
    "secondary": discord.Color.from_rgb(88, 101, 242),  # New Discord blurple
    "success": discord.Color.from_rgb(87, 242, 135),   # Neon green
    "warning": discord.Color.from_rgb(255, 149, 0),    # Cyberpunk orange
    "error": discord.Color.from_rgb(255, 89, 89),      # Neon red
    "info": discord.Color.from_rgb(59, 165, 255),      # Holographic blue
    "tech": discord.Color.from_rgb(32, 34, 37),        # Discord dark
    "cyber": discord.Color.from_rgb(0, 255, 240),      # Cyberpunk cyan
    "future": discord.Color.from_rgb(170, 0, 255),     # Futuristic purple
    "neon": discord.Color.from_rgb(255, 0, 127),       # Neon pink
    "matrix": discord.Color.from_rgb(0, 255, 65)       # Matrix green
}

# Weather condition icons mapping (emoji representation)
WEATHER_ICONS = {
    "clear": "☀️",
    "sunny": "☀️",
    "partly cloudy": "⛅",
    "cloudy": "☁️",
    "overcast": "☁️",
    "mist": "🌫️",
    "fog": "🌫️",
    "light rain": "🌦️",
    "rain": "🌧️",
    "heavy rain": "⛈️",
    "thunderstorm": "⛈️",
    "snow": "❄️",
    "sleet": "🌨️",
    "hail": "🌨️",
    "windy": "💨",
    "tornado": "🌪️",
    "hurricane": "🌀"
}

# ASCII art for futuristic flair
ASCII_ART = {
    "search": """
╔═══════════════════════════╗
║  █▀▀ █▀█ █▀█ █▀▀ █░░ █▀▀  ║
║  █▄█ █▄█ █▄█ █▄█ █▄▄ ██▄  ║
╚═══════════════════════════╝
""",
    "weather": """
╔═══════════════════════════╗
║  █░█░█ █▀▀ ▄▀█ ▀█▀ █▀█ █▀▀ █▀█  ║
║  ▀▄▀▄▀ ██▄ █▀█ ░█░ █▀▄ ██▄ █▀▄  ║
╚═══════════════════════════╝
""",
    "bot": """
╔═══════════════════════════╗
║  █░░ █▀▀ ▀▄▀ █░█ █▀  ║
║  █▄▄ ██▄ █░█ █▄█ ▄█  ║
╚═══════════════════════════╝
"""
}

class Utilities(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.weather_api_key = os.getenv("WEATHER_API_KEY", "")
        self.timezone_cache = {}
        self.timezone_expire_time = 86400  # 24 hours in seconds
        
        # Setup matplotlib for futuristic plots
        plt.style.use('dark_background')
        mpl.rcParams['text.color'] = '#00ffff'
        mpl.rcParams['axes.labelcolor'] = '#00ffff'
        mpl.rcParams['xtick.color'] = '#00ffff'
        mpl.rcParams['ytick.color'] = '#00ffff'

    @commands.hybrid_command(name="google", description="🔍 Search Google with a futuristic flair")
    async def google(self, ctx, *, query: str = None):
        """Search Google with a futuristic interface"""
        if not query:
            embed = discord.Embed(
                title="🔍 NEURAL SEARCH INTERFACE",
                description="Please provide a search query to access the global information network.",
                color=COLORS["cyber"]
            )
            embed.add_field(
                name="SYNTAX",
                value="```lx google your search query```",
                inline=False
            )
            embed.set_footer(text=f"USER: {ctx.author} • TIME: {datetime.now().strftime('%H:%M:%S')}")
            await ctx.send(embed=embed)
            return

        # Show typing indicator while generating
        async with ctx.typing():
            try:
                # URL encode the query to handle special characters
                encoded_query = urllib.parse.quote_plus(query)
                search_url = f"https://www.google.com/search?q={encoded_query}"
                
                # Create futuristic embed
                embed = discord.Embed(
                    title="🔍 NEURAL NETWORK SEARCH RESULTS",
                    description=f"Accessing global information network for: `{query}`",
                    color=COLORS["cyber"],
                    url=search_url
                )
                
                # Add the search query as a field
                embed.add_field(
                    name="QUERY PARAMETERS",
                    value=f"```{query}```",
                    inline=False
                )
                
                # Add the direct link
                embed.add_field(
                    name="ACCESS PORTAL",
                    value=f"[Click to view search results]({search_url})",
                    inline=False
                )
                
                # Add a random cyber tip
                tips = [
                    "Try using quotation marks for exact phrase matching.",
                    "Add 'site:example.com' to search within a specific website.",
                    "Use 'filetype:pdf' to search for specific file types.",
                    "Use '-' before words you want to exclude from results.",
                    "Add 'intitle:' to search for words in the page title."
                ]
                embed.add_field(
                    name="SEARCH PROTOCOL TIP",
                    value=f"```{random.choice(tips)}```",
                    inline=False
                )
                
                embed.set_footer(text=f"USER: {ctx.author} • TIMESTAMP: {datetime.now().strftime('%H:%M:%S')}")
                
                # Set a futuristic thumbnail
                embed.set_thumbnail(url="https://i.imgur.com/GMOth3v.png")  # Replace with a futuristic search icon
            
            except Exception as e:
                logging.error(f"Google search error: {e}")
                embed = discord.Embed(
                    title="🔍 SEARCH PROTOCOL ERROR",
                    description="Neural network connection failure. Please recalibrate your search parameters and try again.",
                    color=COLORS["error"]
                )
                embed.add_field(
                    name="ERROR TRACE",
                    value=f"```{str(e)[:1000]}```",
                    inline=False
                )
                embed.set_footer(text=f"USER: {ctx.author} • TIME: {datetime.now().strftime('%H:%M:%S')}")
        
        await ctx.send(embed=embed)

    @app_commands.command(name="google", description="🔍 Search Google with a futuristic interface")
    async def google_slash(self, interaction: discord.Interaction, query: str):
        """Slash command version of the Google search"""
        await interaction.response.defer()
        
        try:
            # URL encode the query to handle special characters
            encoded_query = urllib.parse.quote_plus(query)
            search_url = f"https://www.google.com/search?q={encoded_query}"
            
            # Create futuristic embed
            embed = discord.Embed(
                title="🔍 NEURAL NETWORK SEARCH RESULTS",
                description=f"Accessing global information network for: `{query}`",
                color=COLORS["cyber"],
                url=search_url
            )
            
            # Add the search query as a field
            embed.add_field(
                name="QUERY PARAMETERS",
                value=f"```{query}```",
                inline=False
            )
            
            # Add the direct link
            embed.add_field(
                name="ACCESS PORTAL",
                value=f"[Click to view search results]({search_url})",
                inline=False
            )
            
            # Add a random cyber tip
            tips = [
                "Try using quotation marks for exact phrase matching.",
                "Add 'site:example.com' to search within a specific website.",
                "Use 'filetype:pdf' to search for specific file types.",
                "Use '-' before words you want to exclude from results.",
                "Add 'intitle:' to search for words in the page title."
            ]
            embed.add_field(
                name="SEARCH PROTOCOL TIP",
                value=f"```{random.choice(tips)}```",
                inline=False
            )
            
            embed.set_footer(text=f"USER: {interaction.user} • TIMESTAMP: {datetime.now().strftime('%H:%M:%S')}")
            
            # Set a futuristic thumbnail
            embed.set_thumbnail(url="https://i.imgur.com/GMOth3v.png")  # Replace with a futuristic search icon
        
        except Exception as e:
            logging.error(f"Google search error: {e}")
            embed = discord.Embed(
                title="🔍 SEARCH PROTOCOL ERROR",
                description="Neural network connection failure. Please recalibrate your search parameters and try again.",
                color=COLORS["error"]
            )
            embed.add_field(
                name="ERROR TRACE",
                value=f"```{str(e)[:1000]}```",
                inline=False
            )
            embed.set_footer(text=f"USER: {interaction.user} • TIME: {datetime.now().strftime('%H:%M:%S')}")
        
        await interaction.followup.send(embed=embed)

    async def get_weather_data(self, location):
        """Fetch weather data from OpenWeatherMap API"""
        if not self.weather_api_key:
            return {"error": "Weather API key not configured"}
        
        try:
            base_url = "https://api.openweathermap.org/data/2.5/weather"
            forecast_url = "https://api.openweathermap.org/data/2.5/forecast"
            
            # Current weather
            params = {
                "q": location,
                "appid": self.weather_api_key,
                "units": "metric"  # Use metric units
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(base_url, params=params) as response:
                    if response.status != 200:
                        return {"error": f"API returned status code {response.status}"}
                    
                    current_data = await response.json()
                
                # 5-day forecast
                async with session.get(forecast_url, params=params) as response:
                    if response.status != 200:
                        return {"error": f"Forecast API returned status code {response.status}"}
                    
                    forecast_data = await response.json()
            
            return {
                "current": current_data,
                "forecast": forecast_data
            }
        
        except Exception as e:
            logging.error(f"Weather API error: {e}")
            return {"error": str(e)}

    async def create_weather_chart(self, forecast_data):
        """Create a futuristic weather chart image"""
        try:
            # Extract temperature data for the next 5 days (every 8 data points = 1 day)
            temps = []
            times = []
            dates = []
            
            for i, item in enumerate(forecast_data["list"][:40:8]):  # Get one reading per day
                temp = item["main"]["temp"]
                dt = datetime.fromtimestamp(item["dt"])
                temps.append(temp)
                times.append(dt.strftime("%a"))
                dates.append(dt.strftime("%m/%d"))
            
            # Create a futuristic plot
            fig, ax = plt.subplots(figsize=(10, 5), facecolor="#000000")
            
            # Plot with glow effect
            ax.plot(times, temps, color="#00ffff", linewidth=2, marker="o", markersize=8)
            ax.set_facecolor("#000011")
            
            # Add grid with cyber styling
            ax.grid(color="#003333", linestyle="--", linewidth=0.5, alpha=0.7)
            
            # Add labels
            ax.set_title("5-DAY TEMPERATURE FORECAST", color="#00ffff", fontsize=16, fontweight="bold")
            ax.set_ylabel("Temperature (°C)", color="#00ffff")
            
            # Add temperature values above points
            for i, temp in enumerate(temps):
                ax.annotate(f"{temp:.1f}°C", (i, temp), 
                           textcoords="offset points", 
                           xytext=(0, 10), 
                           ha="center",
                           color="#00ffff",
                           fontweight="bold")
            
            # Add date below day name
            for i, (day, date) in enumerate(zip(times, dates)):
                ax.annotate(date, (i, min(temps) - 2),
                           ha="center",
                           color="#00ffff")
            
            # Set y-axis limits with some padding
            ax.set_ylim(min(temps) - 5, max(temps) + 5)
            
            # Remove spines
            for spine in ax.spines.values():
                spine.set_color("#00ffff")
                spine.set_linewidth(1)
            
            # Save figure to bytes
            buf = BytesIO()
            plt.tight_layout()
            fig.savefig(buf, format="png", dpi=100, transparent=True)
            buf.seek(0)
            plt.close(fig)
            
            return buf
    
    @commands.hybrid_command(name="weather", description="🌡️ Get a futuristic weather forecast for a location")
    async def weather(self, ctx, *, location: str = None):
        """Get a beautiful futuristic weather forecast for a location"""
        if not location:
            embed = discord.Embed(
                title="🌡️ METEOROLOGICAL DATA SYSTEM",
                description="Please specify a location to analyze atmospheric conditions.",
                color=COLORS["future"]
            )
            embed.add_field(
                name="SYNTAX",
                value="```lx weather New York```",
                inline=False
            )
            embed.set_footer(text=f"USER: {ctx.author} • TIME: {datetime.now().strftime('%H:%M:%S')}")
            await ctx.send(embed=embed)
            return
        
        # Show typing indicator while fetching data
        async with ctx.typing():
            weather_data = await self.get_weather_data(location)
            
            if "error" in weather_data:
                embed = discord.Embed(
                    title="⚠️ ATMOSPHERIC SENSOR MALFUNCTION",
                    description=f"Could not retrieve meteorological data for `{location}`.",
                    color=COLORS["error"]
                )
                embed.add_field(
                    name="ERROR LOG",
                    value=f"```{weather_data['error']}```",
                    inline=False
                )
                embed.set_footer(text=f"USER: {ctx.author} • TIME: {datetime.now().strftime('%H:%M:%S')}")
                await ctx.send(embed=embed)
                return
            
            # Current weather data
            current = weather_data["current"]
            forecast = weather_data["forecast"]
            
            # Get location details
            city = current["name"]
            country = current["sys"]["country"]
            
            # Get weather details
            temp = current["main"]["temp"]
            feels_like = current["main"]["feels_like"]
            humidity = current["main"]["humidity"]
            pressure = current["main"]["pressure"]
            wind_speed = current["wind"]["speed"]
            weather_desc = current["weather"][0]["description"]
            weather_icon_id = current["weather"][0]["icon"]
            
            # Get appropriate emoji for weather condition
            weather_emoji = "🌐"  # Default
            for key, emoji in WEATHER_ICONS.items():
                if key in weather_desc.lower():
                    weather_emoji = emoji
                    break
            
            # Create chart image
            chart_image = await self.create_weather_chart(forecast)
            
            # Create a futuristic embed
            embed = discord.Embed(
                title=f"{weather_emoji} ATMOSPHERIC ANALYSIS: {city.upper()}, {country}",
                description=f"```css\n[{weather_desc.title()}] • Current Temperature: {temp}°C • Feels Like: {feels_like}°C```",
                color=COLORS["future"],
                timestamp=datetime.utcnow()
            )
            
            # Add current conditions
            embed.add_field(
                name="🌡️ THERMAL READINGS",
                value=f"**Temperature:** {temp}°C\n**Feels Like:** {feels_like}°C",
                inline=True
            )
            
            embed.add_field(
                name="💧 HUMIDITY ANALYSIS",
                value=f"**Humidity:** {humidity}%\n**Pressure:** {pressure} hPa",
                inline=True
            )
            
            embed.add_field(
                name="💨 WIND PARAMETERS",
                value=f"**Speed:** {wind_speed} m/s\n**Direction:** {current['wind'].get('deg', 'N/A')}°",
                inline=True
            )
            
            # Add 5-day forecast summary
            forecast_text = ""
            for i, item in enumerate(forecast["list"][:40:8]):  # Get one reading per day (every 8 data points = 1 day)
                dt = datetime.fromtimestamp(item["dt"])
                temp = item["main"]["temp"]
                weather = item["weather"][0]["description"].title()
                
                # Get appropriate emoji
                day_emoji = "🌐"
                for key, emoji in WEATHER_ICONS.items():
                    if key in weather.lower():
                        day_emoji = emoji
                        break
                
                forecast_text += f"**{dt.strftime('%A')}:** {day_emoji} {temp}°C • {weather}\n"
            
            embed.add_field(
                name="📊 5-DAY FORECAST PROJECTION",
                value=forecast_text,
                inline=False
            )
            
            # Add sunrise/sunset
            sunrise = datetime.fromtimestamp(current["sys"]["sunrise"])
            sunset = datetime.fromtimestamp(current["sys"]["sunset"])
            
            embed.add_field(
                name="☀️ SOLAR CYCLE DATA",
                value=f"**Sunrise:** {sunrise.strftime('%H:%M')}\n**Sunset:** {sunset.strftime('%H:%M')}",
                inline=True
            )
            
            # Add local time
            local_time = datetime.now().strftime('%H:%M:%S')
            embed.add_field(
                name="⏰ TEMPORAL COORDINATES",
                value=f"**Local Time:** {local_time}",
                inline=True
            )
            
            # Add coordinates
            lat = current["coord"]["lat"]
            lon = current["coord"]["lon"]
            embed.add_field(
                name="📍 GEOSPATIAL COORDINATES",
                value=f"**Latitude:** {lat}\n**Longitude:** {lon}",
                inline=True
            )
            
            # Set footer
            embed.set_footer(text=f"Data requested by {ctx.author} • Refresh data with 'lx weather {location}'")
            
            # Set thumbnail based on weather condition
            weather_icon_url = f"https://openweathermap.org/img/wn/{weather_icon_id}@2x.png"
            embed.set_thumbnail(url=weather_icon_url)
            
            # Create a file object from the chart image
            chart_file = discord.File(chart_image, filename="forecast_chart.png")
            embed.set_image(url="attachment://forecast_chart.png")
        
        await ctx.send(embed=embed, file=chart_file)
    
    @app_commands.command(name="weather", description="🌡️ Get a futuristic weather forecast for a location")
    async def weather_slash(self, interaction: discord.Interaction, location: str):
        """Slash command version of the weather forecast"""
        await interaction.response.defer()
        
        weather_data = await self.get_weather_data(location)
        
        if "error" in weather_data:
            embed = discord.Embed(
                title="⚠️ ATMOSPHERIC SENSOR MALFUNCTION",
                description=f"Could not retrieve meteorological data for `{location}`.",
                color=COLORS["error"]
            )
            embed.add_field(
                name="ERROR LOG",
                value=f"```{weather_data['error']}```",
                inline=False
            )
            embed.set_footer(text=f"USER: {interaction.user} • TIME: {datetime.now().strftime('%H:%M:%S')}")
            await interaction.followup.send(embed=embed)
            return
        
        # Current weather data
        current = weather_data["current"]
        forecast = weather_data["forecast"]
        
        # Get location details
        city = current["name"]
        country = current["sys"]["country"]
        
        # Get weather details
        temp = current["main"]["temp"]
        feels_like = current["main"]["feels_like"]
        humidity = current["main"]["humidity"]
        pressure = current["main"]["pressure"]
        wind_speed = current["wind"]["speed"]
        weather_desc = current["weather"][0]["description"]
        weather_icon_id = current["weather"][0]["icon"]
        
        # Get appropriate emoji for weather condition
        weather_emoji = "🌐"  # Default
        for key, emoji in WEATHER_ICONS.items():
            if key in weather_desc.lower():
                weather_emoji = emoji
                break
        
        # Create chart image
        chart_image = await self.create_weather_chart(forecast)
        
        # Create a futuristic embed
        embed = discord.Embed(
            title=f"{weather_emoji} ATMOSPHERIC ANALYSIS: {city.upper()}, {country}",
            description=f"```css\n[{weather_desc.title()}] • Current Temperature: {temp}°C • Feels Like: {feels_like}°C```",
            color=COLORS["future"],
            timestamp=datetime.utcnow()
        )
        
        # Add current conditions
        embed.add_field(
            name="🌡️ THERMAL READINGS",
            value=f"**Temperature:** {temp}°C\n**Feels Like:** {feels_like}°C",
            inline=True
        )
        
        embed.add_field(
            name="💧 HUMIDITY ANALYSIS",
            value=f"**Humidity:** {humidity}%\n**Pressure:** {pressure} hPa",
            inline=True
        )
        
        embed.add_field(
            name="💨 WIND PARAMETERS",
            value=f"**Speed:** {wind_speed} m/s\n**Direction:** {current['wind'].get('deg', 'N/A')}°",
            inline=True
        )
        
        # Add 5-day forecast summary
        forecast_text = ""
        for i, item in enumerate(forecast["list"][:40:8]):  # Get one reading per day (every 8 data points = 1 day)
            dt = datetime.fromtimestamp(item["dt"])
            temp = item["main"]["temp"]
            weather = item["weather"][0]["description"].title()
            
            # Get appropriate emoji
            day_emoji = "🌐"
            for key, emoji in WEATHER_ICONS.items():
                if key in weather.lower():
                    day_emoji = emoji
                    break
            
            forecast_text += f"**{dt.strftime('%A')}:** {day_emoji} {temp}°C • {weather}\n"
        
        embed.add_field(
            name="📊 5-DAY FORECAST PROJECTION",
            value=forecast_text,
            inline=False
        )
        
        # Add sunrise/sunset
        sunrise = datetime.fromtimestamp(current["sys"]["sunrise"])
        sunset = datetime.fromtimestamp(current["sys"]["sunset"])
        
        embed.add_field(
            name="☀️ SOLAR CYCLE DATA",
            value=f"**Sunrise:** {sunrise.strftime('%H:%M')}\n**Sunset:** {sunset.strftime('%H:%M')}",
            inline=True
        )
        
        # Add local time
        local_time = datetime.now().strftime('%H:%M:%S')
        embed.add_field(
            name="⏰ TEMPORAL COORDINATES",
            value=f"**Local Time:** {local_time}",
            inline=True
        )
        
        # Add coordinates
        lat = current["coord"]["lat"]
        lon = current["coord"]["lon"]
        embed.add_field(
            name="📍 GEOSPATIAL COORDINATES",
            value=f"**Latitude:** {lat}\n**Longitude:** {lon}",
            inline=True
        )
        
        # Set footer
        embed.set_footer(text=f"Data requested by {interaction.user} • Refresh data with '/weather {location}'")
        
        # Set thumbnail based on weather condition
        weather_icon_url = f"https://openweathermap.org/img/wn/{weather_icon_id}@2x.png"
        embed.set_thumbnail(url=weather_icon_url)
        
        # Create a file object from the chart image
        chart_file = discord.File(chart_image, filename="forecast_chart.png")
        embed.set_image(url="attachment://forecast_chart.png")
        
        await interaction.followup.send(embed=embed, file=chart_file)

async def setup(bot):
    await bot.add_cog(Utilities(bot))
    logging.info("🔧 Utilities cog has been added to the bot")
