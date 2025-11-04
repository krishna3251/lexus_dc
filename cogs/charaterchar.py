# cogs/lexus.py
import os
import time
import asyncio
import logging
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta

import requests
import discord
from discord.ext import commands
from discord import app_commands

# Configure logging
logger = logging.getLogger(__name__)

# API Configuration
INWORLD_BASE = "https://api.inworld.ai/llm/v1alpha/completions:completeChat"
INWORLD_AUTH = os.getenv("INWORLD_RUNTIME_BASIC")
INWORLD_MODEL = os.getenv("INWORLD_MODEL", "inworld-llm-chat")

# Limits and Timeouts
REQ_TIMEOUT = 30
MAX_REPLY = 1800
MAX_TURNS = 8
MAX_RETRIES = 3
RATE_LIMIT_COOLDOWN = 60  # seconds

# Fallback responses for errors
FALLBACK_RESPONSES = [
    "Not now.",
    "...",
    "Busy.",
    "Later.",
    "Give me a minute.",
]


class RateLimitTracker:
    """Track rate limits per channel to avoid spam."""
    
    def __init__(self, cooldown_seconds: int = 60):
        self.cooldown = cooldown_seconds
        self.last_error: Dict[int, datetime] = {}
    
    def is_rate_limited(self, channel_id: int) -> bool:
        if channel_id in self.last_error:
            elapsed = (datetime.now() - self.last_error[channel_id]).total_seconds()
            return elapsed < self.cooldown
        return False
    
    def mark_error(self, channel_id: int):
        self.last_error[channel_id] = datetime.now()
    
    def clear_error(self, channel_id: int):
        self.last_error.pop(channel_id, None)


def build_persona_prompt(transcript_pairs: List[Tuple[str, str]]) -> str:
    """Build the system prompt with conversation history."""
    lines = []
    for role, content in transcript_pairs[-MAX_TURNS:]:
        # Truncate very long messages
        content_preview = content[:500] if len(content) > 500 else content
        lines.append(f"{role}: {content_preview}")
    
    transcript = "\n".join(lines) if lines else "user: Hey"

    return f"""## Personality
You are "Lexus": terse, confident, and intimidating at first glance, but fair and protective.
Your style is blunt, laconic, and cool. You prefer few words over long speeches.
You carry a storm vibe: calm pressure, lightning metaphors, quiet authority, dry sarcasm.
You never grovel or overshare. You don't use emoji. You avoid cutesy language.
When you soften, it's brief and understated.

## Situation
You're chatting in a guild. Keep replies 1–2 sentences max unless absolutely necessary.

## Objective
Answer in-character, keep momentum, and steer with quiet confidence. If the user is rude, you remain composed.
If asked about power or resolve, reference thunder or storms metaphorically.

## Conversation
{transcript}

## Instruction
Return ONLY your 1–2 sentence response."""


