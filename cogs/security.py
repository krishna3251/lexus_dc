"""
Lexus Security Engine Cog.
Exposes clean, professional administration commands for Lexus Security Engine V3
and routes Discord gateway events to the central SecurityEngine.
"""

from __future__ import annotations
import discord
from discord.ext import commands
from discord import app_commands
import time
import logging
from typing import Optional, Literal

from core.events import SecurityEventType
from security.models import (
    SecurityEvent,
    SecurityProfile,
    TrustLevel,
    SecurityActionType,
    GuildSecurityConfig
)
from security.engine import security_engine
from security.quarantine import quarantine_manager
from security.lockdown import lockdown_manager
from security.baseline import baseline_manager
from security.recovery import recovery_engine
from security.audit import audit_correlator
from services.database import security_db

logger = logging.getLogger(__name__)


class SecurityCog(commands.Cog, name="Security"):
    """Lexus V3 Security Engine Management & Defense System."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        security_engine.bot = bot
        security_engine.start_background_workers()

    security_group = app_commands.Group(
        name="security",
        description="Lexus V3 Security Engine commands",
        default_permissions=discord.Permissions(administrator=True)
    )

    # ── Slash Commands ─────────────────────────────────────────────

    @security_group.command(name="status", description="Display server security engine status")
    async def security_status(self, interaction: discord.Interaction):
        """Show current security engine status and protection modules."""
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        guild = interaction.guild
        cfg = await security_engine.get_guild_config(guild.id)
        sm = security_engine.get_state_machine(guild.id)
        hm = security_engine.get_heat_manager(guild.id)
        recent_incidents = await security_db.get_recent_incidents(guild.id, limit=5)
        active_incidents = [inc for inc in recent_incidents if inc.get("state") in ("OPEN", "CONTAINED")]

        embed = discord.Embed(
            title="Lexus Security Engine",
            color=discord.Color.blue() if sm.current_state.value == "NORMAL" else discord.Color.gold(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Status", value=f"**{sm.current_state.value.capitalize()}**", inline=True)
        embed.add_field(name="Mode", value=f"`{cfg.security_mode.upper()}`", inline=True)
        embed.add_field(name="Profile", value=f"`{cfg.profile.value}`", inline=True)

        modules_text = (
            f"Anti-Spam: {'`Enabled`' if cfg.spam_enabled else '`Disabled`'}\n"
            f"Anti-Raid: {'`Enabled`' if cfg.raid_enabled else '`Disabled`'}\n"
            f"Anti-Nuke: {'`Enabled`' if cfg.antinuke_enabled else '`Disabled`'}\n"
            f"Join Gate: {'`Enabled`' if cfg.join_gate_enabled else '`Disabled`'}\n"
            f"Quarantine: {'`Ready`' if cfg.quarantine_role_id else '`Not configured`'}\n"
            f"Lockdown: {'`Active`' if lockdown_manager.is_locked_down(guild.id) else '`Ready`'}"
        )
        embed.add_field(name="Protection Modules", value=modules_text, inline=False)

        heat_text = (
            f"Guild Heat: `{hm.guild_heat.get_heat():.1f}/100` | "
            f"Raid Heat: `{hm.raid_heat.get_heat():.1f}/100` | "
            f"Structural Heat: `{hm.structural_heat.get_heat():.1f}/100`"
        )
        embed.add_field(name="Telemetry", value=heat_text, inline=False)
        embed.add_field(name="Active Incidents", value=str(len(active_incidents)), inline=True)
        embed.add_field(name="Total Lifetime Incidents", value=str(len(recent_incidents)), inline=True)

        embed.set_footer(text="Lexus Defense Engine V3")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @security_group.command(name="setup", description="Quick setup for security roles and channels")
    @app_commands.describe(
        log_channel="Channel for security alerts and incident notifications",
        quarantine_role="Role to assign to quarantined members (or auto-create if omitted)"
    )
    async def security_setup(
        self,
        interaction: discord.Interaction,
        log_channel: Optional[discord.TextChannel] = None,
        quarantine_role: Optional[discord.Role] = None
    ):
        """Guided initial setup for Lexus Security."""
        guild = interaction.guild
        if not guild:
            return

        await interaction.response.defer(ephemeral=True)
        updates: dict[str, Any] = {}
        log_msgs: list[str] = []

        if log_channel:
            updates["security_log_channel_id"] = log_channel.id
            log_msgs.append(f"Security alerts channel set to {log_channel.mention}.")

        # Handle quarantine role
        if quarantine_role:
            updates["quarantine_role_id"] = quarantine_role.id
            log_msgs.append(f"Quarantine role set to {quarantine_role.mention}.")
        else:
            created_role = await quarantine_manager.setup_quarantine_role(guild)
            if created_role:
                updates["quarantine_role_id"] = created_role.id
                log_msgs.append(f"Created dedicated quarantine role {created_role.mention}.")
            else:
                log_msgs.append("Could not auto-create quarantine role (check Manage Roles permission).")

        # Capture initial baseline
        success, base_msg, _ = await baseline_manager.capture_and_save_baseline(
            guild,
            security_engine.get_state_machine(guild.id).current_state,
            force=True
        )
        log_msgs.append(base_msg)

        if updates:
            await security_db.save_config(guild.id, updates)
            security_engine.invalidate_config_cache(guild.id)

        embed = discord.Embed(
            title="Lexus Security Setup Completed",
            description="\n".join(f"• {msg}" for msg in log_msgs),
            color=discord.Color.green()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @security_group.command(name="config", description="Configure security engine mode and strictness")
    @app_commands.describe(
        mode="Operation mode: audit (monitor & log only) or enforce (automated defense)",
        profile="Strictness profile: standard, strict, or custom"
    )
    async def security_config(
        self,
        interaction: discord.Interaction,
        mode: Optional[Literal["audit", "enforce"]] = None,
        profile: Optional[Literal["standard", "strict", "custom"]] = None
    ):
        """Configure security settings."""
        guild = interaction.guild
        if not guild:
            return

        updates: dict[str, Any] = {}
        if mode:
            updates["security_mode"] = mode
        if profile:
            updates["profile"] = profile.upper()

        if updates:
            await security_db.save_config(guild.id, updates)
            security_engine.invalidate_config_cache(guild.id)

        cfg = await security_engine.get_guild_config(guild.id)
        embed = discord.Embed(
            title="Lexus Security Configuration",
            color=discord.Color.blue()
        )
        embed.add_field(name="Current Mode", value=f"`{cfg.security_mode.upper()}`", inline=True)
        embed.add_field(name="Profile", value=f"`{cfg.profile.value}`", inline=True)
        embed.add_field(name="Action Budget", value=f"{cfg.action_budget_limit} per {cfg.action_budget_window}s", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @security_group.command(name="logs", description="View recent security incidents")
    async def security_logs(self, interaction: discord.Interaction):
        """View recent security incidents."""
        guild = interaction.guild
        if not guild:
            return

        incidents = await security_db.get_recent_incidents(guild.id, limit=5)
        if not incidents:
            await interaction.response.send_message("No recent security incidents found for this server.", ephemeral=True)
            return

        embed = discord.Embed(title="Recent Security Incidents", color=discord.Color.dark_blue())
        for inc in incidents:
            actor_text = f"<@{inc.get('primary_actor')}>" if inc.get("primary_actor") else "Unknown"
            embed.add_field(
                name=f"{inc.get('incident_id')} — {inc.get('severity')}",
                value=f"Actor: {actor_text} | State: `{inc.get('state')}` | Score: `{inc.get('score', 0):.1f}`",
                inline=False
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @security_group.command(name="trust", description="Manage trusted actors and roles")
    @app_commands.describe(
        action="add or remove",
        user="User to trust / untrust",
        role="Role to trust / untrust"
    )
    async def security_trust(
        self,
        interaction: discord.Interaction,
        action: Literal["add", "remove"],
        user: Optional[discord.Member] = None,
        role: Optional[discord.Role] = None
    ):
        """Add or remove trusted users or roles."""
        guild = interaction.guild
        if not guild or (not user and not role):
            await interaction.response.send_message("Specify a user or role to trust/untrust.", ephemeral=True)
            return

        cfg = await security_engine.get_guild_config(guild.id)
        trusted_users = list(cfg.trusted_users)
        trusted_roles = list(cfg.trusted_roles)

        msg = ""
        if user:
            if action == "add" and user.id not in trusted_users:
                trusted_users.append(user.id)
                msg = f"Added {user.mention} to trusted users."
            elif action == "remove" and user.id in trusted_users:
                trusted_users.remove(user.id)
                msg = f"Removed {user.mention} from trusted users."
            else:
                msg = f"No change made for {user.mention}."

        if role:
            if action == "add" and role.id not in trusted_roles:
                trusted_roles.append(role.id)
                msg = f"Added {role.mention} to trusted roles."
            elif action == "remove" and role.id in trusted_roles:
                trusted_roles.remove(role.id)
                msg = f"Removed {role.mention} from trusted roles."

        await security_db.save_config(guild.id, {
            "trusted_users": trusted_users,
            "trusted_roles": trusted_roles
        })
        security_engine.invalidate_config_cache(guild.id)
        await interaction.response.send_message(msg or "Trust settings updated.", ephemeral=True)

    @security_group.command(name="quarantine", description="Manually quarantine or release a member")
    @app_commands.describe(
        action="quarantine or release",
        member="Target member",
        reason="Reason for action"
    )
    async def security_quarantine_cmd(
        self,
        interaction: discord.Interaction,
        action: Literal["quarantine", "release"],
        member: discord.Member,
        reason: Optional[str] = "Manual administrative action"
    ):
        """Manually quarantine or release a member."""
        guild = interaction.guild
        if not guild:
            return

        await interaction.response.defer(ephemeral=True)
        cfg = await security_engine.get_guild_config(guild.id)

        if action == "quarantine":
            res = await quarantine_manager.quarantine_member(guild, member, reason or "Manual quarantine", cfg)
        else:
            res = await quarantine_manager.release_member(guild, member, cfg)

        if res.success:
            await interaction.followup.send(f"✅ Success: {res.reason}", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Failed: {res.error}", ephemeral=True)

    @security_group.command(name="lockdown", description="Activate or release emergency channel lockdown")
    @app_commands.describe(
        action="enable or release",
        reason="Reason for emergency lockdown"
    )
    async def security_lockdown_cmd(
        self,
        interaction: discord.Interaction,
        action: Literal["enable", "release"],
        reason: Optional[str] = "Manual lockdown"
    ):
        """Trigger or release server lockdown."""
        guild = interaction.guild
        if not guild:
            return

        await interaction.response.defer(ephemeral=True)
        cfg = await security_engine.get_guild_config(guild.id)

        if action == "enable":
            res = await lockdown_manager.lock_guild(guild, reason or "Manual lockdown", cfg)
        else:
            res = await lockdown_manager.unlock_guild(guild, cfg)

        if res.success:
            await interaction.followup.send(f"✅ {res.reason}", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Failed: {res.error}", ephemeral=True)

    @security_group.command(name="baseline", description="Capture or inspect trusted server baseline")
    @app_commands.describe(
        action="capture (save current structure) or diff (compare current against baseline)"
    )
    async def security_baseline_cmd(
        self,
        interaction: discord.Interaction,
        action: Literal["capture", "diff"]
    ):
        """Capture or compare structural baseline."""
        guild = interaction.guild
        if not guild:
            return

        await interaction.response.defer(ephemeral=True)
        if action == "capture":
            state = security_engine.get_state_machine(guild.id).current_state
            success, msg, _ = await baseline_manager.capture_and_save_baseline(guild, state, force=True)
            status_icon = "✅" if success else "⚠️"
            await interaction.followup.send(f"{status_icon} {msg}", ephemeral=True)
        else:
            diff, summary = await baseline_manager.diff_against_baseline(guild)
            if diff is None:
                await interaction.followup.send(f"⚠️ {summary}", ephemeral=True)
            else:
                await interaction.followup.send(f"📊 Structural Diff: {summary}", ephemeral=True)

    @security_group.command(name="recovery", description="Analyze structural damage compared to baseline")
    async def security_recovery_cmd(self, interaction: discord.Interaction):
        """Analyze damage after an attack."""
        guild = interaction.guild
        if not guild:
            return

        await interaction.response.defer(ephemeral=True)
        report = await recovery_engine.analyze_damage(guild)

        embed = discord.Embed(title="Lexus Recovery Assessment", color=discord.Color.dark_green())
        if report.get("status") == "no_baseline":
            embed.description = report.get("message")
        else:
            embed.description = (
                f"**Damage Status:** {'⚠️ Changes Detected' if report['has_damage'] else '✅ In-Sync with Baseline'}\n"
                f"**Summary:** {report['summary']}\n"
                f"Deleted Roles: {report['deleted_roles_count']}\n"
                f"Deleted Channels: {report['deleted_channels_count']}\n"
                f"Modified Roles: {report['modified_roles_count']}"
            )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── Gateway Event Listeners ────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Normalize message event and process through security engine."""
        if not message.guild or message.author.id == self.bot.user.id:
            return

        evt = SecurityEvent(
            guild_id=message.guild.id,
            actor_id=message.author.id,
            channel_id=message.channel.id,
            event_type=SecurityEventType.MESSAGE,
            timestamp=time.time(),
            metadata={
                "message_id": message.id,
                "content": message.content,
                "mentions_count": len(message.mentions),
                "mention_everyone": message.mention_everyone,
                "attachments_count": len(message.attachments)
            }
        )
        member = message.author if isinstance(message.author, discord.Member) else message.guild.get_member(message.author.id)
        await security_engine.process_event(evt, guild=message.guild, member=member)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Handle member join event."""
        guild = member.guild
        if member.bot:
            # Bot addition: attempt audit correlation to identify installer
            audit_res = await audit_correlator.find_actor_for_event(
                guild, discord.AuditLogAction.bot_add, target_id=member.id
            )
            installer_id = audit_res[0] if audit_res else None

            evt = SecurityEvent(
                guild_id=guild.id,
                actor_id=installer_id,
                target_id=member.id,
                event_type=SecurityEventType.BOT_ADD,
                timestamp=time.time()
            )
            await security_engine.process_event(
                evt,
                guild=guild,
                extra_context={
                    "bot_id": member.id,
                    "bot_permissions": member.guild_permissions.value
                }
            )
        else:
            evt = SecurityEvent(
                guild_id=guild.id,
                actor_id=member.id,
                event_type=SecurityEventType.MEMBER_JOIN,
                timestamp=time.time()
            )
            created_at = member.created_at.timestamp() if member.created_at else None
            has_def_avatar = (member.avatar is None)
            await security_engine.process_event(
                evt,
                guild=guild,
                member=member,
                extra_context={"created_at": created_at, "has_default_avatar": has_def_avatar}
            )

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        audit_res = await audit_correlator.find_actor_for_event(
            guild, discord.AuditLogAction.channel_create, target_id=channel.id
        )
        actor_id = audit_res[0] if audit_res else None
        evt = SecurityEvent(
            guild_id=guild.id,
            actor_id=actor_id,
            target_id=channel.id,
            event_type=SecurityEventType.CHANNEL_CREATE,
            timestamp=time.time()
        )
        await security_engine.process_event(evt, guild=guild)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        audit_res = await audit_correlator.find_actor_for_event(
            guild, discord.AuditLogAction.channel_delete, target_id=channel.id
        )
        actor_id = audit_res[0] if audit_res else None
        evt = SecurityEvent(
            guild_id=guild.id,
            actor_id=actor_id,
            target_id=channel.id,
            event_type=SecurityEventType.CHANNEL_DELETE,
            timestamp=time.time()
        )
        await security_engine.process_event(evt, guild=guild)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        guild = role.guild
        audit_res = await audit_correlator.find_actor_for_event(
            guild, discord.AuditLogAction.role_create, target_id=role.id
        )
        actor_id = audit_res[0] if audit_res else None
        evt = SecurityEvent(
            guild_id=guild.id,
            actor_id=actor_id,
            target_id=role.id,
            event_type=SecurityEventType.ROLE_CREATE,
            timestamp=time.time()
        )
        await security_engine.process_event(evt, guild=guild)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        guild = role.guild
        audit_res = await audit_correlator.find_actor_for_event(
            guild, discord.AuditLogAction.role_delete, target_id=role.id
        )
        actor_id = audit_res[0] if audit_res else None
        evt = SecurityEvent(
            guild_id=guild.id,
            actor_id=actor_id,
            target_id=role.id,
            event_type=SecurityEventType.ROLE_DELETE,
            timestamp=time.time()
        )
        await security_engine.process_event(evt, guild=guild)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        guild = after.guild
        audit_res = await audit_correlator.find_actor_for_event(
            guild, discord.AuditLogAction.role_update, target_id=after.id
        )
        actor_id = audit_res[0] if audit_res else None
        evt = SecurityEvent(
            guild_id=guild.id,
            actor_id=actor_id,
            target_id=after.id,
            event_type=SecurityEventType.ROLE_UPDATE,
            timestamp=time.time()
        )
        await security_engine.process_event(
            evt,
            guild=guild,
            extra_context={
                "before_permissions": before.permissions.value,
                "after_permissions": after.permissions.value,
                "is_everyone": after.is_default()
            }
        )

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User | discord.Member):
        audit_res = await audit_correlator.find_actor_for_event(
            guild, discord.AuditLogAction.ban, target_id=user.id
        )
        actor_id = audit_res[0] if audit_res else None
        evt = SecurityEvent(
            guild_id=guild.id,
            actor_id=actor_id,
            target_id=user.id,
            event_type=SecurityEventType.MEMBER_BAN,
            timestamp=time.time()
        )
        await security_engine.process_event(evt, guild=guild)

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        audit_res = await audit_correlator.find_actor_for_event(
            guild, discord.AuditLogAction.webhook_create
        )
        actor_id = audit_res[0] if audit_res else None
        evt = SecurityEvent(
            guild_id=guild.id,
            actor_id=actor_id,
            channel_id=channel.id,
            event_type=SecurityEventType.WEBHOOK_CREATE,
            timestamp=time.time()
        )
        await security_engine.process_event(evt, guild=guild)


async def setup(bot: commands.Bot):
    await bot.add_cog(SecurityCog(bot))
    logger.info("✅ Lexus V3 Security Engine Cog loaded.")
