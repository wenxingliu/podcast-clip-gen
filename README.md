# podcast-clips

A local-first, file-driven implementation of the StellaxAmy podcast clipping and 9:16 audiogram pipeline. It strictly parses explicit transcript markers, aligns selections to time-coded local ASR output, exports padded audio clips and clip-relative captions, and renders deterministic branded MP4 videos.

## Prerequisites

- Python 3.10 or newer (3.11+ recommended)
- FFmpeg/ffprobe on `PATH`
- A Chinese-capable font (auto-detected on macOS; set `brand.font` elsewhere)
- Optional: `faster-whisper` and its model files when the CLI must create alignment itself

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
# For local ASR too:
pip install -e '.[asr,dev]'
```

No audio or transcript is uploaded. The first ASR run may download the selected model; pass an existing Whisper/WhisperX JSON with `--alignment` for a fully offline run with no model setup.

## Transcript format

Use standalone, non-nested marker lines. IDs must match `[A-Za-z0-9_-]+` and be unique.

```md
<!-- CLIP_START id=clip-001 -->
嘉宾：我觉得很多时候，你不需要很早就知道答案，而是先去尝试。
<!-- CLIP_END id=clip-001 -->
```

Speaker labels are preserved in exported text but omitted from matching. Punctuation, whitespace, case, and full-width forms are normalized only for matching.

## Commands

Generate or reuse a cached local transcription:

```bash
podcast-clips cut \
  --audio input/episode.mp3 \
  --transcript input/episode.marked.md \
  --episode-id episode-001 \
  --out output/episode-001
```

Use an existing Whisper or WhisperX JSON (segments with timestamps, optionally words):

```bash
podcast-clips cut --audio input/episode.mp3 \
  --transcript input/episode.marked.md \
  --alignment input/episode.whisper.json \
  --out output/episode-001 --dry-run
```

Low-confidence or competing matches become `needs_review` and are not exported. Resolve difficult cases with a JSON sidecar (see `examples/overrides.json`):

```bash
podcast-clips cut ... --overrides examples/overrides.json
```

Render every exported clip in a manifest:

```bash
podcast-clips render \
  --manifest output/episode-001/manifest.json \
  --cover cover_photo.png \
  --config configs/stellaxamy.yaml \
  --out output/episode-001/videos
```

Render Module 2 independently:

```bash
podcast-clips render --audio clip.mp3 --timed-transcript clip.timed.json \
  --clip-id clip-001 --cover cover_photo.png --out videos
```

Or run both modules:

```bash
podcast-clips all --audio input/episode.mp3 --transcript input/episode.marked.md \
  --cover cover_photo.png --config configs/stellaxamy.yaml \
  --out output/episode-001
```

`cut` exits nonzero if any clip fails or needs review, while still exporting safe matches. `render` likewise continues per clip and writes `render-report.json`. The integration boundary is `manifest.json` plus each `*.timed.json`; rendering never reloads the full episode or reruns alignment.

## Outputs

```text
output/episode-001/
  alignment-cache/
  clips/
  transcripts/
  manifest.json
  match-report.json
  videos/
    clip-001.mp4
    render-report.json
```

The renderer uses the real audio for a gold animated waveform and preserves source audio in AAC. It creates a contained, blurred/darkened cover over a deep teal canvas, a centered roll-up transcript with the active phrase highlighted, a progress indicator, and the exact `StellaxAmy·自定义` badge. Set `template.subtitle_mode` to `roll_up` or `single`; layout constants are configurable in YAML.

## Alignment and confidence notes

The matching algorithm operates monotonically on normalized ASR characters/words, uses surrounding editorial context to resolve exact repeated phrases, and searches fuzzy windows otherwise. The manifest records the chosen method, best and competing scores, ambiguity, and reasons for review. ASR is evidence, not ground truth: inspect `match-report.json`, especially for names, dialect, overlap, transcript edits, and mixed-language speech.

Word timestamps produce word/character-level timed JSON. Segment-only alignment is interpolated and therefore reported through its source alignment; video captions are grouped into short phrases. Manual override times refer to the source episode and take precedence.

## Tests

```bash
pytest
```

For commercial use, audit your FFmpeg build, ASR model, cover artwork, and font licenses. The renderer intentionally avoids a Remotion dependency while preserving the manifest/timed-text boundary, so a different rendering backend can be substituted later.
