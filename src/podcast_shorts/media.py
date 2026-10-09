from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


def require_ffmpeg() -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("FFmpeg and ffprobe must be installed and available on PATH")


def duration(path: str | Path) -> float:
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)], check=True, capture_output=True, text=True)
    return float(json.loads(result.stdout)["format"]["duration"])


def cut_audio(source: Path, target: Path, start: float, end: float, fmt: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    codec = ["-c:a", "pcm_s16le"] if fmt == "wav" else ["-c:a", "libmp3lame", "-b:a", "192k"]
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{start:.6f}", "-i", str(source), "-t", f"{end-start:.6f}", "-ar", "48000", *codec, str(target)], check=True)

