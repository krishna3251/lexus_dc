# cogs/calendar.py

import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
import os
import logging
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
from dateutil.parser import parse as parse_date
from bson import ObjectId
import pytz
from typing import Optional, Dict, Any, List
import traceback

# Setup logging
log = logging.getLogger("calendar")
log.setLevel(logging.INFO)

# Constants
CALENDARIFIC_API = os.getenv("CALENDARIFIC_API")
MONGO_URI = os.getenv("MONGO_URI")
TIMEZONE = pytz.timezone(os.getenv("TIMEZONE", "Asia/Kolkata"))
MAX_REMINDERS_PER_USER = 50
MAX_TASK_LENGTH = 500
BACKUP_INTERVAL_HOURS = 6

class CalendarError(Exception):
    """Custom exception for calendar operations"""
    pass

class Calendar(commands.Cog):
    """Advanced Calendar System with reminders, birthdays, and holidays"""
    
    def __init__(self, bot):
        self.bot = bot
        self.scheduler = AsyncIOScheduler(timezone=TIMEZONE)
        self.db_client = None
        self.db = None
        self.reminders = None
        self.birthdays = None
        self.backup_data = None
        self.scheduled_jobs = {}  # Track scheduled jobs
        self._ready = False
        
        # Start background tasks
        self.backup_task.start()
        self.birthday_check.start()
        
    async def cog_load(self):
        """Initialize database connections and scheduler"""
        try:
            await self._init_database()
            self.scheduler.start()
            log.info("📅 Calendar Cog initialized successfully")
        except Exception as e:
            log.error(f"Failed to initialize Calendar Cog: {e}")
            raise CalendarError(f"Initialization failed: {e}")

    async def cog_unload(self):
        """Cleanup when cog is unloaded"""
        try:
            if self.scheduler.running:
                self.scheduler.shutdown(wait=True)
            if self.db_client:
                self.db_client.close()
            self.backup_task.cancel()
            self.birthday_check.cancel()
            log.info("📅 Calendar Cog unloaded successfully")
        except Exception as e:
            log.error(f"Error during cog unload: {e}")

    async def _init_database(self):
        """Initialize database connections with retry logic"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                self.db_client = AsyncIOMotorClient(
                    MONGO_URI,
                    serverSelectionTimeoutMS=5000,
                    maxPoolSize=10
                )
                # Test connection
                await self.db_client.admin.command('ping')
                
                self.db = self.db_client["lexus_calendar"]
                self.reminders = self.db.reminders
                self.birthdays = self.db.birthdays
                self.backup_data = self.db.backup_data
                
                # Create indexes for better performance
                await self._create_indexes()
                log.info("✅ Database connection established")
                return
                
            except Exception as e:
                log.warning(f"Database connection attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    raise CalendarError(f"Failed to connect to database after {max_retries} attempts")
                await asyncio.sleep(2 ** attempt)  # Exponential backoff

    async def _create_indexes(self):
        """Create database indexes for optimization"""
        try:
            await self.reminders.create_index("user_id")
            await self.reminders.create_index("time")
            await self.birthdays.create_index("user_id", unique=True)
            await self.backup_data.create_index("timestamp")
            log.info("📊 Database indexes created")
        except Exception as e:
            log.warning(f"Failed to create indexes: {e}")

    # -------------------------
    # SLASH COMMANDS
    # -------------------------

    @app_commands.command(name="addreminder", description="Add a personal reminder with advanced options")
    @app_commands.describe(
        task="What do you want to be reminded of? (max 500 characters)",
        time="When? (e.g. '2025-09-15 18:00', 'tomorrow 6pm', 'in 2 hours')",
        repeat="Repeat interval",
        channel="Channel to send reminder (optional)",
        pingrole="Role to ping (optional)"
    )
    @app_commands.choices(repeat=[
        app_commands.Choice(name="No Repeat", value="none"),
        app_commands.Choice(name="Daily", value="daily"),
        app_commands.Choice(name="Weekly", value="weekly"),
        app_commands.Choice(name="Monthly", value="monthly"),
        app_commands.Choice(name="Yearly", value="yearly")
    ])
    async def add_reminder(
        self, 
        interaction: discord.Interaction, 
        task: str, 
        time: str, 
        repeat: str = "none", 
        channel: Optional[discord.TextChannel] = None,
        pingrole: Optional[discord.Role] = None
    ):
        await interaction.response.defer(ephemeral=True)

        try:
            # Validation
            if len(task) > MAX_TASK_LENGTH:
                return await interaction.followup.send(f"❌ Task description too long (max {MAX_TASK_LENGTH} characters)")

            # Check user's reminder count
            user_reminders = await self.reminders.count_documents({"user_id": interaction.user.id})
            if user_reminders >= MAX_REMINDERS_PER_USER:
                return await interaction.followup.send(f"❌ You've reached the maximum of {MAX_REMINDERS_PER_USER} reminders")

            # Parse time with better error handling
            try:
                dt = self._parse_time(time)
            except ValueError as e:
                return await interaction.followup.send(f"❌ Invalid time format: {e}\n💡 Try: '2025-12-25 18:00', 'tomorrow 6pm', 'in 2 hours'")

            # Validate future time
            if dt <= datetime.now(TIMEZONE):
                return await interaction.followup.send("❌ Reminder time must be in the future")

            # Create reminder document
            reminder = {
                "user_id": interaction.user.id,
                "guild_id": interaction.guild_id,
                "task": task,
                "time": dt,
                "repeat": repeat.lower(),
                "channel_id": channel.id if channel else None,
                "role_id": pingrole.id if pingrole else None,
                "created_at": datetime.now(TIMEZONE),
                "active": True
            }

            result = await self.reminders.insert_one(reminder)
            reminder["_id"] = result.inserted_id

            # Schedule the reminder
            await self._schedule_reminder(result.inserted_id, reminder)

            # Create success embed
            embed = discord.Embed(
                title="✅ Reminder Created",
                color=discord.Color.green(),
                timestamp=datetime.now(TIMEZONE)
            )
            embed.add_field(name="📝 Task", value=task, inline=False)
            embed.add_field(name="⏰ Time", value=f"<t:{int(dt.timestamp())}:F>", inline=True)
            embed.add_field(name="🔄 Repeat", value=repeat.title(), inline=True)
            embed.add_field(name="🆔 ID", value=str(result.inserted_id), inline=True)
            
            if channel:
                embed.add_field(name="📍 Channel", value=channel.mention, inline=True)
            if pingrole:
                embed.add_field(name="🏷️ Role", value=pingrole.mention, inline=True)

            await interaction.followup.send(embed=embed)
            log.info(f"Reminder created by {interaction.user} ({interaction.user.id}) for {dt}")

        except Exception as e:
            log.error(f"Error creating reminder: {e}\n{traceback.format_exc()}")
            await interaction.followup.send("❌ An error occurred while creating the reminder. Please try again.")

    @app_commands.command(name="myreminders", description="View and manage your reminders")
    @app_commands.describe(page="Page number (10 reminders per page)")
    async def my_reminders(self, interaction: discord.Interaction, page: int = 1):
        try:
            if page < 1:
                page = 1

            skip = (page - 1) * 10
            total = await self.reminders.count_documents({"user_id": interaction.user.id, "active": True})
            
            if total == 0:
                embed = discord.Embed(
                    title="📭 No Reminders",
                    description="You don't have any active reminders.\nUse `/addreminder` to create one!",
                    color=discord.Color.blue()
                )
                return await interaction.response.send_message(embed=embed)

            # Get reminders for current page
            cursor = self.reminders.find(
                {"user_id": interaction.user.id, "active": True}
            ).sort("time", 1).skip(skip).limit(10)
            
            reminders = await cursor.to_list(length=10)
            
            if not reminders:
                return await interaction.response.send_message(f"❌ No reminders found on page {page}")

            embed = discord.Embed(
                title=f"📅 Your Reminders (Page {page}/{(total + 9) // 10})",
                color=discord.Color.orange(),
                timestamp=datetime.now(TIMEZONE)
            )
            embed.set_footer(text=f"Total: {total} reminders")

            for reminder in reminders:
                dt = reminder["time"]
                status = "🔄 Repeating" if reminder["repeat"] != "none" else "📅 One-time"
                
                value = f"**Time:** <t:{int(dt.timestamp())}:R>\n"
                value += f"**Type:** {status}\n"
                value += f"**ID:** `{reminder['_id']}`"
                
                embed.add_field(
                    name=f"📝 {reminder['task'][:50]}{'...' if len(reminder['task']) > 50 else ''}",
                    value=value,
                    inline=False
                )

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            log.error(f"Error fetching reminders: {e}")
            await interaction.response.send_message("❌ Error fetching reminders. Please try again.")

    @app_commands.command(name="deletereminder", description="Delete a reminder by ID")
    @app_commands.describe(reminder_id="The ID of the reminder to delete")
    async def delete_reminder(self, interaction: discord.Interaction, reminder_id: str):
        try:
            # Validate ObjectId
            try:
                obj_id = ObjectId(reminder_id)
            except:
                return await interaction.response.send_message("❌ Invalid reminder ID format")

            # Find and delete reminder
            result = await self.reminders.find_one_and_delete({
                "_id": obj_id,
                "user_id": interaction.user.id
            })

            if not result:
                return await interaction.response.send_message("❌ Reminder not found or you don't own it")

            # Remove scheduled job
            job_id = f"reminder_{obj_id}"
            if job_id in self.scheduled_jobs:
                try:
                    self.scheduler.remove_job(job_id)
                    del self.scheduled_jobs[job_id]
                except:
                    pass

            embed = discord.Embed(
                title="🗑️ Reminder Deleted",
                description=f"**Task:** {result['task']}\n**Was scheduled for:** <t:{int(result['time'].timestamp())}:F>",
                color=discord.Color.red()
            )
            
            await interaction.response.send_message(embed=embed)
            log.info(f"Reminder {reminder_id} deleted by {interaction.user}")

        except Exception as e:
            log.error(f"Error deleting reminder: {e}")
            await interaction.response.send_message("❌ Error deleting reminder. Please try again.")

    @app_commands.command(name="setbirthday", description="Set your birthday for automatic wishes")
    @app_commands.describe(date="Your birthday in DD-MM format (e.g., 15-08)")
    async def set_birthday(self, interaction: discord.Interaction, date: str):
        try:
            # Parse and validate date
            try:
                dt = datetime.strptime(date, "%d-%m")
            except ValueError:
                return await interaction.response.send_message("❌ Invalid date format. Use DD-MM (e.g., 15-08 for August 15th)")

            # Update birthday in database
            await self.birthdays.update_one(
                {"user_id": interaction.user.id},
                {
                    "$set": {
                        "user_id": interaction.user.id,
                        "guild_id": interaction.guild_id,
                        "day": dt.day,
                        "month": dt.month,
                        "updated_at": datetime.now(TIMEZONE)
                    }
                },
                upsert=True
            )

            embed = discord.Embed(
                title="🎂 Birthday Set!",
                description=f"Your birthday is now set to **{dt.strftime('%B %d')}**\n\nLexus will automatically wish you every year! 🎉",
                color=discord.Color.gold()
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            log.info(f"Birthday set for {interaction.user}: {date}")

        except Exception as e:
            log.error(f"Error setting birthday: {e}")
            await interaction.response.send_message("❌ Error setting birthday. Please try again.")

    @app_commands.command(name="holidays", description="Get Indian holidays for a specific year")
    @app_commands.describe(year="Year to get holidays for (default: current year)")
    async def holidays(self, interaction: discord.Interaction, year: int = None):
        await interaction.response.defer()
        
        try:
            if year is None:
                year = datetime.now().year
                
            # Validate year
            if year < 2020 or year > 2030:
                return await interaction.followup.send("❌ Year must be between 2020 and 2030")

            if not CALENDARIFIC_API:
                return await interaction.followup.send("❌ Holiday API is not configured")

            # Fetch holidays with timeout
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                url = f"https://calendarific.com/api/v2/holidays"
                params = {
                    "api_key": CALENDARIFIC_API,
                    "country": "IN",
                    "year": year,
                    "type": "national"
                }
                
                async with session.get(url, params=params) as response:
                    if response.status != 200:
                        return await interaction.followup.send("❌ Failed to fetch holidays. Please try again later.")
                    
                    data = await response.json()

            holidays = data.get("response", {}).get("holidays", [])
            if not holidays:
                return await interaction.followup.send(f"❌ No holidays found for {year}")

            # Sort holidays by date
            holidays.sort(key=lambda x: x['date']['iso'])
            
            # Create embed with pagination
            embeds = []
            chunk_size = 8
            
            for i in range(0, len(holidays), chunk_size):
                chunk = holidays[i:i + chunk_size]
                embed = discord.Embed(
                    title=f"🇮🇳 Indian National Holidays {year}",
                    color=discord.Color.green(),
                    timestamp=datetime.now(TIMEZONE)
                )
                embed.set_footer(text=f"Page {(i // chunk_size) + 1}/{(len(holidays) + chunk_size - 1) // chunk_size}")
                
                for holiday in chunk:
                    date_obj = datetime.strptime(holiday['date']['iso'], '%Y-%m-%d')
                    date_str = date_obj.strftime('%B %d, %Y')
                    
                    embed.add_field(
                        name=f"📅 {holiday['name']}",
                        value=f"**Date:** {date_str}\n**Description:** {holiday.get('description', 'National Holiday')}",
                        inline=False
                    )
                
                embeds.append(embed)

            # Send first embed
            await interaction.followup.send(embed=embeds[0])
            
            # If multiple pages, send others
            if len(embeds) > 1:
                for embed in embeds[1:]:
                    await interaction.followup.send(embed=embed)

        except asyncio.TimeoutError:
            await interaction.followup.send("❌ Request timed out. Please try again.")
        except Exception as e:
            log.error(f"Error fetching holidays: {e}")
            await interaction.followup.send("❌ Error fetching holidays. Please try again later.")

    # -------------------------
    # BACKGROUND TASKS
    # -------------------------

    @tasks.loop(hours=24)
    async def birthday_check(self):
        """Check for birthdays daily at midnight"""
        try:
            now = datetime.now(TIMEZONE)
            if now.hour != 0:  # Only run at midnight
                return

            # Find users with birthdays today
            birthdays = self.birthdays.find({
                "day": now.day,
                "month": now.month
            })

            async for birthday in birthdays:
                try:
                    user = self.bot.get_user(birthday["user_id"])
                    guild = self.bot.get_guild(birthday["guild_id"])
                    
                    if user and guild:
                        # Send birthday message
                        embed = discord.Embed(
                            title="🎉 Happy Birthday! 🎂",
                            description=f"Happy Birthday {user.mention}! 🎈\n\nWishing you a wonderful day filled with joy and happiness! 🎁",
                            color=discord.Color.gold()
                        )
                        embed.set_thumbnail(url=user.display_avatar.url)
                        
                        # Try to send to a general channel
                        channel = discord.utils.get(guild.text_channels, name="general") or guild.system_channel
                        if channel and channel.permissions_for(guild.me).send_messages:
                            await channel.send(embed=embed)
                            
                        log.info(f"Birthday wish sent for {user} in {guild}")
                        
                except Exception as e:
                    log.error(f"Error sending birthday wish: {e}")

        except Exception as e:
            log.error(f"Error in birthday check task: {e}")

    @tasks.loop(hours=BACKUP_INTERVAL_HOURS)
    async def backup_task(self):
        """Create periodic backups of important data"""
        try:
            # Create backup document
            backup_doc = {
                "timestamp": datetime.now(TIMEZONE),
                "reminder_count": await self.reminders.count_documents({}),
                "birthday_count": await self.birthdays.count_documents({}),
                "active_reminders": await self.reminders.count_documents({"active": True})
            }
            
            await self.backup_data.insert_one(backup_doc)
            
            # Clean old backups (keep last 30 days)
            cutoff = datetime.now(TIMEZONE) - timedelta(days=30)
            await self.backup_data.delete_many({"timestamp": {"$lt": cutoff}})
            
            log.info(f"Backup created: {backup_doc['reminder_count']} reminders, {backup_doc['birthday_count']} birthdays")
            
        except Exception as e:
            log.error(f"Error in backup task: {e}")

    # -------------------------
    # INTERNAL FUNCTIONS
    # -------------------------

    def _parse_time(self, time_str: str) -> datetime:
        """Parse time string with various formats"""
        try:
            # Handle relative times
            time_str = time_str.lower().strip()
            now = datetime.now(TIMEZONE)
            
            if time_str.startswith("in "):
                # Handle "in X hours/minutes" format
                parts = time_str.split()
                if len(parts) >= 3:
                    amount = int(parts[1])
                    unit = parts[2].lower()
                    
                    if unit.startswith("minute"):
                        return now + timedelta(minutes=amount)
                    elif unit.startswith("hour"):
                        return now + timedelta(hours=amount)
                    elif unit.startswith("day"):
                        return now + timedelta(days=amount)
            
            elif "tomorrow" in time_str:
                tomorrow = now + timedelta(days=1)
                if "at" in time_str or any(x in time_str for x in ["am", "pm", ":"]):
                    time_part = time_str.split("tomorrow")[-1].strip().lstrip("at").strip()
                    try:
                        time_obj = parse_date(f"tomorrow {time_part}", dayfirst=True)
                        return time_obj.astimezone(TIMEZONE)
                    except:
                        pass
                return tomorrow.replace(hour=12, minute=0, second=0, microsecond=0)
            
            # Default parsing
            parsed = parse_date(time_str, dayfirst=True)
            if parsed.tzinfo is None:
                parsed = TIMEZONE.localize(parsed)
            else:
                parsed = parsed.astimezone(TIMEZONE)
                
            return parsed
            
        except Exception as e:
            raise ValueError(f"Could not parse time '{time_str}': {e}")

    async def _schedule_reminder(self, reminder_id: ObjectId, reminder: Dict[str, Any]):
        """Schedule a reminder with the job scheduler"""
        try:
            job_id = f"reminder_{reminder_id}"
            
            async def reminder_job():
                try:
                    await self._execute_reminder(reminder_id, reminder)
                except Exception as e:
                    log.error(f"Error executing reminder {reminder_id}: {e}")

            # Schedule the job
            self.scheduler.add_job(
                reminder_job,
                DateTrigger(run_date=reminder["time"]),
                id=job_id,
                replace_existing=True
            )
            
            self.scheduled_jobs[job_id] = reminder_id
            log.info(f"Reminder {reminder_id} scheduled for {reminder['time']}")
            
        except Exception as e:
            log.error(f"Error scheduling reminder {reminder_id}: {e}")
            raise

    async def _execute_reminder(self, reminder_id: ObjectId, reminder: Dict[str, Any]):
        """Execute a reminder and handle repetition"""
        try:
            # Get fresh reminder data
            fresh_reminder = await self.reminders.find_one({"_id": reminder_id})
            if not fresh_reminder or not fresh_reminder.get("active", True):
                return

            # Send reminder message
            await self._send_reminder_message(fresh_reminder)
            
            # Handle repetition
            if fresh_reminder["repeat"] != "none":
                next_time = self._calculate_next_time(fresh_reminder["time"], fresh_reminder["repeat"])
                
                # Update reminder time
                await self.reminders.update_one(
                    {"_id": reminder_id},
                    {"$set": {"time": next_time}}
                )
                
                # Schedule next occurrence
                updated_reminder = {**fresh_reminder, "time": next_time}
                await self._schedule_reminder(reminder_id, updated_reminder)
                
                log.info(f"Repeating reminder {reminder_id} scheduled for {next_time}")
            else:
                # Mark as inactive for one-time reminders
                await self.reminders.update_one(
                    {"_id": reminder_id},
                    {"$set": {"active": False}}
                )
                log.info(f"One-time reminder {reminder_id} completed")
                
        except Exception as e:
            log.error(f"Error executing reminder {reminder_id}: {e}")

    async def _send_reminder_message(self, reminder: Dict[str, Any]):
        """Send the actual reminder message"""
        try:
            user = self.bot.get_user(reminder["user_id"])
            guild = self.bot.get_guild(reminder["guild_id"]) if reminder.get("guild_id") else None
            
            if not user:
                log.warning(f"User {reminder['user_id']} not found for reminder {reminder['_id']}")
                return

            # Create reminder embed
            embed = discord.Embed(
                title="⏰ Reminder",
                description=reminder["task"],
                color=discord.Color.blue(),
                timestamp=datetime.now(TIMEZONE)
            )
            embed.set_footer(text=f"Reminder ID: {reminder['_id']}")
            
            # Add role ping if specified
            content = ""
            if reminder.get("role_id") and guild:
                role = guild.get_role(reminder["role_id"])
                if role:
                    content = role.mention

            # Try to send to specified channel first, then DM
            sent = False
            
            if reminder.get("channel_id") and guild:
                try:
                    channel = guild.get_channel(reminder["channel_id"])
                    if channel and channel.permissions_for(guild.me).send_messages:
                        await channel.send(content=content, embed=embed)
                        sent = True
                except Exception as e:
                    log.warning(f"Failed to send reminder to channel: {e}")
            
            # Fallback to DM
            if not sent:
                try:
                    await user.send(embed=embed)
                except Exception as e:
                    log.warning(f"Failed to send DM reminder to {user}: {e}")

            log.info(f"Reminder sent to {user} for: {reminder['task'][:50]}")
            
        except Exception as e:
            log.error(f"Error sending reminder message: {e}")

    def _calculate_next_time(self, current_time: datetime, repeat: str) -> datetime:
        """Calculate the next occurrence time for repeating reminders"""
        if repeat == "daily":
            return current_time + timedelta(days=1)
        elif repeat == "weekly":
            return current_time + timedelta(weeks=1)
        elif repeat == "monthly":
            # Add one month (approximate)
            if current_time.month == 12:
                return current_time.replace(year=current_time.year + 1, month=1)
            else:
                return current_time.replace(month=current_time.month + 1)
        elif repeat == "yearly":
            return current_time.replace(year=current_time.year + 1)
        else:
            return current_time

    @commands.Cog.listener()
    async def on_ready(self):
        """Reschedule existing reminders when bot starts"""
        if self._ready:
            return
            
        try:
            log.info("📅 Calendar Cog - Rescheduling active reminders...")
            
            # Find all active reminders
            active_reminders = self.reminders.find({"active": True})
            rescheduled_count = 0
            
            async for reminder in active_reminders:
                try:
                    # Skip past reminders
                    if reminder["time"] <= datetime.now(TIMEZONE):
                        if reminder["repeat"] == "none":
                            # Mark one-time past reminders as inactive
                            await self.reminders.update_one(
                                {"_id": reminder["_id"]},
                                {"$set": {"active": False}}
                            )
                            continue
                        else:
                            # Update past repeating reminders to next occurrence
                            next_time = self._calculate_next_time(reminder["time"], reminder["repeat"])
                            await self.reminders.update_one(
                                {"_id": reminder["_id"]},
                                {"$set": {"time": next_time}}
                            )
                            reminder["time"] = next_time
                    
                    # Schedule the reminder
                    await self._schedule_reminder(reminder["_id"], reminder)
                    rescheduled_count += 1
                    
                except Exception as e:
                    log.error(f"Error rescheduling reminder {reminder['_id']}: {e}")

            self._ready = True
            log.info(f"✅ Calendar Cog ready - {rescheduled_count} reminders rescheduled")
            
        except Exception as e:
            log.error(f"Error in on_ready: {e}")

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Handle application command errors"""
        if interaction.response.is_done():
            send_method = interaction.followup.send
        else:
            send_method = interaction.response.send_message
            
        if isinstance(error, app_commands.CommandOnCooldown):
            await send_method(f"⏱️ Command on cooldown. Try again in {error.retry_after:.2f}s", ephemeral=True)
        elif isinstance(error, app_commands.MissingPermissions):
            await send_method("❌ You don't have permission to use this command", ephemeral=True)
        else:
            log.error(f"Command error: {error}")
            await send_method("❌ An unexpected error occurred. Please try again later.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Calendar(bot))


class EventNavigationView(discord.ui.View):
    """Navigation view for paginated event embeds"""
    
    def __init__(self, embeds: List[discord.Embed]):
        super().__init__(timeout=300)  # 5 minute timeout
        self.embeds = embeds
        self.current_page = 0
        
        # Disable buttons if only one page
        if len(embeds) <= 1:
            self.clear_items()
    
    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.primary, disabled=True)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            await self._update_message(interaction)
    
    @discord.ui.button(label="▶️ Next", style=discord.ButtonStyle.primary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < len(self.embeds) - 1:
            self.current_page += 1
            await self._update_message(interaction)
    
    @discord.ui.button(label="⏹️ Stop", style=discord.ButtonStyle.danger)
    async def stop_pagination(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.clear_items()
        await interaction.response.edit_message(view=self)
        self.stop()
    
    async def _update_message(self, interaction: discord.Interaction):
        # Update button states
        self.children[0].disabled = (self.current_page == 0)  # Previous button
        self.children[1].disabled = (self.current_page == len(self.embeds) - 1)  # Next button
        
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)
    
    async def on_timeout(self):
        # Disable all buttons when timeout occurs
        for child in self.children:
            child.disabled = True
