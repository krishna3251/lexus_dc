"""
Security scoring, heat tracking, decay dynamics, and state machine with hysteresis.
"""

from __future__ import annotations
import math
import time
from typing import Optional, Any
from security.models import SecurityState, RaidSubState, Severity, TrustLevel
from services.cache import TTLCache


class DecayingHeat:
    """
    Tracks a numeric heat score that exponentially decays over time.
    heat(t) = heat0 * exp(-decay_rate * delta_t)
    Evaluated lazily upon access to minimize computational overhead.
    """

    def __init__(self, half_life_seconds: float = 30.0, max_heat: float = 100.0):
        self.half_life = max(1.0, float(half_life_seconds))
        # decay_rate lambda = ln(2) / half_life
        self.decay_rate = math.log(2) / self.half_life
        self.max_heat = float(max_heat)
        self._current_heat = 0.0
        self._last_update = time.monotonic()

    def get_heat(self, now: Optional[float] = None) -> float:
        current_time = time.monotonic() if now is None else now
        elapsed = current_time - self._last_update
        if elapsed > 0 and self._current_heat > 0:
            self._current_heat *= math.exp(-self.decay_rate * elapsed)
            self._last_update = current_time
        return max(0.0, self._current_heat)

    def add_heat(self, amount: float, now: Optional[float] = None) -> float:
        current = self.get_heat(now)
        self._current_heat = min(self.max_heat, current + max(0.0, amount))
        self._last_update = time.monotonic() if now is None else now
        return self._current_heat

    def reset(self) -> None:
        self._current_heat = 0.0
        self._last_update = time.monotonic()


class GuildHeatManager:
    """
    Maintains actor_heat, channel_heat, guild_heat, raid_heat, and structural_heat
    for a single guild, with automatic decay and memory bounds.
    """

    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        self.guild_heat = DecayingHeat(half_life_seconds=45.0)
        self.raid_heat = DecayingHeat(half_life_seconds=60.0)
        self.structural_heat = DecayingHeat(half_life_seconds=30.0)

        # Bounded per-actor and per-channel heat trackers
        self._actor_heat_cache: TTLCache[int, DecayingHeat] = TTLCache(max_size=2000, default_ttl=600.0)
        self._channel_heat_cache: TTLCache[int, DecayingHeat] = TTLCache(max_size=500, default_ttl=600.0)

    def get_actor_heat(self, actor_id: int) -> float:
        tracker = self._actor_heat_cache.get(actor_id)
        return tracker.get_heat() if tracker else 0.0

    def add_actor_heat(self, actor_id: int, amount: float) -> float:
        tracker = self._actor_heat_cache.get(actor_id)
        if tracker is None:
            tracker = DecayingHeat(half_life_seconds=30.0)
            self._actor_heat_cache.set(actor_id, tracker)
        val = tracker.add_heat(amount)
        # Propagate partial heat to overall guild
        self.guild_heat.add_heat(amount * 0.25)
        return val

    def get_channel_heat(self, channel_id: int) -> float:
        tracker = self._channel_heat_cache.get(channel_id)
        return tracker.get_heat() if tracker else 0.0

    def add_channel_heat(self, channel_id: int, amount: float) -> float:
        tracker = self._channel_heat_cache.get(channel_id)
        if tracker is None:
            tracker = DecayingHeat(half_life_seconds=20.0)
            self._channel_heat_cache.set(channel_id, tracker)
        return tracker.add_heat(amount)

    def add_raid_heat(self, amount: float) -> float:
        val = self.raid_heat.add_heat(amount)
        self.guild_heat.add_heat(amount * 0.5)
        return val

    def add_structural_heat(self, amount: float) -> float:
        val = self.structural_heat.add_heat(amount)
        self.guild_heat.add_heat(amount * 0.5)
        return val


