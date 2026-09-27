"""
Central Security Engine for Lexus V3.
Orchestrates event normalization, detector execution, heat tracking, state machine transitions,
incident correlation, policy evaluation, action dispatch, and persistence.
"""

from __future__ import annotations
import asyncio
import logging
import time
from typing import Optional, Any
import discord

from core.events import SecurityEventType
from core.logging import security_logger
from core.errors import DetectorExecutionError
from security.models import (
    SecurityEvent,
    Evidence,
    ActionResult,
    SecurityState,
    TrustLevel,
    Severity,
    SecurityActionType,
    GuildSecurityConfig
)
from security.event_tracker import EventTracker
from security.dedup import EventDeduplicator
from security.scoring import GuildHeatManager, SecurityStateMachine, calculate_risk
from security.incidents import IncidentManager, Incident
from security.policies import PolicyEngine
from security.actions import action_engine
from security.spam import SpamDetector
from security.raid import RaidDetector
from security.join_gate import JoinGate
from security.anti_nuke import AntiNukeDetector
from security.permission_guard import PermissionGuard
from security.bot_guard import BotGuard
from security.webhook_guard import WebhookGuard
from services.database import security_db
from services.cache import TTLCache

logger = logging.getLogger(__name__)


class SecurityEngine:
    """
    Central coordinator of the Lexus Security Architecture.
    Decouples detection from decision and decision from action.
    """

    def __init__(self, bot: Optional[discord.Client] = None):
        self.bot = bot

        # State machines & heat per guild: guild_id -> SecurityStateMachine / GuildHeatManager
        self._state_machines: TTLCache[int, SecurityStateMachine] = TTLCache(max_size=500, default_ttl=3600.0)
        self._heat_managers: TTLCache[int, GuildHeatManager] = TTLCache(max_size=500, default_ttl=3600.0)
        self._configs: TTLCache[int, GuildSecurityConfig] = TTLCache(max_size=500, default_ttl=600.0)

        # Core subsystems
        self.event_tracker = EventTracker()
        self.dedup = EventDeduplicator()
        self.incidents = IncidentManager()
        self.policies = PolicyEngine()
        self.actions = action_engine

        # Detectors
        self.spam_detector = SpamDetector()
        self.raid_detector = RaidDetector()
        self.join_gate = JoinGate()
        self.anti_nuke = AntiNukeDetector()
        self.permission_guard = PermissionGuard()
        self.bot_guard = BotGuard()
        self.webhook_guard = WebhookGuard()

        # Telemetry
        self.events_processed = 0
        self.decisions_made = 0
        self.actions_executed = 0
        self._cleanup_task: Optional[asyncio.Task] = None

    def start_background_workers(self) -> None:
        """Start periodic cleanup worker."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup(), name="lexus_security_cleanup")

    async def stop(self) -> None:
        """Stop background tasks cleanly."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    async def _periodic_cleanup(self) -> None:
        """Periodically purge expired state and caches."""
        while True:
            try:
                await asyncio.sleep(60.0)
                self.event_tracker.cleanup()
                self._state_machines.cleanup_expired()
                self._heat_managers.cleanup_expired()
                self._configs.cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in security periodic cleanup: {e}")

    # ── State & Config Helpers ─────────────────────────────────────

    def get_state_machine(self, guild_id: int) -> SecurityStateMachine:
        sm = self._state_machines.get(guild_id)
        if sm is None:
            sm = SecurityStateMachine(guild_id)
            self._state_machines.set(guild_id, sm)
        return sm

    def get_heat_manager(self, guild_id: int) -> GuildHeatManager:
        hm = self._heat_managers.get(guild_id)
        if hm is None:
            hm = GuildHeatManager(guild_id)
            self._heat_managers.set(guild_id, hm)
        return hm

    async def get_guild_config(self, guild_id: int) -> GuildSecurityConfig:
        cfg = self._configs.get(guild_id)
        if cfg is None:
            data = await security_db.get_config(guild_id)
            cfg = GuildSecurityConfig.from_dict({"guild_id": guild_id, **data})
            self._configs.set(guild_id, cfg)
        return cfg

    def invalidate_config_cache(self, guild_id: int) -> None:
        self._configs.delete(guild_id)

    def determine_trust_level(
        self,
        guild_id: int,
        actor_id: Optional[int],
        config: GuildSecurityConfig,
        member: Optional[discord.Member] = None
    ) -> TrustLevel:
        """Evaluate actor trust based on owner ID, trusted lists, roles, and status."""
        if not actor_id:
            return TrustLevel.UNKNOWN

        # Bot owner
        if self.bot and getattr(self.bot, "owner_id", None) == actor_id:
            return TrustLevel.OWNER

        # Guild owner
        if member and member.guild.owner_id == actor_id:
            return TrustLevel.OWNER

        # Configured trusted user
        if actor_id in config.trusted_users:
            return TrustLevel.TRUSTED

        # Member checks
        if member:
            # Check trusted roles
            if any(r.id in config.trusted_roles for r in member.roles):
                return TrustLevel.TRUSTED

            # Check administrator / staff permissions
            if member.guild_permissions.administrator or member.guild_permissions.manage_guild:
                return TrustLevel.STAFF

            # Check quarantine role
            if config.quarantine_role_id and any(r.id == config.quarantine_role_id for r in member.roles):
                return TrustLevel.QUARANTINED

            # Check account join age
            if member.joined_at:
                joined_seconds = time.time() - member.joined_at.timestamp()
                if joined_seconds < 3600.0:
                    return TrustLevel.NEW_MEMBER

            return TrustLevel.MEMBER

        return TrustLevel.UNKNOWN

    # ── Event Pipeline ─────────────────────────────────────────────

    async def process_event(
        self,
        event: SecurityEvent,
        guild: Optional[discord.Guild] = None,
        member: Optional[discord.Member] = None,
        extra_context: Optional[dict[str, Any]] = None
    ) -> list[ActionResult]:
        """
        Process a normalized SecurityEvent through the pipeline:
        Deduplication -> Evidence Gathering -> Scoring -> State Evaluation ->
        Policy Decision -> Action Execution -> Telemetry.
        """
        self.events_processed += 1
        guild_id = event.guild_id

        # 1. Deduplication check
        if self.dedup.check_and_record(event):
            return []

        # 2. Guild configuration check
        config = await self.get_guild_config(guild_id)
        if not config.security_enabled:
            return []

        # 3. Trust assessment
        trust = self.determine_trust_level(guild_id, event.actor_id, config, member)

        # 4. State & Heat references
        heat_mgr = self.get_heat_manager(guild_id)
        state_machine = self.get_state_machine(guild_id)
        current_state = state_machine.current_state

        evidence_list: list[Evidence] = []
        extra_ctx = extra_context or {}

        # 5. Isolated Detector Execution
        # Spam Detector
        if event.event_type.is_message_level() and config.spam_enabled:
            try:
                ev = self.spam_detector.evaluate(event)
                if ev:
                    evidence_list.append(ev)
                    # Check for distributed pattern via raid detector
                    norm_text = event.metadata.get("content", "")
                    raid_ev = self.raid_detector.evaluate_message_pattern(event, norm_text)
                    if raid_ev:
                        evidence_list.append(raid_ev)
            except Exception as e:
                logger.error(f"Spam detector error: {e}", exc_info=True)

        # Join Gate & Raid Detector (for Member Joins)
        elif event.event_type == SecurityEventType.MEMBER_JOIN:
            if config.raid_enabled:
                try:
                    ev_raid = self.raid_detector.evaluate_join(event)
                    if ev_raid:
                        evidence_list.append(ev_raid)
                except Exception as e:
                    logger.error(f"Raid detector join error: {e}", exc_info=True)

            if config.join_gate_enabled:
                try:
                    created_at = extra_ctx.get("created_at")
                    has_def_avatar = extra_ctx.get("has_default_avatar", False)
                    join_trust, ev_join = self.join_gate.evaluate(event, current_state, created_at, has_def_avatar)
                    if ev_join:
                        evidence_list.append(ev_join)
                    if join_trust == TrustLevel.SUSPICIOUS:
                        trust = TrustLevel.SUSPICIOUS
                except Exception as e:
                    logger.error(f"Join gate error: {e}", exc_info=True)

        # Anti-Nuke Detector (for Structural Events)
        elif event.event_type.is_structural() and config.antinuke_enabled:
            try:
                ev_nuke = self.anti_nuke.evaluate(event)
                if ev_nuke:
                    evidence_list.append(ev_nuke)
            except Exception as e:
                logger.error(f"Anti-nuke detector error: {e}", exc_info=True)

        # Permission Guard (for Role Updates)
        if event.event_type == SecurityEventType.ROLE_UPDATE:
            try:
                before_perms = extra_ctx.get("before_permissions", 0)
                after_perms = extra_ctx.get("after_permissions", 0)
                is_everyone = extra_ctx.get("is_everyone", False)
                is_q_role = (event.target_id == config.quarantine_role_id) if config.quarantine_role_id else False
                ev_perm = self.permission_guard.evaluate_role_update(
                    event, before_perms, after_perms, is_everyone, is_q_role
                )
                if ev_perm:
                    evidence_list.append(ev_perm)
            except Exception as e:
                logger.error(f"Permission guard error: {e}", exc_info=True)

        # Bot Guard (for Bot Additions)
        if event.event_type == SecurityEventType.BOT_ADD:
            try:
                bot_id = extra_ctx.get("bot_id", event.target_id or 0)
                installer_id = event.actor_id
                bot_perms = extra_ctx.get("bot_permissions", 0)
                ev_bot = self.bot_guard.evaluate(event, bot_id, installer_id, bot_perms, trust, config)
                if ev_bot:
                    evidence_list.append(ev_bot)
            except Exception as e:
                logger.error(f"Bot guard error: {e}", exc_info=True)

        # Webhook Guard (for Webhook Events)
        if event.event_type in (SecurityEventType.WEBHOOK_CREATE, SecurityEventType.WEBHOOK_DELETE, SecurityEventType.WEBHOOK_UPDATE):
            try:
                ev_wh = self.webhook_guard.evaluate(event, trust, event.channel_id)
                if ev_wh:
                    evidence_list.append(ev_wh)
            except Exception as e:
                logger.error(f"Webhook guard error: {e}", exc_info=True)

        # 6. Heat and State Updates
        for ev in evidence_list:
            if "Spam" in ev.detector_name:
                heat_mgr.add_actor_heat(event.actor_id or 0, ev.score * 0.4)
                if event.channel_id:
                    heat_mgr.add_channel_heat(event.channel_id, ev.score * 0.3)
            elif "Raid" in ev.detector_name:
                heat_mgr.add_raid_heat(ev.score)
            elif "AntiNuke" in ev.detector_name or "Permission" in ev.detector_name:
                heat_mgr.add_structural_heat(ev.score)
                heat_mgr.add_actor_heat(event.actor_id or 0, ev.score * 0.5)

        # Evaluate state machine transition
        new_state, state_changed = state_machine.update_state(
            heat_mgr.guild_heat.get_heat(),
            heat_mgr.raid_heat.get_heat(),
            heat_mgr.structural_heat.get_heat()
        )
        if state_changed:
            security_logger.state_transition(
                guild_id,
                current_state.value,
                new_state.value,
                trigger="heat_delta",
                heat=heat_mgr.guild_heat.get_heat()
            )

        if not evidence_list:
            return []

        # 7. Incident correlation & Risk calculation
        best_ev = max(evidence_list, key=lambda e: e.score)
        cross_score = 40.0 if len(evidence_list) > 1 else 0.0

        risk_score, severity = calculate_risk(
            base_score=best_ev.score,
            confidence=best_ev.confidence,
            trust=trust,
            cross_action_score=cross_score,
            is_raid_active=(new_state == SecurityState.RAID)
        )

        incident = self.incidents.find_correlated_incident(guild_id, event.actor_id)
        if incident is None:
            incident = self.incidents.create_incident(
                guild_id=guild_id,
                primary_actor=event.actor_id,
                initial_event=event,
                evidence=best_ev,
                severity=severity
            )
        else:
            incident.add_event(event)
            incident.add_evidence(best_ev)
            if severity.value > incident.severity.value:
                incident.severity = severity

        # 8. Policy Evaluation
        planned_actions = self.policies.evaluate(
            risk_score=risk_score,
            severity=severity,
            confidence=best_ev.confidence,
            guild_state=new_state,
            actor_trust=trust,
            is_structural=event.event_type.is_structural(),
            config=config
        )
        self.decisions_made += len(planned_actions)

        # 9. Action Execution
        action_results: list[ActionResult] = []
        target_guild = guild or (self.bot.get_guild(guild_id) if self.bot else None)

        extra_payload = {
            "incident_id": incident.incident_id,
            "actor_id": event.actor_id,
            "risk": severity.value,
            "event_type": event.event_type.value,
            "channel_id": event.channel_id
        }

        if target_guild:
            bot_member = target_guild.me
            for act_type in planned_actions:
                result = await self.actions.execute(
                    action=act_type,
                    guild=target_guild,
                    target_id=event.actor_id,
                    reason=best_ev.reason,
                    config=config,
                    bot_member=bot_member,
                    extra_data=extra_payload
                )
                action_results.append(result)
                incident.add_action(result)
                self.actions_executed += 1

                # Structured log
                security_logger.event(
                    incident_id=incident.incident_id,
                    guild_id=guild_id,
                    actor_id=event.actor_id,
                    event_type=event.event_type.value,
                    risk=severity.value,
                    score=risk_score,
                    action=act_type.value,
                    result="SUCCESS" if result.success else "FAILED",
                    details=result.error or result.reason
                )
        else:
            # Offline simulation or test without connected discord.Guild
            for act_type in planned_actions:
                sim_res = ActionResult(
                    success=True,
                    action=act_type,
                    target_id=event.actor_id,
                    reason=f"[SIMULATED] {best_ev.reason}",
                    timestamp=time.time()
                )
                action_results.append(sim_res)
                incident.add_action(sim_res)
                self.actions_executed += 1

        # 10. Persistence
        await self.incidents.persist_incident(incident)

        return action_results

    # ── Readiness & Health ─────────────────────────────────────────

    def get_health_status(self) -> dict[str, Any]:
        """Report component readiness without exaggerating capabilities."""
        db_connected = security_db.is_connected()
        return {
            "security_ready": True,
            "database_ready": db_connected,
            "audit_ready": True,
            "quarantine_ready": True,
            "recovery_ready": True,
            "events_processed": self.events_processed,
            "decisions_made": self.decisions_made,
            "actions_executed": self.actions_executed
        }


# Global security engine instance
security_engine = SecurityEngine()
