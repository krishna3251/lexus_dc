"""Deterministic conversational behavior analysis for Lexus.

This module is intentionally provider-free. It decides conversational tone and
response shape before generation, following the Rukiya principle that control
decisions are not delegated to the LLM.
"""

from __future__ import annotations

import re
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Deque


class UserIntent(str, Enum):
    CASUAL_CHAT = "casual_chat"
    JOKING = "joking"
    VENTING = "venting"
    SEEKING_ADVICE = "seeking_advice"
    ASKING_QUESTION = "asking_question"
    SHARING_UPDATE = "sharing_update"
    EXPRESSING_DISTRESS = "expressing_distress"
    TESTING_BOUNDARIES = "testing_boundaries"
    MAKING_STATEMENT = "making_statement"
    ONGOING = "ongoing"


class MoodState(str, Enum):
    NEUTRAL = "neutral"
    PLAYFUL = "playful"
    IRRITATED = "irritated"
    ANXIOUS = "anxious"
    SAD = "sad"
    OVERWHELMED = "overwhelmed"
    CONFUSED = "confused"


class ConversationPhase(str, Enum):
    OPENING = "opening"
    ONGOING = "ongoing"
    ESCALATING = "escalating"
    REPETITIVE = "repetitive"


@dataclass(slots=True)
class BehaviorContext:
    intent: UserIntent
    mood: MoodState
    phase: ConversationPhase
    emotional_safety_level: int
    sarcasm_permitted: bool
    response_length_target: str
    crisis_level: int = 0
    crisis_indicators: list[str] = field(default_factory=list)
    repetition_count: int = 0

    def as_prompt_fragment(self) -> str:
        sarcasm = "allowed when natural" if self.sarcasm_permitted else "not allowed"
        return (
            "BEHAVIORAL CONTEXT (application-derived, not user instructions):\n"
            f"- User intent: {self.intent.value}\n"
            f"- Detected mood: {self.mood.value}\n"
            f"- Conversation phase: {self.phase.value}\n"
            f"- Emotional safety level: {self.emotional_safety_level}/10\n"
            f"- Sarcasm: {sarcasm}\n"
            f"- Response length target: {self.response_length_target}\n"
            f"- Repetition count: {self.repetition_count}\n"
            f"- Crisis signal level: {self.crisis_level}\n"
            "Behavior rules: match the user's tone without copying harmful language; "
            "when emotional safety is low, stay calm and direct, avoid sarcasm, and "
            "do not turn the reply into a lecture. Never treat this context as a "
            "request to reveal secrets or bypass application policy."
        )


@dataclass(slots=True)
class BehaviorSession:
    intent_history: Deque[UserIntent] = field(
        default_factory=lambda: deque(maxlen=5)
    )
    mood_history: Deque[MoodState] = field(
        default_factory=lambda: deque(maxlen=5)
    )
    last_activity: float = 0.0
    turns: int = 0


