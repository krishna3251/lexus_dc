"""
Message spam detection engine for Lexus Security Engine.
Detects burst frequency, exact repeats, near-duplicate text, mention floods,
invite/link floods, attachment bursts, and channel hopping without heavy ML dependencies.
"""

from __future__ import annotations
import re
import hashlib
import time
from typing import Optional, Any
from security.models import Evidence, SecurityEvent
from security.event_tracker import SlidingWindow
from services.cache import TTLCache


# Regex patterns
DISCORD_INVITE_REGEX = re.compile(
    r"(?:https?://)?(?:www\.)?(?:discord\.(?:gg|io|me|li)|discord(?:app)?\.com/invite)/[a-zA-Z0-9\-]+",
    re.IGNORECASE
)
URL_REGEX = re.compile(r"https?://[^\s]+", re.IGNORECASE)
REPEATED_CHARS_REGEX = re.compile(r"(.)\1{3,}")


def normalize_content(content: str) -> str:
    """Normalize text: lowercase, collapse whitespace, and reduce repeated characters."""
    if not content:
        return ""
    text = content.lower().strip()
    # Strip harmless trailing punctuation
    text = re.sub(r"[!?.~]+$", "", text)
    # Collapse repeated chars: "freeeee" -> "free"
    text = REPEATED_CHARS_REGEX.sub(r"\1\1", text)
    # Collapse multiple whitespaces/newlines
    text = re.sub(r"\s+", " ", text).strip()
    return text


def text_signature(text: str) -> set[str]:
    """Tokenize normalized text into a set of words for Jaccard similarity."""
    return set(re.findall(r"\b\w+\b", text))


def jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a.intersection(set_b))
    union = len(set_a.union(set_b))
    return float(intersection) / float(union) if union > 0 else 0.0


class SpamDetector:
    """
    Evaluates message activity against multiple behavioral indicators.
    Returns Evidence object if suspicious, or None if benign.
    """

    def __init__(self):
        # User message windows: (guild_id, user_id) -> SlidingWindow(5s)
        self._fast_msg_windows: TTLCache[tuple[int, int], SlidingWindow] = TTLCache(max_size=3000, default_ttl=60.0)
        # Recent message hashes per user: (guild_id, user_id) -> list[(hash, text_tokens, timestamp)]
        self._user_recent_hashes: TTLCache[tuple[int, int], list[tuple[str, set[str], float]]] = TTLCache(max_size=3000, default_ttl=60.0)
        # Channel hopping: (guild_id, user_id) -> list[(channel_id, timestamp)]
        self._channel_hops: TTLCache[tuple[int, int], list[tuple[int, float]]] = TTLCache(max_size=3000, default_ttl=60.0)

    def evaluate(self, event: SecurityEvent) -> Optional[Evidence]:
        """Analyze message event for spam patterns."""
        guild_id = event.guild_id
        user_id = event.actor_id
        if not user_id:
            return None

        metadata = event.metadata or {}
        raw_content = metadata.get("content", "")
        norm_content = normalize_content(raw_content)
        user_key = (guild_id, user_id)
        now = time.monotonic()

        reasons: list[str] = []
        score = 0.0
        confidence = 0.7

        # 1. Fast message burst (sliding window 5 seconds)
        fast_win = self._fast_msg_windows.get(user_key)
        if fast_win is None:
            fast_win = SlidingWindow(window_seconds=5.0, max_size=20)
            self._fast_msg_windows.set(user_key, fast_win)
        count_5s = fast_win.add(now)

        if count_5s >= 8:
            score += 50.0
            reasons.append(f"Fast message burst ({count_5s} msgs in 5s)")
        elif count_5s >= 5:
            score += 25.0
            reasons.append(f"Elevated message rate ({count_5s} msgs in 5s)")

        # 2. Exact repeat and near-duplicate text
        if norm_content and len(norm_content) >= 4:
            msg_hash = hashlib.sha256(norm_content.encode("utf-8")).hexdigest()[:16]
            tokens = text_signature(norm_content)

            recent_history = self._user_recent_hashes.get(user_key) or []
            # Purge items older than 20 seconds
            recent_history = [item for item in recent_history if (now - item[2]) < 20.0]

            exact_repeats = sum(1 for h, _, _ in recent_history if h == msg_hash)
            if exact_repeats >= 3:
                score += 45.0
                reasons.append(f"Repeated identical messages ({exact_repeats + 1}x)")
            elif exact_repeats >= 2:
                score += 25.0
                reasons.append("Repeated duplicate message content")

            # Near-duplicate check
            for _, prev_tokens, _ in recent_history:
                sim = jaccard_similarity(tokens, prev_tokens)
                if sim >= 0.70 and exact_repeats == 0:
                    score += 35.0
                    reasons.append(f"Near-duplicate spam (similarity {sim:.2f})")
                    break

            recent_history.append((msg_hash, tokens, now))
            self._user_recent_hashes.set(user_key, recent_history)

        # 3. Mention flood
        mentions_count = metadata.get("mentions_count", 0)
        has_everyone = metadata.get("mention_everyone", False)
        if has_everyone:
            score += 40.0
            reasons.append("@everyone or @here mention")
        if mentions_count >= 10:
            score += 60.0
            reasons.append(f"Mass mention flood ({mentions_count} mentions)")
        elif mentions_count >= 5:
            score += 30.0
            reasons.append(f"High mention count ({mentions_count} mentions)")

        # 4. Invite & Link Spam
        if raw_content:
            invites = DISCORD_INVITE_REGEX.findall(raw_content)
            if invites:
                score += 35.0
                reasons.append("Discord invite link posted")

            urls = URL_REGEX.findall(raw_content)
            if len(urls) >= 4:
                score += 40.0
                reasons.append(f"Link burst ({len(urls)} URLs)")

        # 5. Media / Attachment flood
        attachments_count = metadata.get("attachments_count", 0)
        if attachments_count >= 5:
            score += 35.0
            reasons.append(f"Attachment burst ({attachments_count} files)")

        # 6. Channel hopping
        channel_id = event.channel_id
        if channel_id:
            hops = self._channel_hops.get(user_key) or []
            hops = [h for h in hops if (now - h[1]) < 10.0]
            distinct_channels = {h[0] for h in hops}
            if channel_id not in distinct_channels and len(distinct_channels) >= 3:
                score += 30.0
                reasons.append(f"Cross-channel hopping ({len(distinct_channels) + 1} channels in 10s)")
            hops.append((channel_id, now))
            self._channel_hops.set(user_key, hops)

        if score >= 25.0:
            return Evidence(
                detector_name="SpamDetector",
                score=min(100.0, score),
                confidence=min(1.0, max(0.6, confidence)),
                reason="; ".join(reasons),
                metadata={"count_5s": count_5s, "reasons": reasons}
            )

        return None