class SecurityStateMachine:
    """
    Manages transitions between NORMAL, ELEVATED, RAID, PANIC, and RECOVERY
    using hysteresis to prevent oscillation/flapping.
    """

    # Hysteresis thresholds
    RAID_ENTER_THRESHOLD = 80.0
    RAID_EXIT_THRESHOLD = 40.0
    RAID_SUSPECTED_THRESHOLD = 50.0

    ELEVATED_ENTER_THRESHOLD = 40.0
    ELEVATED_EXIT_THRESHOLD = 20.0

    PANIC_ENTER_THRESHOLD = 85.0
    PANIC_EXIT_THRESHOLD = 30.0

    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        self.current_state = SecurityState.NORMAL
        self.raid_substate = RaidSubState.NONE
        self.last_transition_time = time.monotonic()
        self.min_state_dwell_time = 5.0  # seconds minimum before down-shifting

    def update_state(
        self,
        guild_heat: float,
        raid_heat: float,
        structural_heat: float
    ) -> tuple[SecurityState, bool]:
        """
        Evaluate and update state based on current heat signals.
        Returns (new_state, state_changed).
        """
        now = time.monotonic()
        prev_state = self.current_state
        time_in_state = now - self.last_transition_time

        # PANIC check (structural destruction)
        if structural_heat >= self.PANIC_ENTER_THRESHOLD:
            self.current_state = SecurityState.PANIC
        elif self.current_state == SecurityState.PANIC:
            if time_in_state >= self.min_state_dwell_time and structural_heat < self.PANIC_EXIT_THRESHOLD:
                # Transition to RECOVERY instead of immediately dropping to NORMAL
                self.current_state = SecurityState.RECOVERY
        # RAID check
        elif raid_heat >= self.RAID_ENTER_THRESHOLD:
            self.current_state = SecurityState.RAID
            self.raid_substate = RaidSubState.RAID_CONFIRMED
        elif raid_heat >= self.RAID_SUSPECTED_THRESHOLD:
            self.raid_substate = RaidSubState.RAID_SUSPECTED
            if self.current_state == SecurityState.NORMAL:
                self.current_state = SecurityState.ELEVATED
        elif self.current_state == SecurityState.RAID:
            if time_in_state >= self.min_state_dwell_time and raid_heat < self.RAID_EXIT_THRESHOLD:
                self.current_state = SecurityState.ELEVATED
                self.raid_substate = RaidSubState.NONE
        # ELEVATED check
        elif guild_heat >= self.ELEVATED_ENTER_THRESHOLD or raid_heat >= self.ELEVATED_ENTER_THRESHOLD:
            if self.current_state == SecurityState.NORMAL:
                self.current_state = SecurityState.ELEVATED
        elif self.current_state in (SecurityState.ELEVATED, SecurityState.RECOVERY):
            if time_in_state >= self.min_state_dwell_time:
                if guild_heat < self.ELEVATED_EXIT_THRESHOLD and raid_heat < self.ELEVATED_EXIT_THRESHOLD:
                    self.current_state = SecurityState.NORMAL
                    self.raid_substate = RaidSubState.NONE

        changed = self.current_state != prev_state
        if changed:
            self.last_transition_time = now

        return self.current_state, changed


def calculate_risk(
    base_score: float,
    confidence: float,
    trust: TrustLevel,
    cross_action_score: float = 0.0,
    is_raid_active: bool = False
) -> tuple[float, Severity]:
    """
    Calculate composite risk score (0 to 100) and severity rating from evidence,
    actor trust level, confidence, and cross-action context.
    """
    # Trust modifiers (lower risk for trusted, higher for suspicious)
    trust_multiplier = {
        TrustLevel.OWNER: 0.1,
        TrustLevel.TRUSTED: 0.3,
        TrustLevel.STAFF: 0.5,
        TrustLevel.MEMBER: 1.0,
        TrustLevel.NEW_MEMBER: 1.25,
        TrustLevel.UNKNOWN: 1.15,
        TrustLevel.SUSPICIOUS: 1.5,
        TrustLevel.QUARANTINED: 1.8,
    }.get(trust, 1.0)

    # Base weighted by confidence
    effective_score = base_score * (0.5 + 0.5 * min(1.0, max(0.1, confidence)))
    effective_score += cross_action_score * 0.4
    if is_raid_active:
        effective_score *= 1.2

    final_risk = min(100.0, max(0.0, effective_score * trust_multiplier))

    # Map to severity
    if final_risk >= 85.0:
        severity = Severity.CRITICAL
    elif final_risk >= 65.0:
        severity = Severity.HIGH
    elif final_risk >= 45.0:
        severity = Severity.MEDIUM
    elif final_risk >= 25.0:
        severity = Severity.LOW
    else:
        severity = Severity.INFO

    return final_risk, severity
