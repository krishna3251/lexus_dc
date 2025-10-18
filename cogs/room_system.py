import discord
from discord.ext import commands, tasks
from discord import app_commands, ui
import sqlite3
from datetime import datetime, timedelta
import asyncio
import logging
from typing import Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('RoomSystem')

# Configuration Constants
CLEANUP_DELAY_MINUTES = 5
MAX_ROOMS_PER_USER = 3
MAX_ROOM_NAME_LENGTH = 32
DB_RETRY_ATTEMPTS = 3
DB_RETRY_DELAY = 0.5
CREATOR_CHANNEL_NAME = "➕ Create Room"


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
            if not self.voice_channel:
                await interaction.response.send_message("❌ Voice channel no longer exists!", ephemeral=True)
                return
            
            await self.voice_channel.set_permissions(interaction.guild.default_role, connect=False)
            await interaction.response.send_message("🔒 Room locked!", ephemeral=True)
            await self.send_log(interaction.guild, f"🔒 {interaction.user.mention} locked **{self.voice_channel.name}**")
            
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to lock this room!", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ Failed to lock room: {str(e)}", ephemeral=True)
        except Exception as e:
            logger.error(f"Unexpected error in lock_room: {e}")
            await interaction.response.send_message("❌ An unexpected error occurred!", ephemeral=True)

    @ui.button(label="Unlock Room", style=discord.ButtonStyle.success, emoji="🔓")
    async def unlock_room(self, interaction: discord.Interaction, button: ui.Button):
        try:
            if not self.voice_channel:
                await interaction.response.send_message("❌ Voice channel no longer exists!", ephemeral=True)
                return
            
            await self.voice_channel.set_permissions(interaction.guild.default_role, connect=True)
            await interaction.response.send_message("🔓 Room unlocked!", ephemeral=True)
            await self.send_log(interaction.guild, f"🔓 {interaction.user.mention} unlocked **{self.voice_channel.name}**")
            
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to unlock this room!", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ Failed to unlock room: {str(e)}", ephemeral=True)
        except Exception as e:
            logger.error(f"Unexpected error in unlock_room: {e}")
            await interaction.response.send_message("❌ An unexpected error occurred!", ephemeral=True)

    @ui.button(label="Rename Room", style=discord.ButtonStyle.primary, emoji="✏️")
    async def rename_room(self, interaction: discord.Interaction, button: ui.Button):
        try:
            if not self.voice_channel:
                await interaction.response.send_message("❌ Voice channel no longer exists!", ephemeral=True)
                return
            await interaction.response.send_modal(RenameModal(self.voice_channel))
        except Exception as e:
            logger.error(f"Error showing rename modal: {e}")
            await interaction.response.send_message("❌ Failed to open rename dialog!", ephemeral=True)

    @ui.button(label="Kick User", style=discord.ButtonStyle.secondary, emoji="🦶")
    async def kick_user(self, interaction: discord.Interaction, button: ui.Button):
        try:
            if not self.voice_channel:
                await interaction.response.send_message("❌ Voice channel no longer exists!", ephemeral=True)
                return
            
            if len(self.voice_channel.members) == 0:
                await interaction.response.send_message("❌ No users in the room to kick!", ephemeral=True)
                return
            
            await interaction.response.send_modal(KickModal(self.voice_channel))
        except Exception as e:
            logger.error(f"Error showing kick modal: {e}")
            await interaction.response.send_message("❌ Failed to open kick dialog!", ephemeral=True)

    @ui.button(label="End Room", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def end_room(self, interaction: discord.Interaction, button: ui.Button):
        try:
            if not self.voice_channel:
                await interaction.response.send_message("❌ Voice channel no longer exists!", ephemeral=True)
                return
            
            channel_name = self.voice_channel.name
            await self.send_log(interaction.guild, f"🗑️ {interaction.user.mention} ended room **{channel_name}**")
            await interaction.response.send_message("Room deleted 🗑️", ephemeral=True)
            
            cog = self.bot.get_cog("RoomSystem")
            if cog and cog.db_manager:
                cog.db_manager.execute_with_retry("DELETE FROM rooms WHERE channel_id = ?", (self.voice_channel.id,))
            
            await self.voice_channel.delete()
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to delete this room!", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ Failed to delete room: {str(e)}", ephemeral=True)
        except Exception as e:
            logger.error(f"Unexpected error in end_room: {e}")
            try:
                await interaction.response.send_message("❌ An unexpected error occurred!", ephemeral=True)
            except:
                pass


