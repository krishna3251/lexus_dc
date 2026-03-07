import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import logging
from typing import Optional, List, Dict, Any
import random

class Quarantine(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Enhanced in-memory config with additional safety features
        self.config: Dict[int, Dict[str, Any]] = {}
        self.quarantine_cooldowns: Dict[tuple, float] = {}  # (guild_id, user_id) -> timestamp
        self.setup_logging()
        
        # Sarcastic responses for various situations
        self.sarcastic_responses = {
            'quarantine_success': [
                "🚫 {user} just earned themselves a timeout! Congratulations on finding the forbidden zone! 🎉",
                "🚫 Well, well, well... {user} decided to test the waters and got quarantined! How original! 🙄",
                "🚫 {user} has been yeeted into quarantine! Maybe next time read the room? 📚",
                "🚫 Aaaand {user} is quarantined! Another brilliant strategist bites the dust! 🧠",
                "🚫 {user} just triggered the anti-fun protocol! Welcome to timeout town! 🏘️",
                "🚫 {user} found the 'click here to get quarantined' button! Mission accomplished! 🎯"
            ],
            'permission_denied': [
                "⚠️ I'd love to quarantine people, but apparently I need permissions first. Who knew? 🤷‍♀️",
                "⚠️ Permission denied! I'm not a wizard, I can't just magically assign roles without proper permissions! 🪄",
                "⚠️ Looks like someone forgot to give me the keys to the quarantine castle! 🏰",
                "⚠️ Error 403: Forbidden! I'm not allowed to play the role police without proper authorization! 👮‍♀️"
            ],
            'already_quarantined': [
                "{user} is already quarantined! No need to double-dip in the timeout sauce! 🥫",
                "Trying to quarantine {user} again? They're already in timeout! Efficiency, my friend! ⚡",
                "{user} is already enjoying their quarantine vacation! No need for an extension! 🏖️"
            ],
            'no_config': [
                "⚠️ No quarantine setup found! It's like trying to catch fish without a net! 🎣",
                "⚠️ Quarantine system not configured! Even I can't work miracles without setup! ✨",
                "⚠️ No quarantine role set! I'm not a mind reader, you know! 🔮"
            ]
        }

    def setup_logging(self):
        """Setup logging for better error tracking"""
        self.logger = logging.getLogger(f'{__name__}.{self.__class__.__name__}')
        
    def get_guild_config(self, guild_id: int) -> Dict[str, Any]:
        """Get or create guild configuration with enhanced structure"""
        return self.config.setdefault(guild_id, {
            "role": None, 
            "channels": [], 
            "enabled": True,
            "auto_delete": True,
            "cooldown": 5,  # seconds
            "max_warnings": 3,
            "warning_count": {}  # user_id -> count
        })

    def get_random_response(self, category: str, **kwargs) -> str:
        """Get a random sarcastic response from the specified category"""
        responses = self.sarcastic_responses.get(category, ["Generic sarcastic response! 😏"])
        response = random.choice(responses)
        return response.format(**kwargs)

    async def check_permissions(self, guild: discord.Guild, required_perms: List[str]) -> tuple[bool, List[str]]:
        """Check if bot has required permissions"""
        bot_member = guild.get_member(self.bot.user.id)
        if not bot_member:
            return False, ["Bot not found in guild"]
            
        missing_perms = []
        permissions = bot_member.guild_permissions
        
        perm_map = {
            'manage_roles': permissions.manage_roles,
            'manage_messages': permissions.manage_messages,
            'send_messages': permissions.send_messages,
            'embed_links': permissions.embed_links
        }
        
        for perm in required_perms:
            if perm in perm_map and not perm_map[perm]:
                missing_perms.append(perm.replace('_', ' ').title())
                
        return len(missing_perms) == 0, missing_perms

    def is_on_cooldown(self, guild_id: int, user_id: int) -> bool:
        """Check if user is on quarantine cooldown"""
        key = (guild_id, user_id)
        if key in self.quarantine_cooldowns:
            import time
            return time.time() - self.quarantine_cooldowns[key] < self.get_guild_config(guild_id)["cooldown"]
        return False

    def set_cooldown(self, guild_id: int, user_id: int):
        """Set quarantine cooldown for user"""
        import time
        self.quarantine_cooldowns[(guild_id, user_id)] = time.time()

    # --- Enhanced Slash Commands ---
    
    @app_commands.command(name="setquarantine", description="Set the quarantine role for this server")
    @app_commands.describe(role="The role to assign when quarantining users")
    async def setquarantine(self, interaction: discord.Interaction, role: discord.Role):
        """Set quarantine role with enhanced validation"""
        try:
            # Permission checks
            if not interaction.user.guild_permissions.manage_roles:
                await interaction.response.send_message(
                    "❌ You need 'Manage Roles' permission to configure quarantine! Nice try though! 😏", 
                    ephemeral=True
                )
                return

            # Bot permission checks
            has_perms, missing = await self.check_permissions(interaction.guild, ['manage_roles'])
            if not has_perms:
                await interaction.response.send_message(
                    f"❌ I need the following permissions: {', '.join(missing)}. "
                    f"Fix my permissions and try again! I'm not a miracle worker! 🔧", 
                    ephemeral=True
                )
                return

            # Role hierarchy check
            bot_member = interaction.guild.get_member(self.bot.user.id)
            if role.position >= bot_member.top_role.position:
                await interaction.response.send_message(
                    f"❌ That role ({role.mention}) is too high in the hierarchy! "
                    f"I can't assign roles above my own rank. I'm not *that* powerful! 💪", 
                    ephemeral=True
                )
                return

            guild_cfg = self.get_guild_config(interaction.guild.id)
            old_role = interaction.guild.get_role(guild_cfg["role"]) if guild_cfg["role"] else None
            guild_cfg["role"] = role.id
            
            response = f"✅ Quarantine role updated to {role.mention}! "
            if old_role:
                response += f"(Previously: {old_role.mention}) "
            response += "Now we're cooking with gas! 🔥"
            
            await interaction.response.send_message(response, ephemeral=True)
            self.logger.info(f"Quarantine role set to {role.name} in guild {interaction.guild.name}")
            
        except Exception as e:
            await interaction.response.send_message(
                "❌ Something went wrong! Even I can't fix everything... yet! 🤖", 
                ephemeral=True
            )
            self.logger.error(f"Error in setquarantine: {e}")

    @app_commands.command(name="addquarantinechannel", description="Add a channel that triggers quarantine")
    @app_commands.describe(channel="Channel where messages will trigger quarantine")
    async def addquarantinechannel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Add quarantine trigger channel with validation"""
        try:
            if not interaction.user.guild_permissions.manage_channels:
                await interaction.response.send_message(
                    "❌ You need 'Manage Channels' permission! I don't take orders from just anyone! 👑", 
                    ephemeral=True
                )
                return

            guild_cfg = self.get_guild_config(interaction.guild.id)
            
            if channel.id in guild_cfg["channels"]:
                await interaction.response.send_message(
                    f"⚠️ {channel.mention} is already a quarantine trigger! "
                    f"No need to be redundant! 🔄", 
                    ephemeral=True
                )
                return

            # Check bot permissions in the channel
            bot_perms = channel.permissions_for(interaction.guild.get_member(self.bot.user.id))
            if not (bot_perms.read_messages and bot_perms.manage_messages):
                await interaction.response.send_message(
                    f"⚠️ I need 'Read Messages' and 'Manage Messages' permissions in {channel.mention}! "
                    f"Can't quarantine what I can't see or manage! 👀", 
                    ephemeral=True
                )
                return

            guild_cfg["channels"].append(channel.id)
            await interaction.response.send_message(
                f"✅ Added {channel.mention} as a quarantine trigger! "
                f"Another trap has been set! 🪤", 
                ephemeral=True
            )
            self.logger.info(f"Added quarantine channel {channel.name} in guild {interaction.guild.name}")
            
        except Exception as e:
            await interaction.response.send_message(
                "❌ Failed to add channel! Technology is hard sometimes! 💻", 
                ephemeral=True
            )
            self.logger.error(f"Error in addquarantinechannel: {e}")

    @app_commands.command(name="removequarantinechannel", description="Remove a quarantine trigger channel")
    @app_commands.describe(channel="Channel to remove from quarantine triggers")
    async def removequarantinechannel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Remove quarantine trigger channel"""
        try:
            if not interaction.user.guild_permissions.manage_channels:
                await interaction.response.send_message(
                    "❌ You need 'Manage Channels' permission! I'm picky about who I listen to! 🎭", 
                    ephemeral=True
                )
                return

            guild_cfg = self.get_guild_config(interaction.guild.id)
            
            if channel.id in guild_cfg["channels"]:
                guild_cfg["channels"].remove(channel.id)
                await interaction.response.send_message(
                    f"✅ Removed {channel.mention} from quarantine triggers! "
                    f"One less trap in the maze! 🌀", 
                    ephemeral=True
                )
                self.logger.info(f"Removed quarantine channel {channel.name} in guild {interaction.guild.name}")
            else:
                await interaction.response.send_message(
                    f"⚠️ {channel.mention} wasn't a quarantine trigger anyway! "
                    f"You're trying to remove something that doesn't exist! 🤔", 
                    ephemeral=True
                )
                
        except Exception as e:
            await interaction.response.send_message(
                "❌ Failed to remove channel! Even simple things can go wrong! 🤷‍♀️", 
                ephemeral=True
            )
            self.logger.error(f"Error in removequarantinechannel: {e}")

    @app_commands.command(name="quarantineconfig", description="Configure advanced quarantine settings")
    @app_commands.describe(
        auto_delete="Whether to auto-delete messages in quarantine channels",
        cooldown="Cooldown between quarantine triggers (seconds)",
        enabled="Enable or disable the quarantine system"
    )
    async def quarantineconfig(self, interaction: discord.Interaction, 
                              auto_delete: Optional[bool] = None, 
                              cooldown: Optional[int] = None,
                              enabled: Optional[bool] = None):
        """Advanced configuration for quarantine system"""
        try:
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message(
                    "❌ You need Administrator permission for advanced config! "
                    "This isn't amateur hour! 🎪", 
                    ephemeral=True
                )
                return

            guild_cfg = self.get_guild_config(interaction.guild.id)
            changes = []

            if auto_delete is not None:
                guild_cfg["auto_delete"] = auto_delete
                changes.append(f"Auto-delete: {auto_delete}")

            if cooldown is not None:
                if cooldown < 0 or cooldown > 300:
                    await interaction.response.send_message(
                        "❌ Cooldown must be between 0 and 300 seconds! "
                        "Let's be reasonable here! ⏰", 
                        ephemeral=True
                    )
                    return
                guild_cfg["cooldown"] = cooldown
                changes.append(f"Cooldown: {cooldown}s")

            if enabled is not None:
                guild_cfg["enabled"] = enabled
                changes.append(f"System: {'Enabled' if enabled else 'Disabled'}")

            if not changes:
                await interaction.response.send_message(
                    "⚠️ No changes specified! You called me for nothing! 🙄", 
                    ephemeral=True
                )
                return

            await interaction.response.send_message(
                f"✅ Configuration updated!\n**Changes:** {', '.join(changes)}\n"
                f"The quarantine machine has been fine-tuned! 🔧", 
                ephemeral=True
            )
            
        except Exception as e:
            await interaction.response.send_message(
                "❌ Configuration failed! Even robots make mistakes! 🤖💥", 
                ephemeral=True
            )
            self.logger.error(f"Error in quarantineconfig: {e}")

    @app_commands.command(name="quarantineinfo", description="Show current quarantine settings")
    async def quarantineinfo(self, interaction: discord.Interaction):
        """Display comprehensive quarantine information"""
        try:
            guild_cfg = self.get_guild_config(interaction.guild.id)
            role = interaction.guild.get_role(guild_cfg["role"]) if guild_cfg["role"] else None
            channels = [interaction.guild.get_channel(c) for c in guild_cfg["channels"] if interaction.guild.get_channel(c)]
            
            embed = discord.Embed(
                title=f"🚫 Quarantine Settings for {interaction.guild.name}",
                color=0xFF6B6B,
                description="Current configuration of the quarantine system (because you asked so nicely! 😏)"
            )
            
            embed.add_field(
                name="🎭 Quarantine Role", 
                value=role.mention if role else "❌ Not Set (How do you expect this to work?)", 
                inline=False
            )
            
            embed.add_field(
                name="📺 Trigger Channels", 
                value="\n".join([f"• {ch.mention}" for ch in channels]) if channels else "❌ None (Boring!)", 
                inline=False
            )
            
            embed.add_field(name="⚙️ System Status", value="✅ Enabled" if guild_cfg["enabled"] else "❌ Disabled", inline=True)
            embed.add_field(name="🗑️ Auto Delete", value="✅ Yes" if guild_cfg["auto_delete"] else "❌ No", inline=True)
            embed.add_field(name="⏰ Cooldown", value=f"{guild_cfg['cooldown']}s", inline=True)
            
            # Permission status
            has_perms, missing = await self.check_permissions(interaction.guild, ['manage_roles', 'manage_messages'])
            embed.add_field(
                name="🔑 Bot Permissions", 
                value="✅ All Good!" if has_perms else f"❌ Missing: {', '.join(missing)}", 
                inline=False
            )
            
            embed.set_footer(text="Pro tip: Make sure everything is configured properly! 💡")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                "❌ Couldn't fetch info! The information gremlins are acting up! 👹", 
                ephemeral=True
            )
            self.logger.error(f"Error in quarantineinfo: {e}")

    @app_commands.command(name="unquarantine", description="Remove quarantine role from a user")
    @app_commands.describe(user="User to remove from quarantine")
    async def unquarantine(self, interaction: discord.Interaction, user: discord.Member):
        """Manually remove quarantine role from user"""
        try:
            if not interaction.user.guild_permissions.manage_roles:
                await interaction.response.send_message(
                    "❌ You need 'Manage Roles' permission! I don't grant pardons to just anyone! 👨‍⚖️", 
                    ephemeral=True
                )
                return

            guild_cfg = self.get_guild_config(interaction.guild.id)
            role = interaction.guild.get_role(guild_cfg["role"]) if guild_cfg["role"] else None
            
            if not role:
                await interaction.response.send_message(
                    "❌ No quarantine role configured! Can't free someone from a prison that doesn't exist! 🏛️", 
                    ephemeral=True
                )
                return

            if role not in user.roles:
                await interaction.response.send_message(
                    f"⚠️ {user.mention} isn't quarantined! You're trying to free someone who's already free! 🕊️", 
                    ephemeral=True
                )
                return

            await user.remove_roles(role, reason=f"Unquarantined by {interaction.user}")
            
            # Reset warning count
            if user.id in guild_cfg["warning_count"]:
                del guild_cfg["warning_count"][user.id]
            
            await interaction.response.send_message(
                f"✅ {user.mention} has been freed from quarantine! "
                f"They've served their time! ⏰", 
                ephemeral=True
            )
            
            # Send notification to the channel
            try:
                await interaction.followup.send(
                    f"🎉 {user.mention} has been released from quarantine! "
                    f"Welcome back to civilization! 🏙️"
                )
            except:
                pass  # If we can't send follow-up, that's okay
                
        except discord.Forbidden:
            await interaction.response.send_message(
                self.get_random_response('permission_denied'), 
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                "❌ Failed to unquarantine user! Even freedom has bugs sometimes! 🐛", 
                ephemeral=True
            )
            self.logger.error(f"Error in unquarantine: {e}")

    # --- Enhanced Event Listener ---
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Enhanced message listener with robust error handling"""
        # Basic checks
        if not message.guild or message.author.bot:
            return
            
        try:
            guild_cfg = self.get_guild_config(message.guild.id)
            
            # Check if system is enabled
            if not guild_cfg.get("enabled", True):
                return
                
            role_id = guild_cfg.get("role")
            channels = guild_cfg.get("channels", [])
            
            if not role_id or not channels or message.channel.id not in channels:
                return

            # Get role and validate
            role = message.guild.get_role(role_id)
            if not role:
                self.logger.warning(f"Quarantine role {role_id} not found in guild {message.guild.name}")
                return

            # Check if user is already quarantined
            if role in message.author.roles:
                if guild_cfg.get("auto_delete", True):
                    try:
                        await message.delete()
                        # Send temporary message
                        temp_msg = await message.channel.send(
                            self.get_random_response('already_quarantined', user=message.author.mention)
                        )
                        await asyncio.sleep(5)
                        await temp_msg.delete()
                    except discord.Forbidden:
                        pass
                return

            # Check cooldown
            if self.is_on_cooldown(message.guild.id, message.author.id):
                return

            # Permission checks
            has_perms, missing = await self.check_permissions(message.guild, ['manage_roles'])
            if not has_perms:
                self.logger.error(f"Missing permissions in {message.guild.name}: {missing}")
                return

            # Role hierarchy check
            bot_member = message.guild.get_member(self.bot.user.id)
            if role.position >= bot_member.top_role.position:
                self.logger.error(f"Quarantine role too high in hierarchy in {message.guild.name}")
                return

            # Apply quarantine
            try:
                await message.author.add_roles(role, reason="Triggered quarantine channel")
                self.set_cooldown(message.guild.id, message.author.id)
                
                # Delete message if configured
                if guild_cfg.get("auto_delete", True):
                    await message.delete()
                
                # Send sarcastic quarantine message
                quarantine_msg = await message.channel.send(
                    self.get_random_response('quarantine_success', user=message.author.mention)
                )
                
                # Auto-delete quarantine message after 10 seconds
                await asyncio.sleep(10)
                try:
                    await quarantine_msg.delete()
                except:
                    pass
                
                # Update warning count
                guild_cfg["warning_count"][message.author.id] = guild_cfg["warning_count"].get(message.author.id, 0) + 1
                
                # Log the quarantine
                self.logger.info(
                    f"Quarantined {message.author} ({message.author.id}) in {message.guild.name} "
                    f"for posting in {message.channel.name}"
                )
                
                # Send DM to quarantined user (optional)
                try:
                    embed = discord.Embed(
                        title="🚫 You've Been Quarantined!",
                        description=f"You've been quarantined in **{message.guild.name}** for posting in a restricted channel.",
                        color=0xFF6B6B
                    )
                    embed.add_field(
                        name="Why?", 
                        value=f"You posted in {message.channel.mention}, which triggers automatic quarantine.", 
                        inline=False
                    )
                    embed.add_field(
                        name="What now?", 
                        value="Contact a moderator to be released from quarantine.", 
                        inline=False
                    )
                    embed.set_footer(text="Next time, read the channel descriptions! 📖")
                    await message.author.send(embed=embed)
                except discord.Forbidden:
                    pass  # User has DMs disabled
                    
            except discord.Forbidden:
                # Send permission error message
                error_msg = await message.channel.send(self.get_random_response('permission_denied'))
                await asyncio.sleep(10)
                try:
                    await error_msg.delete()
                except:
                    pass
                self.logger.error(f"Forbidden to assign quarantine role in {message.guild.name}")
                
            except discord.HTTPException as e:
                self.logger.error(f"HTTP error during quarantine in {message.guild.name}: {e}")
                
        except Exception as e:
            self.logger.error(f"Unexpected error in quarantine listener: {e}")

    # --- Error Handling ---
    
    @setquarantine.error
    @addquarantinechannel.error
    @removequarantinechannel.error
    @quarantineinfo.error
    @quarantineconfig.error
    @unquarantine.error
    async def quarantine_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Global error handler for quarantine commands"""
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "❌ You don't have the required permissions! Nice try though! 😏", 
                ephemeral=True
            )
        elif isinstance(error, app_commands.BotMissingPermissions):
            await interaction.response.send_message(
                "❌ I don't have the required permissions! Fix that first! 🔧", 
                ephemeral=True
            )
        elif isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"⏰ Command on cooldown! Try again in {error.retry_after:.1f} seconds. Patience is a virtue! 🧘‍♀️", 
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ Something unexpected happened! Even I'm surprised! 🤯", 
                ephemeral=True
            )
            self.logger.error(f"Command error: {error}")

async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(Quarantine(bot))
    logging.getLogger().info("Quarantine cog loaded successfully with enhanced features!")
