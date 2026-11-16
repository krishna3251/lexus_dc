"""Select native Discord layouts from the structure of a completed answer."""
from __future__ import annotations

import re
from urllib.parse import urlsplit

import discord

from .discord_output import discord_length
from .ai_engine.research import public_source_url


ACCENT = 0x35BFFF
_SOURCE = re.compile(r"\[(\d+)\] \[[^\n]*\]\(<([^<>\s]+)>\)")
_ITEM = re.compile(r"(?m)^(?=(?:\d+[.)]|[-•])\s+)")
_FACT = re.compile(r"(?:[-•] )?(?:\*\*)?([^:*\n]{1,60}):(?:\*\*)?\s*(.{1,120})")
_HEADING = re.compile(r"(?m)^#{1,3} (.+)$")


def _linked_body(text):
    body, separator, appendix = text.rpartition("\n### Sources\n")
    if not separator:
        return text, False
    links = {}
    for line in appendix.strip().splitlines():
        if not line.strip():
            continue
        match = _SOURCE.fullmatch(line)
        if not match or not public_source_url(match[2]):
            return text, False
        host = urlsplit(match[2]).hostname.removeprefix("www.")
        links[match[1]] = f"[{host}](<{match[2]}>)"
    used = set()

    def replace(match):
        key = match[1]
        if key in links:
            used.add(key)
            return links[key]
        return match[0]

    # Inline literals and existing Markdown links are already formatted.
    parts = re.split(r"(`[^`\n]*`|\[[^\]\n]+\]\([^\n]+?\))", body)
    for i in range(0, len(parts), 2):
        parts[i] = re.sub(r"\[(\d+)\]", replace, parts[i])
    body = "".join(parts).strip()
    unused = [link for key, link in links.items() if key not in used]
    if unused:
        body += "\n\nAdditional sources · " + " · ".join(unused)
    return body, bool(links)


def _comparison_embed(title, body):
    """Render a small, standalone Markdown table as stacked, mobile-readable fields."""
    lines = body.splitlines()
    if not 4 <= len(lines) <= 10 or any("|" not in line for line in lines):
        return None
    if "\\|" in body or "`" in body:
        return None
    rows = [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines]
    headers, rule, *entries = rows
    if not 2 <= len(headers) <= 5 or any(len(row) != len(headers) for row in rows):
        return None
    if not all(headers) or not all(re.fullmatch(r":?-{3,}:?", cell) for cell in rule):
        return None
    embed = discord.Embed(title=title or "Comparison", colour=ACCENT)
    for name, *values in entries:
        value = "\n".join(f"**{key}** · {cell}" for key, cell in zip(headers[1:], values))
        if not name or discord_length(name) > 256 or discord_length(value) > 1024:
            return None
        embed.add_field(name=name, value=value, inline=False)
    if sum(discord_length(f.name + f.value) for f in embed.fields) > 5500:
        return None
    return embed


class ReplyCard(discord.ui.LayoutView):
    def __init__(self, title, pages, owner_id, index=0):
        super().__init__(timeout=900)
        items = [discord.ui.TextDisplay(f"## {title}"), discord.ui.Separator()]
        for block in pages[index]:
            items.append(discord.ui.TextDisplay(block))
        if len(pages) > 1:
            items.extend([discord.ui.Separator(),
                          discord.ui.TextDisplay(f"-# Page {index + 1} of {len(pages)} · Full answer attached"),
                          discord.ui.File("attachment://lxeus-reply.md")])
            row = discord.ui.ActionRow()
            for label, target in (("Previous", index - 1), ("Next", index + 1)):
                button = discord.ui.Button(label=label, disabled=not 0 <= target < len(pages))

                async def navigate(interaction, destination=target):
                    if owner_id is not None and interaction.user.id != owner_id:
                        await interaction.response.send_message("Only the person who asked can turn these pages.", ephemeral=True)
                        return
                    await interaction.response.edit_message(
                        view=ReplyCard(title, pages, owner_id, destination),
                        allowed_mentions=discord.AllowedMentions.none(),
                    )

                button.callback = navigate
                row.add_item(button)
            items.append(row)
        self.add_item(discord.ui.Container(*items, accent_colour=ACCENT))


def choose_layout(text, owner_id=None):
    """Return send kwargs, or an empty dict to use the Markdown/file sender."""
    if not text.strip() or "```" in text or "~~~" in text or discord_length(text) > 24000:
        return {}
    body, sourced = _linked_body(text.strip())
    heading = _HEADING.match(body)
    title = heading[1].strip() if heading else ""
    if title and len(title) <= 200:
        body = body[heading.end():].strip()
    else:
        title = ""
    if not body:
        return {}
    comparison = _comparison_embed(title, body)
    if comparison:
        return {"embed": comparison}
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    facts = [_FACT.fullmatch(line) for line in lines]
    if 2 <= len(lines) <= 8 and all(facts) and not sourced:
        embed = discord.Embed(title=title or "At a glance", colour=ACCENT)
        for fact in facts:
            embed.add_field(name=fact[1].strip(), value=fact[2], inline=True)
        return {"embed": embed}

    blocks = [s.strip() for s in _ITEM.split(body) if s.strip()]
    listed = len(_ITEM.findall(body)) >= 2
    if not listed:
        blocks = [s.strip() for s in re.split(r"\n(?=#{1,3} )|\n\s*\n", body) if s.strip()]
    if sourced and not listed and len(blocks) <= 2 and discord_length(body) < 1000:
        return {"embed": discord.Embed(title=title or "Research answer", description=body, colour=ACCENT)}
    if not (listed or title or sourced or discord_length(body) >= 420):
        return {}
    # Keep each finding intact and reserve room for the card title and controls.
    # Keep standalone section headings with their opening paragraph.
    joined = []
    for block in blocks:
        if joined and _HEADING.fullmatch(joined[-1]):
            joined[-1] += "\n" + block
        else:
            joined.append(block)
    pages, page, used = [], [], 0
    for block in joined:
        size = discord_length(block)
        if size > 3400:
            return {}
        if page and (used + size > 3400 or len(page) == 5):
            pages.append(page)
            page, used = [], 0
        page.append(block)
        used += size
    pages.append(page)
    if len(pages) > 1 and not owner_id:
        return {}
    return {"view": ReplyCard(title or ("Briefing" if sourced else "Answer"), pages, owner_id),
            **({"attach_full": True} if len(pages) > 1 else {})}
