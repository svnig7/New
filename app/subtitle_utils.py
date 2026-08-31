import re

_ASS_TAG_RE = re.compile(r"\{.*?\}")


def srt_to_vtt(srt_text: str) -> str:
    body = srt_text.replace("\r\n", "\n").strip()
    # SRT uses a comma for milliseconds; VTT requires a dot.
    body = re.sub(r"(\d{2}:\d{2}:\d{2}),(\d{3})", r"\1.\2", body)
    # Drop pure sequence-number lines (a line that's only digits).
    lines = [ln for ln in body.split("\n") if not re.fullmatch(r"\d+", ln.strip())]
    return "WEBVTT\n\n" + "\n".join(lines) + "\n"


def ass_to_vtt(ass_text: str) -> str:
    """
    Best-effort ASS -> VTT: pulls Dialogue lines, strips override tags,
    converts timestamps. Positioning, karaoke and styling effects aren't
    preserved -- for pixel-accurate ASS rendering you'd want a real
    renderer (e.g. libass compiled to WASM) instead of text extraction.
    """
    cues = []
    idx = 1
    for line in ass_text.splitlines():
        if not line.startswith("Dialogue:"):
            continue
        parts = line.split(",", 9)
        if len(parts) < 10:
            continue
        start, end, text = parts[1].strip(), parts[2].strip(), parts[9]
        text = _ASS_TAG_RE.sub("", text).replace("\\N", "\n").strip()
        if not text:
            continue
        cues.append(f"{idx}\n{_ass_ts(start)} --> {_ass_ts(end)}\n{text}\n")
        idx += 1
    return "WEBVTT\n\n" + "\n".join(cues)


def _ass_ts(ts: str) -> str:
    # ASS: H:MM:SS.cc  ->  VTT: HH:MM:SS.ccc
    h, m, s = ts.split(":")
    sec, cs = s.split(".")
    return f"{int(h):02d}:{m}:{sec}.{int(cs) * 10:03d}"
