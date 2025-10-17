import discord
from discord.ext import commands, tasks
from discord import app_commands, ui
import sqlite3
from datetime import datetime, timedelta
import asyncio
import logging
from typing import Optional, Union

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('RoomSystem')

# Configuration
CLEANUP_DELAY_MINUTES = 5
MAX_ROOMS_PER_USER = 3
MAX_ROOM_NAME_LENGTH = 32
DB_RETRY_ATTEMPTS = 3
DB_RETRY_DELAY = 0.5


class DatabaseManager:
    """Handles all database operations with retry logic and error handling"""
    
    def __init__(self, db_path: str = "rooms.db"):
        self.db_path = db_path
        self.db = None
        self.cursor = None
        self.initialize_db()
    
    def initialize_db(self):
        """Initialize database with retry logic"""
        for attempt in range(DB_RETRY_ATTEMPTS):
            try:
                self.db = sqlite3.connect(self.db_path, check_same_thread=False)
                self.cursor = self.db.cursor()
                self.cursor.execute("""
                    CREATE TABLE IF NOT EXISTS rooms (
                        channel_id INTEGER PRIMARY KEY,
                        owner_id INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        last_active TEXT NOT NULL,
                        guild_id INTEGER NOT NULL
                    )
                """)
                self.db.commit()
                logger.info("Database initialized successfully")
                return
            except sqlite3.Error as e:
                logger.error(f"Database init attempt {attempt + 1} failed: {e}")
                if attempt < DB_RETRY_ATTEMPTS - 1:
                    asyncio.sleep(DB_RETRY_DELAY)
                else:
                    raise Exception("Failed to initialize database after multiple attempts")
    
    def execute_with_retry(self, query: str, params: tuple = ()):
        """Execute database query with retry logic"""
        for attempt in range(DB_RETRY_ATTEMPTS):
            try:
                self.cursor.execute(query, params)
                self.db.commit()
                return True
            except sqlite3.Error as e:
                logger.error(f"Query execution attempt {attempt + 1} failed: {e}")
                if attempt < DB_RETRY_ATTEMPTS - 1:
                    asyncio.sleep(DB_RETRY_DELAY)
                else:
                    logger.error(f"Query failed after {DB_RETRY_ATTEMPTS} attempts: {query}")
                    return False
    
    def fetch_with_retry(self, query: str, params: tuple = ()):
        """Fetch data with retry logic"""
        for attempt in range(DB_RETRY_ATTEMPTS):
            try:
                self.cursor.execute(query, params)
                return self.cursor.fetchall()
            except sqlite3.Error as e:
                logger.error(f"Fetch attempt {attempt + 1} failed: {e}")
                if attempt < DB_RETRY_ATTEMPTS - 1:
                    asyncio.sleep(DB_RETRY_DELAY)
                else:
                    return []
    
    def close(self):
        """Safely close database connection"""
        try:
            if self.db:
                self.db.close()
                logger.info("Database connection closed")
        except Exception as e:
            logger.error(f"Error closing database: {e}")


