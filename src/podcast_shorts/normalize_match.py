from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"(?m)^\s*[^\n：:]{1,30}[：:]\s*", "", text)
    return "".join(c for c in text if c.isalnum() or "\u3400" <= c <= "\u9fff")


@dataclass
class Match:
    start: int
    end: int
    score: float
    second_score: float
    exact: bool


def locate(target: str, corpus: str, before: str = "", after: str = "") -> Match | None:
    target = normalize(target)
    corpus = normalize(corpus)
    if not target or not corpus:
        return None
    exacts: list[int] = []
    pos = corpus.find(target)
    while pos >= 0:
        exacts.append(pos)
        pos = corpus.find(target, pos + 1)
    nb, na = normalize(before)[-40:], normalize(after)[:40]
    if exacts:
        ranked = []
        for p in exacts:
            left = corpus[max(0, p - len(nb)) : p]
            right = corpus[p + len(target) : p + len(target) + len(na)]
            ctx = ((difflib.SequenceMatcher(None, nb, left).ratio() if nb else 1.0) +
                   (difflib.SequenceMatcher(None, na, right).ratio() if na else 1.0)) / 2
            ranked.append((0.9 + 0.1 * ctx, p))
        ranked.sort(reverse=True)
        second = ranked[1][0] if len(ranked) > 1 else 0.0
        return Match(ranked[0][1], ranked[0][1] + len(target), ranked[0][0], second, True)

    length = len(target)
    step = max(1, length // 15)
    candidates: list[tuple[float, int, int]] = []
    for size in range(max(1, int(length * .72)), int(length * 1.28) + 1, step):
        scan_step = max(1, min(5, size // 20))
        for start in range(0, max(1, len(corpus) - size + 1), scan_step):
            score = difflib.SequenceMatcher(None, target, corpus[start : start + size]).ratio()
            if score >= .5:
                candidates.append((score, start, start + size))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    best = candidates[0]
    nonoverlap = [c for c in candidates[1:] if c[2] <= best[1] or c[1] >= best[2]]
    return Match(best[1], best[2], best[0], nonoverlap[0][0] if nonoverlap else 0.0, False)

