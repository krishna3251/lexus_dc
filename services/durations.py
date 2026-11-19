"""Parse durations used by scheduled Discord commands."""

import re

_PART = re.compile(r"([0-9]+)\s*(week|day|hour|min|sec|hr|[smhdw])", re.IGNORECASE)
_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
_MAX_SECONDS = 365 * 86400


def parse_duration(text: str) -> int | None:
    total = 0
    end = 0
    for match in _PART.finditer(text):
        if text[end:match.start()].strip() or len(match[1]) > 8:
            return None
        total += int(match[1]) * _SECONDS[match[2][0].lower()]
        end = match.end()
    if text[end:].strip() or not 0 < total <= _MAX_SECONDS:
        return None
    return total
