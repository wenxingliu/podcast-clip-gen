from __future__ import annotations

import json
import logging
from pathlib import Path

from . import __version__
from .alignment import file_hash, load_alignment, token_corpus, transcribe
from .media import cut_audio, duration, require_ffmpeg
from .normalize_match import locate
from .transcript_markers import parse_transcript

LOG = logging.getLogger(__name__)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _overrides(path: str | None) -> dict:
    if not path:
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    raw = data.get("clips", data)
    if isinstance(raw, list):
        return {item["id"]: item for item in raw}
    return raw


def run_cut(*, audio: str, transcript: str, out: str, episode_id: str | None,
            alignment: str | None, overrides: str | None, padding_ms: int,
            threshold: float, ambiguity_margin: float, output_format: str,
            dry_run: bool, model: str, device: str) -> tuple[dict, int]:
    require_ffmpeg()
    source = Path(audio).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Audio not found: {source}")
    selections, _ = parse_transcript(transcript)
    manual = _overrides(overrides)
    root = Path(out).resolve()
    episode_id = episode_id or source.stem
    audio_sha = file_hash(source)
    cache = root / "alignment-cache" / f"{audio_sha[:16]}-{model}.json"
    all_overridden = all(selection.id in manual for selection in selections)
    if alignment:
        tokens = load_alignment(alignment)
        alignment_source = str(Path(alignment).resolve())
    elif all_overridden:
        tokens = []
        alignment_source = "manual_overrides"
    elif cache.exists():
        tokens = load_alignment(cache)
        alignment_source = str(cache)
    else:
        LOG.info("Transcribing locally with faster-whisper model=%s device=%s", model, device)
        tokens = transcribe(source, cache, model, device)
        alignment_source = str(cache)
    corpus, owners = token_corpus(tokens)
    if not corpus and not all_overridden:
        raise RuntimeError("Alignment normalized to empty text")
    source_duration = duration(source)
    pad = padding_ms / 1000.0
    entries: list[dict] = []
    report: list[dict] = []
    failures = 0
    last_end = -1.0
    for selection in selections:
        override = manual.get(selection.id)
        match = None if override else locate(selection.alignment_text, corpus, selection.before_context, selection.after_context)
        reasons: list[str] = []
        if override:
            raw_start = float(override["start_sec"])
            raw_end = float(override["end_sec"])
            score, second, exact = 1.0, 0.0, False
            match_state = "matched"
            method = "manual_override"
            token_start = token_end = None
        elif match:
            token_start = owners[min(match.start, len(owners) - 1)]
            token_end = owners[min(max(match.start, match.end - 1), len(owners) - 1)]
            raw_start, raw_end = tokens[token_start].start, tokens[token_end].end
            score, second, exact = match.score, match.second_score, match.exact
            if score < threshold:
                reasons.append(f"score {score:.3f} is below threshold {threshold:.3f}")
            if second and score - second < ambiguity_margin:
                reasons.append(f"competing match score {second:.3f} is within ambiguity margin {ambiguity_margin:.3f}")
            match_state = "needs_review" if reasons else "matched"
            method = "exact_text" if exact else "fuzzy_text"
        else:
            raw_start = raw_end = 0.0
            score = second = 0.0
            exact = False
            token_start = token_end = None
            reasons.append("no plausible normalized text match")
            match_state = "failed"
            method = "none"
        if raw_end <= raw_start or raw_start < 0 or raw_end > source_duration + .05:
            reasons.append("resolved timestamps are empty or outside the source audio")
            match_state = "failed"
        if raw_start < last_end and match_state == "matched":
            reasons.append("resolved region is out of source order or overlaps a prior selection")
            match_state = "needs_review"
        if match_state == "matched":
            last_end = raw_end
        clip_start = max(0.0, raw_start - pad)
        clip_end = min(source_duration, raw_end + pad)
        ext = "wav" if output_format == "wav" else "mp3"
        audio_rel = f"clips/{selection.id}.{ext}"
        transcript_rel = f"transcripts/{selection.id}.txt"
        timed_rel = f"transcripts/{selection.id}.timed.json"
        status = match_state
        timed_segments: list[dict] = []
        if match_state == "matched":
            if token_start is not None:
                for tok in tokens[token_start : token_end + 1]:
                    timed_segments.append({"text": tok.text.strip(), "start": round(tok.start - clip_start, 3), "end": round(tok.end - clip_start, 3)})
            elif override and override.get("segments"):
                for segment in override["segments"]:
                    seg_start = float(segment["start_sec"])
                    seg_end = float(segment["end_sec"])
                    if seg_start < raw_start or seg_end > raw_end + .001 or seg_end <= seg_start:
                        raise ValueError(f"Manual timed segment for '{selection.id}' is outside its clip boundary")
                    timed_segments.append({"text": str(segment["text"]).strip(), "start": round(seg_start - clip_start, 3), "end": round(seg_end - clip_start, 3)})
            else:
                timed_segments = [{"text": selection.alignment_text, "start": round(raw_start - clip_start, 3), "end": round(raw_end - clip_start, 3)}]
            if not dry_run:
                try:
                    cut_audio(source, root / audio_rel, clip_start, clip_end, output_format)
                    (root / transcript_rel).parent.mkdir(parents=True, exist_ok=True)
                    (root / transcript_rel).write_text(selection.text + "\n", encoding="utf-8")
                    timing_quality = ("aligned_tokens" if token_start is not None else
                                      "manual_segment_proportional_fallback" if override and override.get("segments") else
                                      "manual_boundary_proportional_fallback")
                    _write_json(root / timed_rel, {"clip_id": selection.id, "duration_sec": round(clip_end - clip_start, 3), "timing_quality": timing_quality, "segments": timed_segments})
                    status = "exported"
                except Exception as exc:
                    reasons.append(f"audio export failed: {exc}")
                    status = "failed"
        if status in {"failed", "needs_review"}:
            failures += 1
        diagnostics = {"status": match_state, "method": method, "score": round(score, 4), "second_best_score": round(second, 4), "ambiguous": bool(second and score - second < ambiguity_margin), "reasons": reasons}
        has_timing = bool(match or override)
        entry = {"id": selection.id, "status": status, "text": selection.text, "source_audio": str(source), "source_start_sec": round(raw_start, 3) if has_timing else None, "source_end_sec": round(raw_end, 3) if has_timing else None, "clip_start_sec": round(clip_start, 3) if has_timing else None, "clip_end_sec": round(clip_end, 3) if has_timing else None, "duration_sec": round(clip_end - clip_start, 3) if has_timing else None, "padding_ms": padding_ms, "audio_path": audio_rel if status == "exported" else None, "transcript_path": transcript_rel if status == "exported" else None, "timed_transcript_path": timed_rel if status == "exported" else None, "match_diagnostics": diagnostics}
        entries.append(entry)
        report.append({"id": selection.id, "lines": [selection.start_line, selection.end_line], "status": status, "source_start_sec": entry["source_start_sec"], "source_end_sec": entry["source_end_sec"], **diagnostics})
    manifest = {"schema_version": 1, "tool_version": __version__, "episode_id": episode_id, "source_audio": str(source), "source_sha256": audio_sha, "alignment_source": alignment_source, "dry_run": dry_run, "clips": entries}
    _write_json(root / "manifest.json", manifest)
    _write_json(root / "match-report.json", {"episode_id": episode_id, "clips": report})
    return manifest, 2 if failures else 0

