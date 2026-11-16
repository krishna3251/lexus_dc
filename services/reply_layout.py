"""Select native Discord layouts from the structure of a completed answer."""
from __future__ import annotations

import re

import discord

from .discord_output import _MASKED_LINK, discord_length, split_reply
from .source_cards import ACCENT, _short, linked_sources, sources_button


_ITEM = re.compile(r"(?m)^(?=(?:\d+[.)]|[-•])\s+)")
_FACT = re.compile(r"(?:[-•] )?(?:\*\*)?([^:*\n]{1,60}):(?:\*\*)?\s*(.{1,120})")
_HEADING = re.compile(r"(?m)^#{1,3} (.+)$")


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


def _embed_layout(embed, sources, body):
    layout = {"embed": embed}
    if sources:
        toolbar = discord.ui.View(timeout=900)
        toolbar.add_item(sources_button(sources, body))
        layout["view"] = toolbar
    return layout


class ReplyCard(discord.ui.LayoutView):
    def __init__(self, title, pages, owner_id, index=0, sources=(), body=""):
        super().__init__(timeout=900)
        items = [discord.ui.TextDisplay(f"## {title}"), discord.ui.Separator()]
        for block in pages[index]:
            items.append(discord.ui.TextDisplay(block))
        if sources:
            visible = [source for source in sources if f"](<{source.url}>)" in "\n".join(pages[index])]
            items.append(discord.ui.Separator())
            for source in (visible or sources)[:2]:
                label = discord.utils.escape_markdown(_short(source.title, 90))
                items.append(discord.ui.Section(
                    discord.ui.TextDisplay(f"**{label}**\n-# {_short(source.domain, 80)}"),
                    accessory=discord.ui.Button(label="Open article", url=source.url),
                ))
            items.append(discord.ui.ActionRow(sources_button(sources, body)))
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
                        view=ReplyCard(title, pages, owner_id, destination, sources, body),
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
    body, sources = linked_sources(text.strip())
    heading = _HEADING.match(body)
    title = heading[1].strip() if heading else ""
    if title and discord_length(title) <= 200:
        body = body[heading.end():].strip()
    else:
        title = ""
    if not body:
        return {}
    comparison = _comparison_embed(title, body)
    if comparison:
        return _embed_layout(comparison, sources, body)
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    facts = [_FACT.fullmatch(line) for line in lines]
    if 2 <= len(lines) <= 8 and all(facts) and not sources:
        embed = discord.Embed(title=title or "At a glance", colour=ACCENT)
        for fact in facts:
            embed.add_field(name=fact[1].strip(), value=fact[2], inline=True)
        return {"embed": embed}

    blocks = [s.strip() for s in _ITEM.split(body) if s.strip()]
    listed = len(_ITEM.findall(body)) >= 2
    if not listed:
        blocks = [s.strip() for s in re.split(r"\n(?=#{1,3} )|\n\s*\n", body) if s.strip()]
    if sources and not listed and len(blocks) <= 2 and discord_length(body) < 1000:
        embed = discord.Embed(title=title or (_short(sources[0].title, 200) if len(sources) == 1 else "Search results"),
                              description=body, colour=ACCENT)
        if len(sources) == 1:
            embed.url = sources[0].url
            embed.set_footer(text=_short(sources[0].domain, 120))
        return _embed_layout(embed, sources, body)
    if not (listed or title or sources):
        return {}
    # Keep each finding intact and reserve room for the card title and controls.
    # Keep standalone section headings with their opening paragraph.
    joined = []
    for block in blocks:
        if joined and _HEADING.fullmatch(joined[-1]):
            joined[-1] += "\n" + block
        else:
            joined.append(block)
    if any(discord_length(link[0]) > 2700 for link in _MASKED_LINK.finditer(body)):
        return {}
    pages, page, used = [], [], 0
    chunks = [part for block in joined for part in split_reply(block, 2700)]
    for block in chunks:
        size = discord_length(block)
        if page and (used + size > 2700 or len(page) == 5):
            pages.append(page)
            page, used = [], 0
        page.append(block)
        used += size
    pages.append(page)
    if len(pages) > 1 and not owner_id:
        return {}
    return {"view": ReplyCard(title or ("Search results" if sources else "Answer"), pages, owner_id, sources=sources, body=body),
            **({"attach_full": True} if len(pages) > 1 else {})}
