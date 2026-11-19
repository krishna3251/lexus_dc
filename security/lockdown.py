"""Reversible lockdown with a durable journal of changed permission fields."""

from __future__ import annotations

import asyncio
import logging
from weakref import WeakValueDictionary

import discord
from pymongo import ReturnDocument
from pymongo.errors import PyMongoError

import mongo_helper
from core.logging import security_logger
from security.models import ActionResult, GuildSecurityConfig, SecurityActionType

logger = logging.getLogger(__name__)
LOCKED_FIELDS = (
    "send_messages",
    "send_messages_in_threads",
    "create_public_threads",
    "create_private_threads",
)


class LockdownManager:
    """Preserve the original overwrite before editing Discord."""

    def __init__(self):
        self._guild_locks: WeakValueDictionary[int, asyncio.Lock] = WeakValueDictionary()

    def _guild_lock(self, guild_id: int) -> asyncio.Lock:
        return self._guild_locks.setdefault(guild_id, asyncio.Lock())

    @staticmethod
    def _journal():
        return mongo_helper.get_collection("security_lockdowns")

    async def status(self, guild_id: int) -> str:
        journal = self._journal()
        if journal is None:
            return "Journal unavailable"
        try:
            entry = await journal.find_one({"guild_id": guild_id}, {"_id": 1})
        except PyMongoError:
            return "Journal unavailable"
        return "Recovery pending" if entry else "Ready"

    @staticmethod
    def _result(*, reason=None, error=None):
        return ActionResult(
            success=error is None, action=SecurityActionType.LOCKDOWN,
            reason=reason, error=error,
        )

    async def lock_guild(
        self, guild: discord.Guild, reason: str, config: GuildSecurityConfig,
    ) -> ActionResult:
        if not guild.me or not guild.me.guild_permissions.manage_roles:
            return self._result(error="Bot lacks Manage Roles permission")
        journal = self._journal()
        if journal is None:
            return self._result(error="Lockdown requires an available recovery journal")

        locked_channels = failed = 0
        everyone = guild.default_role
        async with self._guild_lock(guild.id):
            for channel in guild.text_channels:
                if channel.id in config.protected_channels or channel.id == config.security_log_channel_id:
                    continue
                try:
                    current = channel.overwrites_for(everyone)
                    original = {
                        name: getattr(current, name)
                        for name in LOCKED_FIELDS if getattr(current, name) is not False
                    }
                    if not original:
                        continue
                    key = {"_id": str(channel.id)}
                    entry = await journal.find_one_and_update(
                        key,
                        {"$setOnInsert": {"guild_id": guild.id, "channel_id": channel.id, "original": original}},
                        upsert=True, return_document=ReturnDocument.AFTER,
                    )
                    changes = original.keys() & entry["original"].keys()
                    if not changes:
                        continue
                    current.update(**dict.fromkeys(changes, False))
                    await channel.set_permissions(everyone, overwrite=current, reason=f"Lexus Lockdown: {reason}")
                    locked_channels += 1
                except (discord.HTTPException, PyMongoError) as exc:
                    logger.warning("Lockdown failed in guild %s channel %s (%s)", guild.id, channel.id, type(exc).__name__)
                    failed += 1

        security_logger.event(
            incident_id="LOCKDOWN", guild_id=guild.id, actor_id=None, event_type="LOCKDOWN_ACTIVE",
            risk="CRITICAL", score=95.0, action="LOCKDOWN",
            result="FAILED" if failed or not locked_channels else "SUCCESS",
            details=f"Locked {locked_channels} channels, {failed} failed",
        )
        if failed:
            return self._result(error=f"Locked {locked_channels} channels. {failed} failed. Check the recovery journal before retrying.")
        if not locked_channels:
            return self._result(error="No eligible channels needed changes")
        return self._result(reason=f"Lockdown activated across {locked_channels} channels")

    async def unlock_guild(self, guild: discord.Guild, config: GuildSecurityConfig) -> ActionResult:
        if not guild.me or not guild.me.guild_permissions.manage_roles:
            return self._result(error="Bot lacks Manage Roles permission")
        journal = self._journal()
        if journal is None:
            return self._result(error="Lockdown recovery journal is unavailable")

        restored = pending = removed = 0
        everyone = guild.default_role
        async with self._guild_lock(guild.id):
            try:
                async for entry in journal.find({"guild_id": guild.id}):
                    key = {"_id": entry["_id"]}
                    try:
                        channel = await guild.fetch_channel(entry["channel_id"])
                        current = channel.overwrites_for(everyone)
                        changes = {
                            name: value for name, value in entry["original"].items()
                            if getattr(current, name) is False
                        }
                        if changes:
                            current.update(**changes)
                            await channel.set_permissions(
                                everyone, overwrite=None if current.is_empty() else current,
                                reason="Lexus Security: Lockdown released",
                            )
                        await journal.delete_one(key)
                        restored += 1
                    except discord.NotFound:
                        await journal.delete_one(key)
                        removed += 1
                    except (discord.HTTPException, PyMongoError) as exc:
                        logger.warning("Lockdown restore failed in guild %s channel %s (%s)",
                                       guild.id, entry["channel_id"], type(exc).__name__)
                        pending += 1
            except PyMongoError:
                return self._result(error=f"Processed {restored} channels before the journal became unavailable. Retry release.")
        security_logger.event(
            incident_id="LOCKDOWN", guild_id=guild.id, actor_id=None, event_type="LOCKDOWN_RELEASED",
            risk="CRITICAL", score=0.0, action="LOCKDOWN_RELEASE",
            result="FAILED" if pending or not (restored or removed) else "SUCCESS",
            details=f"Processed {restored} channels, {pending} pending, {removed} deleted",
        )
        if pending:
            return self._result(error=f"Processed {restored} channels. {pending} still need recovery. Retry release.")
        if not restored and not removed:
            return self._result(error="No lockdown recovery entries were found")
        return self._result(reason=f"Lockdown released. Processed {restored} channels and removed {removed} deleted channels.")


lockdown_manager = LockdownManager()