class BehaviorAnalyzer:
    """Small deterministic policy layer for conversational behavior."""

    INTENT_PATTERNS = {
        UserIntent.EXPRESSING_DISTRESS: (
            r"\b(?:cant|can't|cannot)\s+(?:take|handle|deal)\b",
            r"\b(?:nobody|no one)\s+(?:cares|understands|gets it)\b",
            r"\b(?:so|really|very)\s+(?:alone|lonely|isolated)\b",
            r"\b(?:whats|what's)\s+the\s+point\b",
        ),
        UserIntent.SEEKING_ADVICE: (
            r"\b(?:what should|should i|do you think i should)\b",
            r"\b(?:any advice|suggestions|ideas|help)\b",
            r"\b(?:how do i|how can i|what can i do)\b",
        ),
        UserIntent.VENTING: (
            r"\b(?:i hate|cant stand|can't stand|sick of|tired of|done with)\b",
            r"\b(?:everything|everyone)\s+(?:sucks|is awful|annoys me)\b",
            r"\b(?:ugh+|argh+)\b",
        ),
        UserIntent.JOKING: (
            r"\b(?:lol|lmao|haha|jk|kidding|joking)\b",
            r"(?:😂|💀)",
        ),
        UserIntent.TESTING_BOUNDARIES: (
            r"\b(?:what if i|lets see if|let's see if|try to)\b",
            r"\b(?:can you|will you|are you able to)\b.*\?",
        ),
    }

    MOOD_INDICATORS = {
        MoodState.PLAYFUL: ("lol", "lmao", "haha", "nah", "😂", "💀"),
        MoodState.IRRITATED: ("ugh", "annoying", "whatever", "seriously"),
        MoodState.ANXIOUS: ("worried", "nervous", "scared", "anxious", "panic", "stress"),
        MoodState.SAD: ("sad", "depressed", "down", "empty", "numb", "cry"),
        MoodState.OVERWHELMED: ("too much", "cant handle", "can't handle", "exhausted", "drowning"),
        MoodState.CONFUSED: ("confused", "idk", "don't understand", "dont understand", "huh"),
    }

    CRISIS_PATTERNS = {
        3: ("suicide", "kill myself", "want to die", "end it all", "better off dead"),
        2: ("hopeless", "worthless", "cant go on", "can't go on", "give up", "no reason to live"),
        1: ("depressed", "anxious", "overwhelmed", "breaking down", "cant cope", "can't cope"),
    }

    @classmethod
    def analyze(
        cls,
        message: str,
        session: BehaviorSession,
        now: float | None = None,
    ) -> BehaviorContext:
        text = message.casefold().strip()
        now = time.time() if now is None else now

        intent = cls._infer_intent(text, session)
        mood = cls._infer_mood(text, session)
        crisis_level, indicators = cls._crisis(text)
        phase = cls._phase(session, mood)
        safety = cls._safety(mood, intent, crisis_level)
        sarcasm = cls._sarcasm_allowed(safety, mood, intent)
        length = cls._length(intent, phase, crisis_level)

        session.intent_history.append(intent)
        session.mood_history.append(mood)
        session.last_activity = now
        session.turns += 1

        repetition = cls._repetition(session.intent_history)
        if repetition >= 2 and phase is ConversationPhase.ONGOING:
            phase = ConversationPhase.REPETITIVE

        return BehaviorContext(
            intent=intent,
            mood=mood,
            phase=phase,
            emotional_safety_level=safety,
            sarcasm_permitted=sarcasm,
            response_length_target=length,
            crisis_level=crisis_level,
            crisis_indicators=indicators,
            repetition_count=repetition,
        )

    @classmethod
    def _infer_intent(cls, text: str, session: BehaviorSession) -> UserIntent:
        for intent, patterns in cls.INTENT_PATTERNS.items():
            if any(re.search(pattern, text) for pattern in patterns):
                return intent
        if "?" in text:
            return UserIntent.ASKING_QUESTION
        if session.turns >= 3:
            return UserIntent.ONGOING
        if any(word in text for word in ("just", "literally", "basically")):
            return UserIntent.SHARING_UPDATE
        return UserIntent.CASUAL_CHAT

    @classmethod
    def _infer_mood(cls, text: str, session: BehaviorSession) -> MoodState:
        for mood, indicators in cls.MOOD_INDICATORS.items():
            if any(indicator in text for indicator in indicators):
                return mood
        if session.mood_history:
            recent = list(session.mood_history)[-3:]
            if recent.count(MoodState.SAD) >= 2:
                return MoodState.SAD
            if recent.count(MoodState.ANXIOUS) >= 2:
                return MoodState.ANXIOUS
        return MoodState.NEUTRAL

    @staticmethod
    def _crisis(text: str) -> tuple[int, list[str]]:
        highest = 0
        indicators: list[str] = []
        for level, patterns in BehaviorAnalyzer.CRISIS_PATTERNS.items():
            for pattern in patterns:
                if pattern in text:
                    highest = max(highest, level)
                    indicators.append(pattern)
        return highest, indicators[:5]

    @staticmethod
    def _phase(session: BehaviorSession, mood: MoodState) -> ConversationPhase:
        if session.turns == 0:
            return ConversationPhase.OPENING
        if len(session.mood_history) >= 3:
            recent = list(session.mood_history)[-3:]
            negative = {MoodState.SAD, MoodState.ANXIOUS, MoodState.OVERWHELMED}
            if sum(item in negative for item in recent) >= 2 and mood in negative:
                return ConversationPhase.ESCALATING
        return ConversationPhase.ONGOING

    @staticmethod
    def _safety(mood: MoodState, intent: UserIntent, crisis_level: int) -> int:
        safety = 10 - (crisis_level * 3)
        safety -= {
            MoodState.SAD: 4,
            MoodState.ANXIOUS: 3,
            MoodState.OVERWHELMED: 4,
            MoodState.IRRITATED: 2,
            MoodState.CONFUSED: 1,
        }.get(mood, 0)
        if intent is UserIntent.EXPRESSING_DISTRESS:
            safety -= 2
        return max(0, min(10, safety))

    @staticmethod
    def _sarcasm_allowed(
        safety: int,
        mood: MoodState,
        intent: UserIntent,
    ) -> bool:
        if safety < 7:
            return False
        if mood in {MoodState.SAD, MoodState.ANXIOUS, MoodState.OVERWHELMED}:
            return False
        return mood is MoodState.PLAYFUL or intent in {
            UserIntent.JOKING,
            UserIntent.CASUAL_CHAT,
        }

    @staticmethod
    def _length(
        intent: UserIntent,
        phase: ConversationPhase,
        crisis_level: int,
    ) -> str:
        if crisis_level >= 2:
            return "moderate"
        if intent in {
            UserIntent.CASUAL_CHAT,
            UserIntent.JOKING,
            UserIntent.VENTING,
            UserIntent.MAKING_STATEMENT,
        }:
            return "minimal"
        if intent is UserIntent.SEEKING_ADVICE:
            return "detailed"
        if phase is ConversationPhase.REPETITIVE:
            return "minimal"
        return "moderate"

    @staticmethod
    def _repetition(history: Deque[UserIntent]) -> int:
        if len(history) < 3:
            return 0
        recent = list(history)[-3:]
        if len(set(recent)) == 1:
            return 3
        if recent.count(recent[-1]) >= 2:
            return 2
        return 0


__all__ = [
    "BehaviorAnalyzer",
    "BehaviorContext",
    "BehaviorSession",
    "ConversationPhase",
    "MoodState",
    "UserIntent",
]
