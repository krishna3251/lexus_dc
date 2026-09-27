"""
Core event types and definitions for Lexus Security Engine.
Provides enumeration of all monitored Discord and security activity.
"""

from __future__ import annotations
from enum import Enum, unique


@unique
class SecurityEventType(str, Enum):
    # Message activity
    MESSAGE = "MESSAGE"

    # Member lifecycle
    MEMBER_JOIN = "MEMBER_JOIN"
    MEMBER_LEAVE = "MEMBER_LEAVE"

    # Channel operations
    CHANNEL_CREATE = "CHANNEL_CREATE"
    CHANNEL_UPDATE = "CHANNEL_UPDATE"
    CHANNEL_DELETE = "CHANNEL_DELETE"

    # Overwrite operations
    OVERWRITE_CREATE = "OVERWRITE_CREATE"
    OVERWRITE_UPDATE = "OVERWRITE_UPDATE"
    OVERWRITE_DELETE = "OVERWRITE_DELETE"

    # Role operations
    ROLE_CREATE = "ROLE_CREATE"
    ROLE_UPDATE = "ROLE_UPDATE"
    ROLE_DELETE = "ROLE_DELETE"

    # Moderation actions
    MEMBER_BAN = "MEMBER_BAN"
    MEMBER_KICK = "MEMBER_KICK"
    MEMBER_PRUNE = "MEMBER_PRUNE"

    # Bot additions
    BOT_ADD = "BOT_ADD"

    # Webhook operations
    WEBHOOK_CREATE = "WEBHOOK_CREATE"
    WEBHOOK_UPDATE = "WEBHOOK_UPDATE"
    WEBHOOK_DELETE = "WEBHOOK_DELETE"

    # Invite operations
    INVITE_CREATE = "INVITE_CREATE"
    INVITE_UPDATE = "INVITE_UPDATE"
    INVITE_DELETE = "INVITE_DELETE"

    # Integration operations
    INTEGRATION_CREATE = "INTEGRATION_CREATE"
    INTEGRATION_UPDATE = "INTEGRATION_UPDATE"
    INTEGRATION_DELETE = "INTEGRATION_DELETE"

    # AutoMod operations
    AUTOMOD_CREATE = "AUTOMOD_CREATE"
    AUTOMOD_UPDATE = "AUTOMOD_UPDATE"
    AUTOMOD_DELETE = "AUTOMOD_DELETE"

    # Command permissions
    COMMAND_PERMISSION_UPDATE = "COMMAND_PERMISSION_UPDATE"

    # Thread operations
    THREAD_CREATE = "THREAD_CREATE"
    THREAD_UPDATE = "THREAD_UPDATE"
    THREAD_DELETE = "THREAD_DELETE"

    # Emoji operations
    EMOJI_CREATE = "EMOJI_CREATE"
    EMOJI_UPDATE = "EMOJI_UPDATE"
    EMOJI_DELETE = "EMOJI_DELETE"

    # Sticker operations
    STICKER_CREATE = "STICKER_CREATE"
    STICKER_UPDATE = "STICKER_UPDATE"
    STICKER_DELETE = "STICKER_DELETE"

    # Security configuration tampering
    SECURITY_CONFIG_UPDATE = "SECURITY_CONFIG_UPDATE"

    def is_structural(self) -> bool:
        """Return True if this event alters guild structure or security boundaries."""
        return self in (
            SecurityEventType.CHANNEL_CREATE,
            SecurityEventType.CHANNEL_UPDATE,
            SecurityEventType.CHANNEL_DELETE,
            SecurityEventType.OVERWRITE_CREATE,
            SecurityEventType.OVERWRITE_UPDATE,
            SecurityEventType.OVERWRITE_DELETE,
            SecurityEventType.ROLE_CREATE,
            SecurityEventType.ROLE_UPDATE,
            SecurityEventType.ROLE_DELETE,
            SecurityEventType.MEMBER_BAN,
            SecurityEventType.MEMBER_KICK,
            SecurityEventType.MEMBER_PRUNE,
            SecurityEventType.BOT_ADD,
            SecurityEventType.WEBHOOK_CREATE,
            SecurityEventType.WEBHOOK_UPDATE,
            SecurityEventType.WEBHOOK_DELETE,
            SecurityEventType.AUTOMOD_CREATE,
            SecurityEventType.AUTOMOD_UPDATE,
            SecurityEventType.AUTOMOD_DELETE,
            SecurityEventType.SECURITY_CONFIG_UPDATE,
        )

    def is_message_level(self) -> bool:
        """Return True if this is a message or content level event."""
        return self == SecurityEventType.MESSAGE

    def is_join_level(self) -> bool:
        """Return True if this relates to member join activity."""
        return self in (SecurityEventType.MEMBER_JOIN, SecurityEventType.MEMBER_LEAVE)
