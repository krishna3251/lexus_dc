"""Deterministic Discord report presentation; no model calls or factual rewriting."""
from __future__ import annotations

import html
import re


_CODE = re.compile(r"(```[\s\S]*?(?:```|\Z)|~~~[\s\S]*?(?:~~~|\Z)|`[^`\n]+`)")
_CITATION = re.compile(r"\[\s*[Ss]\s*\d+(?:\s*[,;]\s*[Ss]?\s*\d+)*\s*\]")


def map_citations(text: str, replace) -> str:
    """Normalize spaced/grouped source IDs outside literal code."""
    parts = _CODE.split(text)
    for index in range(0, len(parts), 2):
        parts[index] = _CITATION.sub(
            lambda match: " ".join(replace("S" + number) for number in re.findall(r"\d+", match.group())),
            parts[index],
        )
        parts[index] = re.sub(r"(?<=\])(?=\[S\d+\])", " ", parts[index])
    return "".join(parts)


def normalize_report(text: str) -> str:
    """Clean prose transport artifacts while preserving fenced/inline code."""
    parts = _CODE.split(text.strip())
    for index in range(0, len(parts), 2):
        prose = html.unescape(parts[index]).replace("\u00a0", " ").replace("\u202f", " ")
        prose = re.sub(r"\\[ \t]*\n", "\n", prose)
        prose = re.sub(r"[ \t]+(?=\r?\n)", "", prose)
        # Remove a report's accidental outer list wrapper, not numbered steps.
        prose = re.sub(r"^\d+[.)]\s+(?=(?:#{1,6}\s|\*\*[^\n*]+\*\*[ \t]*$))", "", prose, flags=re.M)
        if index == 0:
            prose = re.sub(r"^\*\*([^*\n]+)\*\*(?=\n|$)", r"## \1", prose)
        prose = re.sub(r"^#\s+", "## ", prose, flags=re.M)
        prose = re.sub(r"^\*\*Bottom line:\*\*", "**Impact:**", prose, flags=re.M | re.I)
        prose = re.sub(r"(?<!\n)\n(?=(?:#{1,6}\s|[-•]\s|\*\*[^\n*]+\*\*[:\n]))", "\n\n", prose)
        prose = re.sub(r"(^#{1,6}[^\n]+)\n(?=\S)", r"\1\n\n", prose, flags=re.M)
        prose = re.sub(r"\n{3,}", "\n\n", prose)
        parts[index] = prose
    return map_citations("".join(parts), lambda source_id: f"[{source_id}]").strip()


def _label(text: str, maximum: int) -> str:
    text = " ".join(html.unescape(str(text)).split())
    text = re.sub(r"[\[\]`*_<>|\\]", "", text)
    if len(text) > maximum:
        text = text[:maximum - 1].rsplit(" ", 1)[0] + "…"
    return text or "Source"


def _without_model_sources(text: str) -> str:
    parts = _CODE.split(text)
    heading = re.compile(r"(?im)^(?:\d+[.)]\s+)?(?:#{1,6}\s+)?(?:\*\*)?(?:sources|references|source links)(?:\*\*)?\s*(?::|$)")
    for index in range(0, len(parts), 2):
        match = heading.search(parts[index])
        if match:
            return ("".join(parts[:index]) + parts[index][:match.start()]).rstrip()
    return text


def format_research_report(answer: str, sources) -> str:
    from .ai_engine.research import public_source_url

    body = normalize_report(answer)
    valid, seen = [], set()
    for source in sources:
        url = public_source_url(source.url)
        if not url or source.source_id in seen or not re.fullmatch(r"S\d+", source.source_id):
            continue
        seen.add(source.source_id)
        valid.append((source, url))
        if len(valid) >= 10:
            break
    if not valid:
        return body
    # The application owns the source list; discard a model-generated duplicate.
    body = _without_model_sources(body)
    numbers = {source.source_id: str(index) for index, (source, _) in enumerate(valid, 1)}
    body = map_citations(body, lambda source_id: f"[{numbers[source_id]}]" if source_id in numbers else "[source unverified]")
    lines = [body, "", "### Sources", ""]
    for index, (source, url) in enumerate(valid, 1):
        title = _label(source.title or source.domain, 82)
        domain = _label(source.domain.removeprefix("www."), 40) if source.domain else ""
        label = title if not domain or domain.casefold() in title.casefold() else f"{domain} · {title}"
        safe_url = url.replace("<", "%3C").replace(">", "%3E")
        lines.extend([f"[{index}] [{label}](<{safe_url}>)", ""])
    return "\n".join(lines).strip()
