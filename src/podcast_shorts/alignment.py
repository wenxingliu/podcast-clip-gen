from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .normalize_match import normalize


@dataclass
class Token:
    text: str
    start: float
    end: float


def file_hash(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_alignment(path: str | Path) -> list[Token]:
    data: Any = json.loads(Path(path).read_text(encoding="utf-8"))
    segments = data.get("segments", data) if isinstance(data, dict) else data
    tokens: list[Token] = []
    for segment in segments:
        words = segment.get("words") or []
        if words:
            for word in words:
                if word.get("start") is not None and word.get("end") is not None:
                    tokens.append(Token(str(word.get("word", word.get("text", ""))), float(word["start"]), float(word["end"])))
        elif segment.get("start") is not None and segment.get("end") is not None and segment.get("text"):
            text = normalize(str(segment["text"]))
            if text:
                duration = float(segment["end"]) - float(segment["start"])
                for i, char in enumerate(text):
                    tokens.append(Token(char, float(segment["start"]) + duration * i / len(text), float(segment["start"]) + duration * (i + 1) / len(text)))
    if not tokens:
        raise ValueError(f"Alignment has no timed words or segments: {path}")
    return tokens


def transcribe(audio: Path, cache_path: Path, model: str, device: str) -> list[Token]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("No alignment supplied and faster-whisper is not installed. Install with 'pip install .[asr]' or pass --alignment JSON.") from exc
    compute = "int8" if device == "cpu" else "float16"
    whisper = WhisperModel(model, device=device, compute_type=compute)
    segments, info = whisper.transcribe(str(audio), language=None, word_timestamps=True, vad_filter=True)
    payload = {"engine": "faster-whisper", "model": model, "language": info.language, "segments": []}
    for seg in segments:
        payload["segments"].append({"start": seg.start, "end": seg.end, "text": seg.text, "words": [
            {"word": w.word, "start": w.start, "end": w.end, "probability": w.probability} for w in (seg.words or [])
        ]})
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return load_alignment(cache_path)


def token_corpus(tokens: list[Token]) -> tuple[str, list[int]]:
    chars: list[str] = []
    owners: list[int] = []
    for index, token in enumerate(tokens):
        for char in normalize(token.text):
            chars.append(char)
            owners.append(index)
    return "".join(chars), owners