class RenameModal(ui.Modal, title="Rename Your Room"):
    new_name = ui.TextInput(label="New Room Name", placeholder="Enter new room name...", max_length=MAX_ROOM_NAME_LENGTH, min_length=1)

    def __init__(self, voice_channel):
        super().__init__()
        self.voice_channel = voice_channel

    async def on_submit(self, interaction: discord.Interaction):
        try:
            new_name = self.new_name.value.strip()
            if not new_name:
                await interaction.response.send_message("❌ Room name cannot be empty!", ephemeral=True)
                return
            
            forbidden_words = ['@everyone', '@here', 'discord.gg']
            if any(word in new_name.lower() for word in forbidden_words):
                await interaction.response.send_message("❌ Room name contains forbidden content!", ephemeral=True)
                return
            
            await self.voice_channel.edit(name=f"🎮│{new_name}")
            await interaction.response.send_message(f"✅ Room renamed to **{new_name}**", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to rename this room!", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ Failed to rename room: {str(e)}", ephemeral=True)
        except Exception as e:
            logger.error(f"Unexpected error in rename modal: {e}")
            await interaction.response.send_message("❌ An unexpected error occurred!", ephemeral=True)


class KickModal(ui.Modal, title="Kick a User From Room"):
    member_name = ui.TextInput(label="Enter username to kick", placeholder="e.g. @User or username")

    def __init__(self, voice_channel):
        super().__init__()
        self.voice_channel = voice_channel

    async def on_submit(self, interaction: discord.Interaction):
        try:
            search_name = self.member_name.value.strip().replace("@", "").lower()
            if not search_name:
                await interaction.response.send_message("❌ Please enter a valid username!", ephemeral=True)
                return
            
            member = None
            for m in self.voice_channel.members:
                if m.name.lower() == search_name or m.display_name.lower() == search_name or str(m.id) == search_name:
                    member = m
                    break
            
            if not member:
                await interaction.response.send_message(f"❌ User '{self.member_name.value}' not found in this room!", ephemeral=True)
                return
            
            if member.id == interaction.user.id:
                await interaction.response.send_message("❌ You cannot kick yourself! Use 'End Room' instead.", ephemeral=True)
                return
            
            await member.move_to(None)
            await interaction.response.send_message(f"🦶 {member.mention} kicked from the room!", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to kick users!", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ Failed to kick user: {str(e)}", ephemeral=True)
        except Exception as e:
            logger.error(f"Unexpected error in kick modal: {e}")
            await interaction.response.send_message("❌ An unexpected error occurred!", ephemeral=True)


class RoomSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_manager = DatabaseManager()
        self.cleanup_rooms.start()

    def cog_unload(self):
        self.cleanup_rooms.cancel()
        self.db_manager.close()

    def check_bot_permissions(self, guild: discord.Guild) -> dict:
        bot_member = guild.me
        permissions = bot_member.guild_permissions
        return {
            'manage_channels': permissions.manage_channels,
            'manage_roles': permissions.manage_roles,
            'move_members': permissions.move_members,
            'mute_members': permissions.mute_members,
            'deafen_members': permissions.deafen_members,
            'view_channel': permissions.view_channel,
            'send_messages': permissions.send_messages,
            'administrator': permissions.administrator
        }

    async def create_creator_channel(self, guild: discord.Guild, category: discord.CategoryChannel) -> Optional[discord.VoiceChannel]:
        try:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=True, connect=True, speak=False),
                guild.me: discord.PermissionOverwrite(view_channel=True, manage_channels=True, move_members=True, connect=True)
            }
            creator_channel = await guild.create_voice_channel(
                CREATOR_CHANNEL_NAME,
                category=category,
                overwrites=overwrites,
                user_limit=0,
                reason="Room creator channel for Lexus Room System"
            )
            logger.info(f"Created creator channel in {guild.name}")
            return creator_channel
        except Exception as e:
            logger.error(f"Failed to create creator channel: {e}")
            return None

    async def get_or_create_category(self, guild: discord.Guild) -> Optional[discord.CategoryChannel]:
        try:
            perms = self.check_bot_permissions(guild)
            if not perms['manage_channels'] and not perms['administrator']:
                logger.error(f"Bot lacks Manage Channels permission in {guild.name}")
                return None
            
            category = discord.utils.get(guild.categories, name="🎮 Game Rooms")
            
            if not category:
                if len(guild.channels) >= 500:
                    logger.error(f"Guild {guild.name} has reached channel limit")
                    return None
                
                category = await guild.create_category("🎮 Game Rooms", reason="Auto-created by Lexus Room System")
                await category.set_permissions(guild.default_role, manage_channels=False, view_channel=True)
                
                if not perms['administrator']:
                    await category.set_permissions(guild.me, manage_channels=True, manage_permissions=True, manage_roles=True, move_members=True, mute_members=True, deafen_members=True, view_channel=True, connect=True)
                
                if perms['manage_roles'] or perms['administrator']:
                    for role in guild.roles:
                        if role.permissions.administrator:
                            try:
                                await category.set_permissions(role, manage_channels=True, manage_permissions=True, view_channel=True)
                            except discord.Forbidden:
                                pass
                
                logger.info(f"Created category in {guild.name}")
                await self.create_creator_channel(guild, category)
            else:
                creator_channel = discord.utils.get(category.voice_channels, name=CREATOR_CHANNEL_NAME)
                if not creator_channel:
                    await self.create_creator_channel(guild, category)
            
            return category
        except Exception as e:
            logger.error(f"Unexpected error creating category: {e}")
            return None

    async def get_log_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        try:
            log_channel = discord.utils.get(guild.text_channels, name="room-logs")
            if not log_channel:
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(send_messages=False, view_channel=True),
                    guild.me: discord.PermissionOverwrite(send_messages=True, view_channel=True, manage_channels=True)
                }
                log_channel = await guild.create_text_channel("room-logs", overwrites=overwrites, reason="Auto-created for Lexus Room System logs")
                logger.info(f"Created log channel in {guild.name}")
            return log_channel
        except Exception as e:
            logger.error(f"Error getting/creating log channel: {e}")
            return None

    def get_user_room_count(self, user_id: int, guild_id: int) -> int:
        try:
            result = self.db_manager.fetch_with_retry("SELECT COUNT(*) FROM rooms WHERE owner_id = ? AND guild_id = ?", (user_id, guild_id))
            return result[0][0] if result else 0
        except Exception as e:
            logger.error(f"Error getting user room count: {e}")
            return 0

    async def create_room_for_user(self, user: discord.Member, guild: discord.Guild, send_controls_dm: bool = False) -> Optional[discord.VoiceChannel]:
        try:
            perms = self.check_bot_permissions(guild)
            
            if not perms['manage_channels'] and not perms['administrator']:
                raise Exception("I need **Manage Channels** permission to create rooms!")
            
            if not perms['move_members'] and not perms['administrator']:
                raise Exception("I need **Move Members** permission to manage rooms!")
            
            user_rooms = self.get_user_room_count(user.id, guild.id)
            if user_rooms >= MAX_ROOMS_PER_USER:
                raise ValueError(f"You can only have {MAX_ROOMS_PER_USER} active rooms at a time!")
            
            category = await self.get_or_create_category(guild)
            if not category:
                raise Exception("Failed to create or access category")
            
            if len(category.channels) >= 50:
                raise ValueError("Room category is full! Please contact an administrator.")
            
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False, connect=False),
                user: discord.PermissionOverwrite(view_channel=True, connect=True, speak=True, stream=True, use_voice_activation=True),
                guild.me: discord.PermissionOverwrite(view_channel=True, manage_channels=True, manage_permissions=True, move_members=True, mute_members=True, deafen_members=True, connect=True, speak=True)
            }

            voice_channel = await guild.create_voice_channel(f"🎮│{user.name}'s Room", overwrites=overwrites, category=category, reason=f"Private room created for {user.name}")
            
            control_embed = discord.Embed(
                title=f"🎮 {user.name}'s Room Controls",
                description=f"Use the buttons below to manage your private room.\n\n**⚠️ Auto-Delete:** Room will be deleted after {CLEANUP_DELAY_MINUTES} minutes of inactivity.",
                color=discord.Color.green()
            )
            control_embed.add_field(name="🔒 Lock/Unlock", value="Control who can join your room", inline=True)
            control_embed.add_field(name="✏️ Rename", value="Change your room name", inline=True)
            control_embed.add_field(name="🦶 Kick", value="Remove unwanted users", inline=True)
            control_embed.set_footer(text="Lexus Room System")
            
            view = RoomButtons(self.bot, user.id, voice_channel)
            
            if send_controls_dm:
                try:
                    await user.send(f"✅ Your room **{voice_channel.name}** has been created!\nJoin it here: {voice_channel.mention}", embed=control_embed, view=view)
                except discord.Forbidden:
                    try:
                        control_thread = await voice_channel.create_thread(name="Room Controls", auto_archive_duration=60)
                        await control_thread.send(embed=control_embed, view=view)
                    except:
                        pass
            else:
                try:
                    control_thread = await voice_channel.create_thread(name="Room Controls", auto_archive_duration=60)
                    await control_thread.send(embed=control_embed, view=view)
                except:
                    try:
                        await user.send(embed=control_embed, view=view)
                    except:
                        pass

            now = datetime.now().isoformat()
            self.db_manager.execute_with_retry("INSERT OR REPLACE INTO rooms (channel_id, owner_id, created_at, last_active, guild_id) VALUES (?, ?, ?, ?, ?)", (voice_channel.id, user.id, now, now, guild.id))

            log_channel = await self.get_log_channel(guild)
            if log_channel:
                try:
                    await log_channel.send(f"✅ {user.mention} created room **{voice_channel.name}** at <t:{int(datetime.now().timestamp())}:f>")
                except:
                    pass

            logger.info(f"Room created: {voice_channel.name} for {user.name}")
            return voice_channel
        except ValueError as e:
            raise
        except Exception as e:
            logger.error(f"Unexpected error creating room: {e}")
            raise Exception(str(e) if "permission" in str(e).lower() else "An unexpected error occurred!")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        try:
            if member.bot:
                return
            
            if after.channel and not before.channel:
                if after.channel.name == CREATOR_CHANNEL_NAME:
                    logger.info(f"{member.name} joined creator channel")
                    
                    try:
                        voice_channel = await self.create_room_for_user(member, member.guild, send_controls_dm=True)
                        
                        if voice_channel:
                            try:
                                await member.move_to(voice_channel)
                            except discord.Forbidden:
                                try:
                                    await member.send(f"⚠️ I couldn't move you automatically. Please join your room manually: {voice_channel.mention}")
                                except:
                                    pass
                    except ValueError as e:
                        try:
                            await member.send(f"❌ {str(e)}")
                            await member.move_to(None)
                        except:
                            pass
                    except Exception as e:
                        logger.error(f"Error creating room for {member.name}: {e}")
                        try:
                            await member.send(f"❌ Failed to create room: {str(e)}\nPlease try again or contact an administrator.")
                            await member.move_to(None)
                        except:
                            pass
        except Exception as e:
            logger.error(f"Error in on_voice_state_update: {e}")

    @app_commands.command(name="setup_room_panel", description="Create the main Game Room Creator panel")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_room_panel(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            
            perms = self.check_bot_permissions(interaction.guild)
            missing_perms = []
            if not perms['manage_channels'] and not perms['administrator']:
                missing_perms.append("Manage Channels")
            if not perms['move_members'] and not perms['administrator']:
                missing_perms.append("Move Members")
            
            warning_text = f"\n\n⚠️ **Warning:** Bot is missing permissions:\n• {', '.join(missing_perms)}\nRoom creation may fail without these permissions!" if missing_perms else ""
            
            category = await self.get_or_create_category(interaction.guild)
            
            embed = discord.Embed(
                title="🎮 Create Your Game Room",
                description=(
                    f"**Two ways to create your room:**\n\n"
                    f"**Method 1:** Join the **{CREATOR_CHANNEL_NAME}** voice channel\n"
                    f"• Instant room creation\n• Auto-moved to your room\n• Controls sent via DM\n\n"
                    f"**Method 2:** Click the button below\n"
                    f"• Manual room creation\n• Controls in voice channel thread\n\n"
                    f"**Features:**\n• 🔒 Lock/Unlock your room\n• ✏️ Rename your room\n• 🦶 Kick users\n• 🗑️ End room anytime\n• ⏰ Auto-cleanup after {CLEANUP_DELAY_MINUTES} minutes of inactivity{warning_text}"
                ),
                color=discord.Color.blurple() if not missing_perms else discord.Color.orange()
            )
            embed.set_footer(text="Lexus Room System • Secure & Easy")

            view = ui.View(timeout=None)
            view.add_item(CreateRoomButton(self.bot))
            
            await interaction.channel.send(embed=embed, view=view)
            
            success_msg = "✅ Room Creator panel created successfully!"
            if category:
                creator_channel = discord.utils.get(category.voice_channels, name=CREATOR_CHANNEL_NAME)
                if creator_channel:
                    success_msg += f"\n\n🎤 Creator channel: {creator_channel.mention}"
            
            if missing_perms:
                success_msg += f"\n\n⚠️ **Bot is missing permissions:**\n• {', '.join(missing_perms)}\n\nPlease grant these permissions for full functionality."
            
            await interaction.followup.send(success_msg, ephemeral=True)
        except Exception as e:
            logger.error(f"Error in setup_room_panel: {e}")
            try:
                await interaction.followup.send("❌ An unexpected error occurred!", ephemeral=True)
            except:
                pass

    @tasks.loop(minutes=1)
    async def cleanup_rooms(self):
        try:
            now = datetime.now()
            rooms = self.db_manager.fetch_with_retry("SELECT channel_id, last_active, guild_id FROM rooms")
            
            for channel_id, last_active, guild_id in rooms:
                try:
                    channel = self.bot.get_channel(channel_id)
                    if not channel:
                        try:
                            channel = await self.bot.fetch_channel(channel_id)
                        except discord.NotFound:
                            self.db_manager.execute_with_retry("DELETE FROM rooms WHERE channel_id = ?", (channel_id,))
                            continue
                        except:
                            continue
                    
                    if not isinstance(channel, discord.VoiceChannel):
                        continue

                    if len(channel.members) > 0:
                        self.db_manager.execute_with_retry("UPDATE rooms SET last_active = ? WHERE channel_id = ?", (datetime.now().isoformat(), channel_id))
                        continue

                    last_active_time = datetime.fromisoformat(last_active)
                    if now - last_active_time > timedelta(minutes=CLEANUP_DELAY_MINUTES):
                        log_channel = discord.utils.get(channel.guild.text_channels, name="room-logs")
                        if log_channel:
                            try:
                                await log_channel.send(f"⏰ Auto-deleting **{channel.name}** (inactive for {CLEANUP_DELAY_MINUTES} mins)")
                            except:
                                pass

                        try:
                            await channel.delete(reason="Auto-cleanup: inactive room")
                        except:
                            pass

                        self.db_manager.execute_with_retry("DELETE FROM rooms WHERE channel_id = ?", (channel_id,))
                except:
                    continue
        except Exception as e:
            logger.error(f"Critical error in cleanup_rooms: {e}")

    @cleanup_rooms.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()


class CreateRoomButton(ui.Button):
    def __init__(self, bot):
        super().__init__(label="🎮 Create Room", style=discord.ButtonStyle.primary, custom_id="persistent_create_room")
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            cog = self.bot.get_cog("RoomSystem")
            if not cog:
                await interaction.followup.send("❌ Room system is not available!", ephemeral=True)
                return
            
            voice_channel = await cog.create_room_for_user(interaction.user, interaction.guild, send_controls_dm=False)
            
            if voice_channel:
                await interaction.followup.send(f"✅ Room created: {voice_channel.mention}\nJoin the voice channel to start using it!", ephemeral=True)
            else:
                await interaction.followup.send("❌ Failed to create room. Please try again later.", ephemeral=True)
                
        except ValueError as e:
            await interaction.followup.send(f"❌ {str(e)}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in CreateRoomButton callback: {e}")
            await interaction.followup.send(f"❌ {str(e)}", ephemeral=True)


async def setup(bot):
    """Setup function to add cog to bot"""
    try:
        await bot.add_cog(RoomSystem(bot))
        logger.info("RoomSystem cog loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load RoomSystem cog: {e}")
        raise