class RoomButtons(ui.View):
    def __init__(self, bot, owner_id, voice_channel):
        super().__init__(timeout=None)
        self.bot = bot
        self.owner_id = owner_id
        self.voice_channel = voice_channel

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Verify the user has permission to use controls"""
        try:
            if interaction.user.id != self.owner_id:
                await interaction.response.send_message(
                    "❌ Only the room owner can use these controls!", 
                    ephemeral=True
                )
                return False
            return True
        except discord.errors.NotFound:
            logger.warning(f"Interaction expired for user {interaction.user.id}")
            return False
        except Exception as e:
            logger.error(f"Error in interaction check: {e}")
            return False

    async def send_log(self, guild: discord.Guild, message: str):
        """Send log message with fallback"""
        try:
            log_channel = discord.utils.get(guild.text_channels, name="room-logs")
            if log_channel:
                await log_channel.send(message)
        except discord.Forbidden:
            logger.warning(f"No permission to send logs in {guild.name}")
        except Exception as e:
            logger.error(f"Failed to send log: {e}")

    @ui.button(label="Lock Room", style=discord.ButtonStyle.danger, emoji="🔒")
    async def lock_room(self, interaction: discord.Interaction, button: ui.Button):
        try:
            # Check if channel still exists
            if not self.voice_channel:
                await interaction.response.send_message(
                    "❌ Voice channel no longer exists!", 
                    ephemeral=True
                )
                return
            
            await self.voice_channel.set_permissions(
                interaction.guild.default_role, 
                connect=False
            )
            await interaction.response.send_message("🔒 Room locked!", ephemeral=True)
            await self.send_log(
                interaction.guild,
                f"🔒 {interaction.user.mention} locked **{self.voice_channel.name}**"
            )
            
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to lock this room!", 
                ephemeral=True
            )
        except discord.HTTPException as e:
            await interaction.response.send_message(
                f"❌ Failed to lock room: {str(e)}", 
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Unexpected error in lock_room: {e}")
            await interaction.response.send_message(
                "❌ An unexpected error occurred!", 
                ephemeral=True
            )

    @ui.button(label="Unlock Room", style=discord.ButtonStyle.success, emoji="🔓")
    async def unlock_room(self, interaction: discord.Interaction, button: ui.Button):
        try:
            if not self.voice_channel:
                await interaction.response.send_message(
                    "❌ Voice channel no longer exists!", 
                    ephemeral=True
                )
                return
            
            await self.voice_channel.set_permissions(
                interaction.guild.default_role, 
                connect=True
            )
            await interaction.response.send_message("🔓 Room unlocked!", ephemeral=True)
            await self.send_log(
                interaction.guild,
                f"🔓 {interaction.user.mention} unlocked **{self.voice_channel.name}**"
            )
            
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to unlock this room!", 
                ephemeral=True
            )
        except discord.HTTPException as e:
            await interaction.response.send_message(
                f"❌ Failed to unlock room: {str(e)}", 
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Unexpected error in unlock_room: {e}")
            await interaction.response.send_message(
                "❌ An unexpected error occurred!", 
                ephemeral=True
            )

    @ui.button(label="Rename Room", style=discord.ButtonStyle.primary, emoji="✏️")
    async def rename_room(self, interaction: discord.Interaction, button: ui.Button):
        try:
            if not self.voice_channel:
                await interaction.response.send_message(
                    "❌ Voice channel no longer exists!", 
                    ephemeral=True
                )
                return
            
            await interaction.response.send_modal(RenameModal(self.voice_channel))
            
        except Exception as e:
            logger.error(f"Error showing rename modal: {e}")
            await interaction.response.send_message(
                "❌ Failed to open rename dialog!", 
                ephemeral=True
            )

    @ui.button(label="Kick User", style=discord.ButtonStyle.secondary, emoji="🦶")
    async def kick_user(self, interaction: discord.Interaction, button: ui.Button):
        try:
            if not self.voice_channel:
                await interaction.response.send_message(
                    "❌ Voice channel no longer exists!", 
                    ephemeral=True
                )
                return
            
            if len(self.voice_channel.members) == 0:
                await interaction.response.send_message(
                    "❌ No users in the room to kick!", 
                    ephemeral=True
                )
                return
            
            await interaction.response.send_modal(KickModal(self.voice_channel))
            
        except Exception as e:
            logger.error(f"Error showing kick modal: {e}")
            await interaction.response.send_message(
                "❌ Failed to open kick dialog!", 
                ephemeral=True
            )

    @ui.button(label="End Room", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def end_room(self, interaction: discord.Interaction, button: ui.Button):
        try:
            if not self.voice_channel:
                await interaction.response.send_message(
                    "❌ Voice channel no longer exists!", 
                    ephemeral=True
                )
                return
            
            channel_name = self.voice_channel.name
            await self.send_log(
                interaction.guild,
                f"🗑️ {interaction.user.mention} ended room **{channel_name}**"
            )
            
            await interaction.response.send_message("Room deleted 🗑️", ephemeral=True)
            
            # Delete from database
            cog = self.bot.get_cog("RoomSystem")
            if cog and cog.db_manager:
                cog.db_manager.execute_with_retry(
                    "DELETE FROM rooms WHERE channel_id = ?",
                    (self.voice_channel.id,)
                )
            
            await self.voice_channel.delete()
            
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to delete this room!", 
                ephemeral=True
            )
        except discord.HTTPException as e:
            await interaction.response.send_message(
                f"❌ Failed to delete room: {str(e)}", 
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Unexpected error in end_room: {e}")
            try:
                await interaction.response.send_message(
                    "❌ An unexpected error occurred!", 
                    ephemeral=True
                )
            except:
                pass


class RenameModal(ui.Modal, title="Rename Your Room"):
    new_name = ui.TextInput(
        label="New Room Name",
        placeholder="Enter new room name...",
        max_length=MAX_ROOM_NAME_LENGTH,
        min_length=1
    )

    def __init__(self, voice_channel):
        super().__init__()
        self.voice_channel = voice_channel

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Sanitize input
            new_name = self.new_name.value.strip()
            
            if not new_name:
                await interaction.response.send_message(
                    "❌ Room name cannot be empty!", 
                    ephemeral=True
                )
                return
            
            # Check for inappropriate content (basic filter)
            forbidden_words = ['@everyone', '@here', 'discord.gg']
            if any(word in new_name.lower() for word in forbidden_words):
                await interaction.response.send_message(
                    "❌ Room name contains forbidden content!", 
                    ephemeral=True
                )
                return
            
            await self.voice_channel.edit(name=f"🎮│{new_name}")
            await interaction.response.send_message(
                f"✅ Room renamed to **{new_name}**", 
                ephemeral=True
            )
            
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to rename this room!", 
                ephemeral=True
            )
        except discord.HTTPException as e:
            await interaction.response.send_message(
                f"❌ Failed to rename room: {str(e)}", 
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Unexpected error in rename modal: {e}")
            await interaction.response.send_message(
                "❌ An unexpected error occurred!", 
                ephemeral=True
            )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        logger.error(f"Modal error: {error}")
        try:
            await interaction.response.send_message(
                "❌ Something went wrong!", 
                ephemeral=True
            )
        except:
            pass


class KickModal(ui.Modal, title="Kick a User From Room"):
    member_name = ui.TextInput(
        label="Enter username to kick",
        placeholder="e.g. @User or username"
    )

    def __init__(self, voice_channel):
        super().__init__()
        self.voice_channel = voice_channel

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Sanitize and normalize input
            search_name = self.member_name.value.strip().replace("@", "").lower()
            
            if not search_name:
                await interaction.response.send_message(
                    "❌ Please enter a valid username!", 
                    ephemeral=True
                )
                return
            
            # Find member in voice channel
            member = None
            for m in self.voice_channel.members:
                if (m.name.lower() == search_name or 
                    m.display_name.lower() == search_name or
                    str(m.id) == search_name):
                    member = m
                    break
            
            if not member:
                await interaction.response.send_message(
                    f"❌ User '{self.member_name.value}' not found in this room!", 
                    ephemeral=True
                )
                return
            
            # Prevent kicking yourself
            if member.id == interaction.user.id:
                await interaction.response.send_message(
                    "❌ You cannot kick yourself! Use 'End Room' instead.", 
                    ephemeral=True
                )
                return
            
            await member.move_to(None)
            await interaction.response.send_message(
                f"🦶 {member.mention} kicked from the room!", 
                ephemeral=True
            )
            
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to kick users!", 
                ephemeral=True
            )
        except discord.HTTPException as e:
            await interaction.response.send_message(
                f"❌ Failed to kick user: {str(e)}", 
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Unexpected error in kick modal: {e}")
            await interaction.response.send_message(
                "❌ An unexpected error occurred!", 
                ephemeral=True
            )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        logger.error(f"Modal error: {error}")
        try:
            await interaction.response.send_message(
                "❌ Something went wrong!", 
                ephemeral=True
            )
        except:
            pass


class RoomSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_manager = DatabaseManager()
        self.cleanup_rooms.start()

    def cog_unload(self):
        """Clean shutdown of the cog"""
        self.cleanup_rooms.cancel()
        self.db_manager.close()

    async def get_or_create_category(self, guild: discord.Guild) -> Optional[discord.CategoryChannel]:
        """Get or create the game rooms category with error handling"""
        try:
            category = discord.utils.get(guild.categories, name="🎮 Game Rooms")
            
            if not category:
                # Check if we can create more channels
                if len(guild.channels) >= 500:
                    logger.error(f"Guild {guild.name} has reached channel limit")
                    return None
                
                category = await guild.create_category(
                    "🎮 Game Rooms",
                    reason="Auto-created by Lexus Room System"
                )
                
                # Set permissions
                await category.set_permissions(
                    guild.default_role,
                    manage_channels=False
                )
                
                # Give admins permission
                for role in guild.roles:
                    if role.permissions.administrator:
                        await category.set_permissions(
                            role,
                            manage_channels=True
                        )
                
                logger.info(f"Created category in {guild.name}")
            
            return category
            
        except discord.Forbidden:
            logger.error(f"No permission to create category in {guild.name}")
            return None
        except discord.HTTPException as e:
            logger.error(f"HTTP error creating category: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error creating category: {e}")
            return None

    async def get_log_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        """Get or create log channel with error handling"""
        try:
            log_channel = discord.utils.get(guild.text_channels, name="room-logs")
            
            if not log_channel:
                if len(guild.channels) >= 500:
                    logger.warning(f"Cannot create log channel in {guild.name} - channel limit reached")
                    return None
                
                log_channel = await guild.create_text_channel(
                    "room-logs",
                    reason="Auto-created for Lexus Room System logs"
                )
                logger.info(f"Created log channel in {guild.name}")
            
            return log_channel
            
        except discord.Forbidden:
            logger.warning(f"No permission to create log channel in {guild.name}")
            return None
        except Exception as e:
            logger.error(f"Error getting/creating log channel: {e}")
            return None

    def get_user_room_count(self, user_id: int, guild_id: int) -> int:
        """Get number of active rooms owned by user"""
        try:
            result = self.db_manager.fetch_with_retry(
                "SELECT COUNT(*) FROM rooms WHERE owner_id = ? AND guild_id = ?",
                (user_id, guild_id)
            )
            return result[0][0] if result else 0
        except Exception as e:
            logger.error(f"Error getting user room count: {e}")
            return 0

    @app_commands.command(
        name="setup_room_panel",
        description="Create the main Game Room Creator panel"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_room_panel(self, interaction: discord.Interaction):
        try:
            embed = discord.Embed(
                title="🎮 Create Your Game Room",
                description=(
                    "Press the button below to instantly create your own private room!\n"
                    "You'll get full control through Lexus buttons inside your channel.\n\n"
                    f"**Features:**\n"
                    f"• Lock/Unlock your room\n"
                    f"• Rename your room\n"
                    f"• Kick users\n"
                    f"• Auto-cleanup after {CLEANUP_DELAY_MINUTES} minutes of inactivity"
                ),
                color=discord.Color.blurple()
            )
            embed.set_footer(text="Lexus Room System • Secure & Easy")

            view = ui.View(timeout=None)
            view.add_item(CreateRoomButton(self.bot))
            
            await interaction.channel.send(embed=embed, view=view)
            await interaction.response.send_message(
                "✅ Room Creator panel created successfully!",
                ephemeral=True
            )
            
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to send messages in this channel!",
                ephemeral=True
            )
        except discord.HTTPException as e:
            await interaction.response.send_message(
                f"❌ Failed to create panel: {str(e)}",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error in setup_room_panel: {e}")
            await interaction.response.send_message(
                "❌ An unexpected error occurred!",
                ephemeral=True
            )

    async def create_room_for_user(
        self, 
        user: discord.Member, 
        guild: discord.Guild
    ) -> Optional[discord.VoiceChannel]:
        """Create a private room for user with comprehensive error handling"""
        
        try:
            # Check room limit per user
            user_rooms = self.get_user_room_count(user.id, guild.id)
            if user_rooms >= MAX_ROOMS_PER_USER:
                raise ValueError(
                    f"You can only have {MAX_ROOMS_PER_USER} active rooms at a time!"
                )
            
            # Get or create category
            category = await self.get_or_create_category(guild)
            if not category:
                raise Exception("Failed to create or access category")
            
            # Check category channel limit (50 channels per category)
            if len(category.channels) >= 50:
                raise ValueError("Room category is full! Please contact an administrator.")
            
            # Setup permissions
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(
                    view_channel=False,
                    connect=False
                ),
                user: discord.PermissionOverwrite(
                    view_channel=True,
                    connect=True,
                    speak=True,
                    stream=True
                ),
                guild.me: discord.PermissionOverwrite(
                    manage_channels=True,
                    move_members=True,
                    mute_members=True,
                    deafen_members=True,
                    view_channel=True
                )
            }

            # Create voice channel
            voice_channel = await guild.create_voice_channel(
                f"🎮│{user.name}'s Room",
                overwrites=overwrites,
                category=category,
                reason=f"Private room created for {user.name}"
            )
            
            # Create control embed
            control_embed = discord.Embed(
                title=f"🎮 {user.name}'s Room Controls",
                description=(
                    "Use the buttons below to manage your private room.\n\n"
                    f"**⚠️ Auto-Delete:** Room will be deleted after "
                    f"{CLEANUP_DELAY_MINUTES} minutes of inactivity."
                ),
                color=discord.Color.green()
            )
            control_embed.add_field(
                name="🔒 Lock/Unlock",
                value="Control who can join your room",
                inline=True
            )
            control_embed.add_field(
                name="✏️ Rename",
                value="Change your room name",
                inline=True
            )
            control_embed.add_field(
                name="🦶 Kick",
                value="Remove unwanted users",
                inline=True
            )
            control_embed.set_footer(text="Lexus Room System")
            
            # Create control thread
            view = RoomButtons(self.bot, user.id, voice_channel)
            
            try:
                control_thread = await voice_channel.create_thread(
                    name="Room Controls",
                    auto_archive_duration=60
                )
                await control_thread.send(embed=control_embed, view=view)
            except Exception as e:
                logger.warning(f"Failed to create thread, trying text channel: {e}")
                # Fallback: Send in a text channel or DM
                try:
                    await user.send(embed=control_embed, view=view)
                except:
                    logger.error("Failed to send controls via DM")

            # Save to database
            now = datetime.now().isoformat()
            success = self.db_manager.execute_with_retry(
                """INSERT OR REPLACE INTO rooms 
                   (channel_id, owner_id, created_at, last_active, guild_id) 
                   VALUES (?, ?, ?, ?, ?)""",
                (voice_channel.id, user.id, now, now, guild.id)
            )
            
            if not success:
                logger.warning(f"Failed to save room {voice_channel.id} to database")

            # Log creation
            log_channel = await self.get_log_channel(guild)
            if log_channel:
                try:
                    await log_channel.send(
                        f"✅ {user.mention} created room **{voice_channel.name}** "
                        f"at <t:{int(datetime.now().timestamp())}:f>"
                    )
                except:
                    pass

            logger.info(f"Room created: {voice_channel.name} for {user.name}")
            return voice_channel
            
        except ValueError as e:
            # User-friendly errors
            logger.warning(f"User error creating room: {e}")
            raise
        except discord.Forbidden:
            logger.error(f"Permission error creating room for {user.name}")
            raise Exception("I don't have permission to create rooms!")
        except discord.HTTPException as e:
            logger.error(f"Discord HTTP error creating room: {e}")
            raise Exception(f"Discord error: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error creating room: {e}")
            raise Exception("An unexpected error occurred!")

    @tasks.loop(minutes=1)
    async def cleanup_rooms(self):
        """Clean up inactive rooms with error handling"""
        try:
            now = datetime.now()
            rooms = self.db_manager.fetch_with_retry(
                "SELECT channel_id, last_active, guild_id FROM rooms"
            )
            
            for channel_id, last_active, guild_id in rooms:
                try:
                    channel = self.bot.get_channel(channel_id)
                    
                    # If channel not in cache, try fetching
                    if not channel:
                        try:
                            channel = await self.bot.fetch_channel(channel_id)
                        except discord.NotFound:
                            # Channel deleted externally
                            logger.info(f"Channel {channel_id} not found, removing from DB")
                            self.db_manager.execute_with_retry(
                                "DELETE FROM rooms WHERE channel_id = ?",
                                (channel_id,)
                            )
                            continue
                        except Exception:
                            continue
                    
                    if not isinstance(channel, discord.VoiceChannel):
                        continue

                    # Update last active if members present
                    if len(channel.members) > 0:
                        self.db_manager.execute_with_retry(
                            "UPDATE rooms SET last_active = ? WHERE channel_id = ?",
                            (datetime.now().isoformat(), channel_id)
                        )
                        continue

                    # Check if room should be deleted
                    last_active_time = datetime.fromisoformat(last_active)
                    if now - last_active_time > timedelta(minutes=CLEANUP_DELAY_MINUTES):
                        # Send log message
                        log_channel = discord.utils.get(
                            channel.guild.text_channels,
                            name="room-logs"
                        )
                        if log_channel:
                            try:
                                await log_channel.send(
                                    f"⏰ Auto-deleting **{channel.name}** "
                                    f"(inactive for {CLEANUP_DELAY_MINUTES} mins)"
                                )
                            except:
                                pass

                        # Delete channel
                        try:
                            await channel.delete(reason="Auto-cleanup: inactive room")
                            logger.info(f"Deleted inactive room: {channel.name}")
                        except discord.Forbidden:
                            logger.error(f"No permission to delete {channel.name}")
                        except discord.HTTPException as e:
                            logger.error(f"HTTP error deleting {channel.name}: {e}")

                        # Remove from database
                        self.db_manager.execute_with_retry(
                            "DELETE FROM rooms WHERE channel_id = ?",
                            (channel_id,)
                        )
                        
                except Exception as e:
                    logger.error(f"Error processing room {channel_id}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Critical error in cleanup_rooms: {e}")

    @cleanup_rooms.before_loop
    async def before_cleanup(self):
        """Wait for bot to be ready before starting cleanup loop"""
        await self.bot.wait_until_ready()
        logger.info("Cleanup task started")

    @cleanup_rooms.error
    async def cleanup_error(self, error):
        """Handle errors in the cleanup loop"""
        logger.error(f"Cleanup loop error: {error}")


class CreateRoomButton(ui.Button):
    def __init__(self, bot):
        super().__init__(
            label="🎮 Create Room",
            style=discord.ButtonStyle.primary,
            custom_id="persistent_create_room"
        )
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        try:
            # Defer response to avoid timeout
            await interaction.response.defer(ephemeral=True)
            
            cog = self.bot.get_cog("RoomSystem")
            if not cog:
                await interaction.followup.send(
                    "❌ Room system is not available!",
                    ephemeral=True
                )
                return
            
            # Create room
            voice_channel = await cog.create_room_for_user(
                interaction.user,
                interaction.guild
            )
            
            if voice_channel:
                await interaction.followup.send(
                    f"✅ Room created: {voice_channel.mention}\n"
                    f"Join the voice channel to start using it!",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ Failed to create room. Please try again later.",
                    ephemeral=True
                )
                
        except ValueError as e:
            # User-friendly errors
            await interaction.followup.send(
                f"❌ {str(e)}",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error in CreateRoomButton callback: {e}")
            await interaction.followup.send(
                f"❌ {str(e)}",
                ephemeral=True
            )


async def setup(bot):
    """Setup function to add cog to bot"""
    try:
        await bot.add_cog(RoomSystem(bot))
        logger.info("RoomSystem cog loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load RoomSystem cog: {e}")
        raise
