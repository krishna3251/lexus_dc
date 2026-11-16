"""Link-aware Discord source previews built only from the completed reply."""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote, urlsplit

import discord

from .ai_engine.research import public_source_url
from .report_formatting import _CODE, _label
from .discord_output import discord_length


ACCENT = 0x35BFFF
_SOURCE = re.compile(r"\[(\d+)\] \[([^\n]*)\]\(<([^<>\s]+)>\)")
_LINK = re.compile(
    r'\[(?P<label>(?:\\.|[^\]\\\n])+)\]\('
    r'(?:<(?P<angle>https?://[^>\s]+)>|'
    r'(?P<url>https?://(?:[^\s()<>]|\((?:[^\s()<>]|\([^\s()<>]*\))*\))+))'
    r'(?:\s+"[^"\n]*")?\)'
    r'|<(?P<auto>https?://[^>\s]+)>'
    r'|(?P<bare>https?://[^\s<>]+)',
    re.I,
)


@dataclass(frozen=True)
class SourceLink:
    title: str
    url: str
    domain: str


def _safe_link(url):
    if not public_source_url(url):
        return None
    # Preserve fragments and encoded paths while escaping Markdown delimiters.
    return quote(url, safe=":/?#[]@!$&'+,;=%~-")


def _short(text, limit):
    text = " ".join(text.split())
    if discord_length(text) <= limit:
        return text
    prefix = text.encode("utf-16-le")[:(limit - 1) * 2].decode("utf-16-le", errors="ignore")
    return prefix + "…"


def linked_sources(text):
    """Keep authored links, shorten bare URLs and resolve the app's source IDs.

    Literal code is untouched. A malformed appendix stays visible. No URL is fetched.
    """
    sources, positions, references = [], {}, {}

    def add(url, title=""):
        safe = _safe_link(url)
        if not safe:
            return None
        if safe not in positions:
            domain = urlsplit(safe).hostname.removeprefix("www.")
            positions[safe] = len(sources)
            sources.append(SourceLink(_label(title or domain, 200), safe, domain))
        return positions[safe]

    body, marker, appendix = text.rpartition("\n### Sources\n")
    entries = [_SOURCE.fullmatch(line) for line in appendix.splitlines() if line.strip()]
    if marker and entries and all(entry and _safe_link(entry[3]) for entry in entries):
        for entry in entries:
            references[entry[1]] = add(entry[3], entry[2])
    else:
        body = text
    parts = _CODE.split(body)
    for index in range(0, len(parts), 2):
        # Use one pass over the original text, keeping replacement links out of the parser.
        def replace(match):
            url = match["angle"] or match["url"] or match["auto"] or match["bare"]
            suffix = ""
            if match["bare"]:
                trimmed = url.rstrip(".,;:!?*_~")
                while trimmed.endswith(")") and trimmed.count(")") > trimmed.count("("):
                    trimmed = trimmed[:-1]
                suffix = url[len(trimmed):]
                url = trimmed
            position = add(url, match["label"] or "")
            if position is None:
                return match[0]
            source = sources[position]
            label = match["label"] or source.domain
            return f"[{label}](<{source.url}>)" + suffix

        # Protect every recognized link while replacing numeric citation IDs.
        pieces, start = [], 0
        for match in _LINK.finditer(parts[index]):
            pieces.append(_citations(parts[index][start:match.start()], references, sources))
            pieces.append(replace(match))
            start = match.end()
        pieces.append(_citations(parts[index][start:], references, sources))
        parts[index] = "".join(pieces)
    return "".join(parts).strip(), tuple(sources)


def _citations(text, references, sources):
    def replace(match):
        position = references.get(match[1])
        if position is None:
            return match[0]
        source = sources[position]
        return f"[{position + 1} · {source.domain}](<{source.url}>)"
    return re.sub(r"\[(\d+)\]", replace, text)


class SourceBrowser(discord.ui.LayoutView):
    """An individual reader browses every result in a private Discord message."""
    def __init__(self, sources, body, selected=0):
        super().__init__(timeout=900)
        source = sources[selected]
        heading = discord.ui.Section(
            discord.ui.TextDisplay(f"### {discord.utils.escape_markdown(_short(source.title, 200))}\n{_short(source.domain, 120)}"),
            accessory=discord.ui.Button(label="Open article", url=source.url),
        )
        items = [heading]
        contexts = [block for block in re.split(r"\n\s*\n", body) if f"](<{source.url}>)" in block]
        if contexts:
            context = contexts[0]
            if discord_length(context) > 1800:
                context = "This result is linked in the answer above."
            items.extend([discord.ui.Separator(), discord.ui.TextDisplay("**In this answer**\n" + context)])
        items.append(discord.ui.TextDisplay(f"-# Source {selected + 1} of {len(sources)} · Controls active for 15 min"))
        start = selected // 25 * 25
        menu = discord.ui.Select(placeholder="Choose a source", options=[
            discord.SelectOption(label=_short(f"{i + 1}. {item.title}", 100), value=str(i),
                                 description=_short(item.domain, 100), default=i == selected)
            for i, item in enumerate(sources[start:start + 25], start)
        ])

        async def select(interaction):
            await interaction.response.edit_message(
                view=SourceBrowser(sources, body, int(menu.values[0])),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        menu.callback = select
        items.append(discord.ui.ActionRow(menu))
        if len(sources) > 25:
            row = discord.ui.ActionRow()
            for label, target in (("Previous sources", start - 25), ("Next sources", start + 25)):
                button = discord.ui.Button(label=label, disabled=not 0 <= target < len(sources))

                async def navigate(interaction, destination=target):
                    await interaction.response.edit_message(
                        view=SourceBrowser(sources, body, destination),
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                button.callback = navigate
                row.add_item(button)
            items.append(row)
        self.add_item(discord.ui.Container(*items, accent_colour=ACCENT))


def sources_button(sources, body):
    button = discord.ui.Button(label=f"Sources · {len(sources)}", style=discord.ButtonStyle.secondary)

    async def open_sources(interaction):
        await interaction.response.send_message(
            view=SourceBrowser(sources, body), ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )
    button.callback = open_sources
    return button