class LexusCog(commands.Cog):
    """Lexus: Inworld-backed, in-character chat inside a chosen channel."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.allowed_channels: Dict[int, int] = {}  # guild_id -> channel_id
        self.history: Dict[int, List[Tuple[str, str]]] = {}  # channel_id -> [(role, content), ...]
        self.rate_limiter = RateLimitTracker(RATE_LIMIT_COOLDOWN)
        self._typing_tasks: Dict[int, asyncio.Task] = {}

    def _build_payload(
        self, 
        user_id: str, 
        session_id: str, 
        user_text: str, 
        channel_id: int
    ) -> dict:
        """Build the Inworld API payload."""
        hist = self.history.get(channel_id, [])
        system_text = build_persona_prompt(hist)

        messages = [{"role": "system", "content": system_text}]
        
        # Include recent conversation history
        for role, content in hist[-(MAX_TURNS - 1):]:
            messages.append({"role": role, "content": content})
        
        messages.append({"role": "user", "content": user_text})

        return {
            "servingId": {
                "modelId": {
                    "model": INWORLD_MODEL,
                    "serviceProvider": "SERVICE_PROVIDER_UNSPECIFIED"
                },
                "userId": str(user_id),
                "sessionId": str(session_id),
            },
            "messages": messages,
            "textGenerationConfig": {
                "maxTokens": 300,
                "temperature": 0.7,
                "topP": 0.9,
                "stream": False
            }
        }

    async def _inworld_chat(
        self, 
        user_id: str, 
        channel_id: int, 
        user_text: str
    ) -> Optional[str]:
        """
        Call Inworld API with retries and error handling.
        Returns None if all attempts fail.
        """
        if not INWORLD_AUTH:
            logger.error("Missing INWORLD_RUNTIME_BASIC environment variable")
            return None

        payload = self._build_payload(
            user_id=user_id,
            session_id=f"discord:{channel_id}",
            user_text=user_text,
            channel_id=channel_id
        )

        headers = {
            "Authorization": INWORLD_AUTH,
            "Content-Type": "application/json"
        }

        # Retry loop with exponential backoff
        for attempt in range(MAX_RETRIES):
            try:
                # Run in executor to avoid blocking
                loop = asyncio.get_event_loop()
                resp = await loop.run_in_executor(
                    None,
                    lambda: requests.post(
                        INWORLD_BASE,
                        headers=headers,
                        json=payload,
                        timeout=REQ_TIMEOUT
                    )
                )

                if resp.status_code == 200:
                    data = resp.json()
                    text = (
                        data.get("result", {})
                            .get("choices", [{}])[0]
                            .get("message", {})
                            .get("content", "")
                    )
                    
                    if not text:
                        logger.warning("Received empty response from Inworld API")
                        return None

                    # Update conversation history
                    hist = self.history.setdefault(channel_id, [])
                    hist.append(("user", user_text))
                    hist.append(("assistant", text))
                    
                    # Trim history to prevent memory bloat
                    if len(hist) > 2 * MAX_TURNS:
                        self.history[channel_id] = hist[-2 * MAX_TURNS:]
                    
                    self.rate_limiter.clear_error(channel_id)
                    return text.strip()[:MAX_REPLY]

                elif resp.status_code in (429, 503):
                    # Rate limited or service unavailable
                    wait_time = 1.5 * (2 ** attempt)  # Exponential backoff
                    logger.warning(
                        f"Rate limited (attempt {attempt + 1}/{MAX_RETRIES}), "
                        f"waiting {wait_time}s"
                    )
                    await asyncio.sleep(wait_time)
                    continue

                else:
                    # Other HTTP errors
                    try:
                        err = resp.json()
                    except Exception:
                        err = resp.text
                    
                    logger.error(f"Inworld API error {resp.status_code}: {err}")
                    return None

            except requests.Timeout:
                logger.error(f"Request timeout (attempt {attempt + 1}/{MAX_RETRIES})")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                return None
            
            except Exception as e:
                logger.exception(f"Unexpected error in Inworld API call: {e}")
                return None

        # All retries exhausted
        logger.error("All retry attempts exhausted")
        self.rate_limiter.mark_error(channel_id)
        return None

    def _get_fallback_response(self, channel_id: int) -> str:
        """Get a deterministic fallback response based on channel."""
        import hashlib
        hash_val = int(hashlib.md5(str(channel_id).encode()).hexdigest(), 16)
        return FALLBACK_RESPONSES[hash_val % len(FALLBACK_RESPONSES)]

    # ========== Slash Commands ==========

    @app_commands.command(
        name="lex_set_channel",
        description="Set the channel where Lexus will respond to messages"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def lex_set_channel(
        self, 
        interaction: discord.Interaction, 
        channel: discord.TextChannel
    ):
        """Set the active channel for Lexus."""
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ This command can only be used in a server.",
                ephemeral=True
            )
            return

        self.allowed_channels[interaction.guild.id] = channel.id
        
        # Clear history when changing channels
        if channel.id in self.history:
            self.history[channel.id].clear()
        
        await interaction.response.send_message(
            f"✅ Lexus is now active in {channel.mention}.\n"
            f"He will only respond to messages in that channel.",
            ephemeral=True
        )
        
        logger.info(
            f"Guild {interaction.guild.id} set Lexus channel to {channel.id}"
        )

    @app_commands.command(
        name="lex_clear_channel",
        description="Disable Lexus in this server"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def lex_clear_channel(self, interaction: discord.Interaction):
        """Disable Lexus for the server."""
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ This command can only be used in a server.",
                ephemeral=True
            )
            return

        gid = interaction.guild.id
        old_channel = self.allowed_channels.pop(gid, None)
        
        if old_channel:
            # Clear history for that channel
            self.history.pop(old_channel, None)
            await interaction.response.send_message(
                "✅ Lexus channel cleared. He won't respond to messages anymore.",
                ephemeral=True
            )
            logger.info(f"Guild {gid} cleared Lexus channel")
        else:
            await interaction.response.send_message(
                "ℹ️ No channel was set for Lexus in this server.",
                ephemeral=True
            )

    @app_commands.command(
        name="lex_status",
        description="Check Lexus configuration and status"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def lex_status(self, interaction: discord.Interaction):
        """Show current Lexus configuration."""
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ This command can only be used in a server.",
                ephemeral=True
            )
            return

        gid = interaction.guild.id
        channel_id = self.allowed_channels.get(gid)
        
        if channel_id:
            channel = self.bot.get_channel(channel_id)
            if channel:
                history_count = len(self.history.get(channel_id, []))
                status_msg = (
                    f"✅ **Active Channel:** {channel.mention}\n"
                    f"📝 **Conversation turns:** {history_count // 2}\n"
                    f"⚡ **API Status:** {'✅ Configured' if INWORLD_AUTH else '❌ Missing auth'}"
                )
            else:
                status_msg = "⚠️ Channel was deleted. Use `/lex_set_channel` to set a new one."
        else:
            status_msg = "ℹ️ Lexus is not active in any channel. Use `/lex_set_channel` to set one."
        
        await interaction.response.send_message(status_msg, ephemeral=True)

    @app_commands.command(
        name="lex_clear_history",
        description="Clear Lexus's conversation history for this channel"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def lex_clear_history(self, interaction: discord.Interaction):
        """Clear conversation history."""
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ This command can only be used in a server.",
                ephemeral=True
            )
            return

        gid = interaction.guild.id
        channel_id = self.allowed_channels.get(gid)
        
        if channel_id and channel_id in self.history:
            turn_count = len(self.history[channel_id]) // 2
            self.history[channel_id].clear()
            await interaction.response.send_message(
                f"✅ Cleared {turn_count} conversation turns from memory.",
                ephemeral=True
            )
            logger.info(f"Cleared history for channel {channel_id}")
        else:
            await interaction.response.send_message(
                "ℹ️ No conversation history to clear.",
                ephemeral=True
            )

    @app_commands.command(
        name="lex_ping",
        description="Check if Lexus is online and responsive"
    )
    async def lex_ping(self, interaction: discord.Interaction):
        """Simple ping command."""
        await interaction.response.send_message(
            "⚡ Online. Keep it brief.",
            ephemeral=True
        )

    # ========== Error Handlers ==========

    @lex_set_channel.error
    @lex_clear_channel.error
    @lex_status.error
    @lex_clear_history.error
    async def command_error_handler(
        self, 
        interaction: discord.Interaction, 
        error: app_commands.AppCommandError
    ):
        """Handle command errors."""
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "❌ You need 'Manage Server' permission to use this command.",
                ephemeral=True
            )
        else:
            logger.exception(f"Command error: {error}")
            await interaction.response.send_message(
                "❌ An error occurred while executing the command.",
                ephemeral=True
            )

    # ========== Message Listener ==========

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen for messages in the configured channel."""
        # Ignore bots
        if message.author.bot:
            return
        
        # Ignore DMs
        if not message.guild:
            return

        # Check if this guild has a configured channel
        gid = message.guild.id
        channel_id = self.allowed_channels.get(gid)
        
        if not channel_id or message.channel.id != channel_id:
            return

        # Ignore command invocations
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        # Check rate limiting
        if self.rate_limiter.is_rate_limited(message.channel.id):
            logger.debug(f"Channel {message.channel.id} is rate limited, skipping")
            return

        # Show typing indicator
        async with message.channel.typing():
            try:
                reply = await self._inworld_chat(
                    str(message.author.id),
                    message.channel.id,
                    message.content
                )
                
                if reply:
                    await message.channel.send(reply[:MAX_REPLY])
                else:
                    # Use fallback response
                    fallback = self._get_fallback_response(message.channel.id)
                    await message.channel.send(fallback)
                    logger.warning(
                        f"Used fallback response for channel {message.channel.id}"
                    )
            
            except discord.HTTPException as e:
                logger.error(f"Discord API error: {e}")
                # Don't send error messages to avoid spam
            
            except Exception as e:
                logger.exception(f"Unexpected error in message handler: {e}")
                # Send a brief error message
                try:
                    await message.channel.send("Something went wrong. Try again later.")
                except Exception:
                    pass  # Even error message failed, give up


async def setup(bot: commands.Bot):
    """Load the cog."""
    await bot.add_cog(LexusCog(bot))
