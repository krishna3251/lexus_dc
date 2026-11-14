"""Discord-sized prose and intact file delivery for large code replies."""
from __future__ import annotations

import io
import discord


def discord_length(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def split_reply(text: str, limit: int = 1900) -> list[str]:
    """Prefer paragraphs/lines/words; measure astral emoji conservatively."""
    if limit < 2:
        raise ValueError("Reply limit must be at least two")
    remaining = text.strip()
    parts = []
    while discord_length(remaining) > limit:
        units, end = 0, 0
        for char in remaining:
            units += 2 if ord(char) > 0xFFFF else 1
            if units > limit:
                break
            end += 1
        candidate = remaining[:end]
        for separator in ("\n\n", "\n", " "):
            boundary = candidate.rfind(separator)
            if boundary >= end // 2:
                end = boundary
                break
        parts.append(remaining[:end].rstrip())
        remaining = remaining[end:].lstrip()
    if remaining:
        parts.append(remaining)
    return parts


def prepare_reply(text: str) -> tuple[list[str], discord.File | None]:
    """Avoid splitting code fences or flooding a channel with a long answer."""
    if not text or not text.strip():
        return [], None
    if discord_length(text) > 1900 and ("```" in text or discord_length(text) > 7600):
        summary = "Full reply attached to keep the formatting intact."
        if "```" not in text:
            preview = split_reply(text, 1100)[0]
            summary = preview + "\n\nFull report attached."
        return [summary], discord.File(
            io.BytesIO(text.encode("utf-8")), filename="lxeus-reply.md",
        )
    return split_reply(text), None


async def send_reply(send, text: str, **kwargs) -> list:
    """Share delivery across prefix, natural and slash replies; never allow pings."""
    parts, attachment = prepare_reply(text)
    kwargs["allowed_mentions"] = discord.AllowedMentions.none()
    if attachment is not None:
        try:
            return [await send(parts[0], file=attachment, **kwargs)]
        except discord.Forbidden as exc:
            if exc.code != 50013:
                raise
            # A server may allow text but not attachments. Preserve the answer.
            parts = split_reply(text)
        finally:
            attachment.close()
    sent = []
    for part in parts:
        sent.append(await send(part, **kwargs))
    return sent
