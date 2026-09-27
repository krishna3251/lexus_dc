"""
Incident management, correlation, and tracking for Lexus Security Engine.
Groups related events, evidence, and actions into structured security incidents.
"""

from __future__ import annotations
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Optional, Any
from security.models import (
    SecurityEvent,
    Evidence,
    ActionResult,
    Severity,
    SecurityState
)
from services.cache import TTLCache
from services.database import security_db


@dataclass
class Incident:
    incident_id: str
    guild_id: int
    primary_actor: Optional[int]
    severity: Severity = Severity.LOW
    score: float = 0.0
    confidence: float = 0.5
    state: str = "OPEN"  # OPEN, CONTAINED, RESOLVED, CLOSED
    events: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["severity"] = self.severity.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Incident:
        sev_str = data.get("severity", "LOW")
        try:
            sev = Severity(sev_str)
        except ValueError:
            sev = Severity.LOW
        return cls(
            incident_id=data["incident_id"],
            guild_id=data["guild_id"],
            primary_actor=data.get("primary_actor"),
            severity=sev,
            score=data.get("score", 0.0),
            confidence=data.get("confidence", 0.5),
            state=data.get("state", "OPEN"),
            events=data.get("events", []),
            evidence=data.get("evidence", []),
            actions=data.get("actions", []),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time())
        )

    def add_event(self, event: SecurityEvent) -> None:
        self.events.append(event.to_dict())
        self.updated_at = time.time()

    def add_evidence(self, ev: Evidence) -> None:
        self.evidence.append(ev.to_dict())
        # Update score and confidence
        if ev.score > self.score:
            self.score = ev.score
        self.confidence = max(self.confidence, ev.confidence)
        self.updated_at = time.time()

    def add_action(self, action: ActionResult) -> None:
        self.actions.append(action.to_dict())
        self.updated_at = time.time()


class IncidentManager:
    """
    Manages active security incidents, correlates incoming events,
    and coordinates persistence.
    """

    def __init__(self, ttl: float = 300.0, max_active: int = 500):
        # Maps actor/target key -> incident_id
        self._actor_to_incident: TTLCache[tuple[int, int], str] = TTLCache(max_size=max_active, default_ttl=ttl)
        # Maps incident_id -> Incident
        self._incidents: TTLCache[str, Incident] = TTLCache(max_size=max_active, default_ttl=ttl * 2)

    def find_correlated_incident(self, guild_id: int, actor_id: Optional[int]) -> Optional[Incident]:
        """Find an active open incident for the given guild and actor."""
        if not actor_id:
            return None
        key = (guild_id, actor_id)
        inc_id = self._actor_to_incident.get(key)
        if inc_id:
            incident = self._incidents.get(inc_id)
            if incident and incident.state in ("OPEN", "CONTAINED"):
                return incident
        return None

    def create_incident(
        self,
        guild_id: int,
        primary_actor: Optional[int],
        initial_event: SecurityEvent,
        evidence: Optional[Evidence] = None,
        severity: Severity = Severity.LOW
    ) -> Incident:
        """Create and track a new security incident."""
        inc_id = f"INC-{uuid.uuid4().hex[:6].upper()}"
        incident = Incident(
            incident_id=inc_id,
            guild_id=guild_id,
            primary_actor=primary_actor,
            severity=severity,
            score=evidence.score if evidence else 0.0,
            confidence=evidence.confidence if evidence else 0.5
        )
        incident.add_event(initial_event)
        if evidence:
            incident.add_evidence(evidence)

        self._incidents.set(inc_id, incident)
        if primary_actor:
            self._actor_to_incident.set((guild_id, primary_actor), inc_id)

        return incident

    def get_incident(self, incident_id: str) -> Optional[Incident]:
        return self._incidents.get(incident_id)

    async def persist_incident(self, incident: Incident) -> bool:
        return await security_db.save_incident(incident.to_dict())
