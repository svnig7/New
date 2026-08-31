import re
import shlex

TTL_RE = re.compile(r"^(\d+)([smhd])$", re.IGNORECASE)
UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_ttl(value: str):
    m = TTL_RE.match(value.strip())
    if not m:
        return None
    n, unit = m.groups()
    return int(n) * UNITS[unit.lower()]


def human_ttl(seconds: int) -> str:
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds % size == 0 and seconds >= size:
            return f"{seconds // size}{unit}"
    return f"{seconds}s"


def parse_stream_args(text: str) -> dict:
    """
    Parses flags out of a /stream command's argument text:
      -pl <name>   add to / create a playlist (quote multi-word names)
      -t <url>     custom thumbnail shown on the watch page
      -ttl <time>  self-expiring link, e.g. 30m, 2h, 1d
    """
    try:
        parts = shlex.split(text)
    except ValueError:
        parts = text.split()

    out = {"playlist": None, "thumb": None, "ttl": None}
    i = 0
    while i < len(parts):
        tok = parts[i]
        if tok == "-pl" and i + 1 < len(parts):
            out["playlist"] = parts[i + 1]
            i += 2
        elif tok == "-t" and i + 1 < len(parts):
            out["thumb"] = parts[i + 1]
            i += 2
        elif tok == "-ttl" and i + 1 < len(parts):
            secs = parse_ttl(parts[i + 1])
            if secs:
                out["ttl"] = secs
            i += 2
        else:
            i += 1
    return out
