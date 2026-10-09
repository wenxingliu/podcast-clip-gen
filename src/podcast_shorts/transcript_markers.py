from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

MARKER_RE = re.compile(
    r"^\s*<!--\s*CLIP_(START|END)\s+id=([A-Za-z0-9_-]+)\s*-->\s*$"
)
SPEAKER_RE = re.compile(r"(?m)^\s*[^\n：:]{1,30}[：:]\s*")


class MarkerError(ValueError):
    pass


@dataclass(frozen=True)
class Selection:
    id: str
    text: str
    alignment_text: str
    before_context: str
    after_context: str
    start_line: int
    end_line: int
    order: int


def _spoken(text: str) -> str:
    return SPEAKER_RE.sub("", text).strip()


def parse_transcript(path: str | Path) -> tuple[list[Selection], str]:
    source = Path(path).read_text(encoding="utf-8-sig")
    lines = source.splitlines(keepends=True)
    open_clip: tuple[str, int, int] | None = None
    seen: set[str] = set()
    raw: list[tuple[str, int, int, int, str]] = []
    marker_lines: set[int] = set()
    for index, line in enumerate(lines):
        match = MARKER_RE.match(line.rstrip("\r\n"))
        if not match:
            if "CLIP_START" in line or "CLIP_END" in line:
                raise MarkerError(f"Malformed clip marker on line {index + 1}: {line.strip()}")
            continue
        marker_lines.add(index)
        kind, clip_id = match.groups()
        if kind == "START":
            if open_clip:
                raise MarkerError(f"Nested clip '{clip_id}' on line {index + 1}; '{open_clip[0]}' is still open")
            if clip_id in seen:
                raise MarkerError(f"Duplicate clip id '{clip_id}' on line {index + 1}")
            open_clip = (clip_id, index, index + 1)
        else:
            if not open_clip:
                raise MarkerError(f"End marker for '{clip_id}' on line {index + 1} has no start")
            if clip_id != open_clip[0]:
                raise MarkerError(f"Mismatched end id '{clip_id}' on line {index + 1}; expected '{open_clip[0]}'")
            text = "".join(lines[open_clip[2] : index]).strip()
            if not text:
                raise MarkerError(f"Clip '{clip_id}' is empty (lines {open_clip[1] + 1}-{index + 1})")
            raw.append((clip_id, open_clip[1], index, open_clip[2], text))
            seen.add(clip_id)
            open_clip = None
    if open_clip:
        raise MarkerError(f"Start marker for '{open_clip[0]}' on line {open_clip[1] + 1} has no end")
    if not raw:
        raise MarkerError("No valid CLIP_START/CLIP_END marker pairs found")

    clean_lines = [line for i, line in enumerate(lines) if i not in marker_lines]
    full_text = "".join(clean_lines).strip()
    selections: list[Selection] = []
    for order, (clip_id, start, end, content_start, text) in enumerate(raw):
        before = "".join(line for i, line in enumerate(lines[max(0, start - 8) : start], max(0, start - 8)) if i not in marker_lines)
        after = "".join(line for i, line in enumerate(lines[end + 1 : end + 9], end + 1) if i not in marker_lines)
        selections.append(Selection(clip_id, text, _spoken(text), _spoken(before), _spoken(after), start + 1, end + 1, order))
    return selections, full_text

