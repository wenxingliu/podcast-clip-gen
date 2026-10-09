---
name: podcast-clip-video
description: Turn a user-selected podcast passage into a verified audio excerpt and branded vertical video using the podcast-clips project. Use when Codex must locate exact source boundaries, review/correct captions against the audio and transcript, cut the audio, and render the final audiogram.
---

# Podcast Clip & Video

Produce the clip end to end with the repository's existing `podcast-clips` CLI. Codex owns the editorial alignment and subtitle-review step; scripts own deterministic cutting and rendering.

## Required inputs

Identify these before rendering:

- Full episode audio.
- Episode transcript and the user's selected passage.
- Cover image: use the repository-root `cover_photo.png` unless the user explicitly
  names a different file. Do not substitute an example, fixture, preview, or
  `visual-test-cover.png` merely because it is stored beside the episode assets.
- Output directory and clip ID; infer stable, filename-safe values when omitted.
- Rendering config, normally `configs/stellaxamy.yaml`.

Ask only for an input that cannot be found or safely inferred. A missing
`cover_photo.png` blocks the final branded render unless the user explicitly
provides or selects another cover, but it does not block timestamp analysis.

## 1. Verify boundaries and edit the selected transcript

Locate the selection in the source transcript. Preserve it as one contiguous passage; do not join distant excerpts.

Determine source start/end times from the strongest available evidence, in this order:

1. Word/segment alignment from Whisper, WhisperX, or another local time-coded transcript.
2. Speaker timestamps bracketing the selected passage, with the next speaker turn as the natural endpoint.
3. A user-provided timestamp override.

Verify coarse timestamps against the audio rather than copying them blindly. Inspect a short region around each edge and use FFmpeg silence detection or waveform evidence to move boundaries to speech onset/offset. Retain the configured padding (normally 150 ms). Never claim word-level precision when only speaker timestamps or silence boundaries are available.

Review the selected text against both audio and context. Correct clear transcription errors, punctuation, speaker labels, names, pronouns, code-switching, and omitted function words. Preserve what was spoken—do not summarize or rewrite for style. Treat a semantic correction that cannot be verified from the audio as uncertain; report it and request review instead of inventing wording.

### Mandatory subtitle approval checkpoint

Before creating or updating the marked transcript, timing override, audio clip,
or video, show the user the complete corrected subtitle text, including speaker
labels, and summarize every substantive correction. Ask the user to verify and
approve it. Stop and wait for explicit approval; do not run `cut`, `render`, or
`all` in the same turn as the approval request. If the user requests changes,
revise the subtitles and ask for approval again. This checkpoint may be skipped
only when the user explicitly says to use supplied subtitle text verbatim and to
generate without review.

Create auditable canonical inputs near the episode assets:

- `<episode>.clip.marked.md` with one `CLIP_START`/`CLIP_END` pair per requested clip.
- `<episode>.clip.overrides.json` when manual boundaries are needed.

For a manual override, include `start_sec`, `end_sec`, provenance in `source`, and timed `segments` when speaker boundaries are known. Segment timestamps are episode-relative. Keep the corrected wording identical in the marked transcript and override segments.

## 2. Generate and verify the audio cut

From the repository root, prefer the installed project executable:

```bash
.venv/bin/podcast-clips cut \
  --audio <episode-audio> \
  --transcript <marked-transcript> \
  --overrides <override-json> \
  --episode-id <episode-id> \
  --out <output-directory>
```

When reliable alignment JSON exists, pass `--alignment` instead of relying solely on overrides. A `needs_review` or `failed` result is not a successful cut.

Inspect `manifest.json`, `match-report.json`, the generated timed transcript, and the audio with `ffprobe`. Confirm:

- source and padded boundaries;
- expected duration, sample rate, channels, and codec;
- corrected transcript assets exist;
- clip-relative timed segments start and end within the exported audio;
- manual or estimated timing is labeled honestly.

## 3. Render and visually verify the video

Resolve and verify the cover before invoking the renderer. Unless the user
explicitly selected another image, the command must use the repository-root
`cover_photo.png` exactly. Check the resolved path in `render-report.json` after
rendering; a different cover path is a failed render and must be corrected.

```bash
.venv/bin/podcast-clips render \
  --manifest <output-directory>/manifest.json \
  --cover cover_photo.png \
  --config configs/stellaxamy.yaml \
  --out <output-directory>/videos
```

Inspect `render-report.json` and probe the MP4. Extract representative frames near the beginning, middle, speaker transitions, and end. Visually verify:

- the supplied cover is recognizable, contained, blurred, and not full bleed;
- `cover_path` in the render report resolves to repository-root `cover_photo.png`
  unless the user explicitly selected another cover;
- the badge text is exactly `StellaxAmy·自定义`;
- captions stay inside the safe width, wrap naturally, and never overlap;
- when `template.subtitle_mode` is `roll_up`, the active phrase is bright and
  centered, nearby phrases are progressively dimmer, the window advances in
  transcript order, and the lowest row stays clear of the waveform;
- Chinese and English glyphs render correctly;
- waveform responds to audio and uses the configured gold color;
- progress advances from start to finish;
- audio, subtitles, waveform, progress, and duration share the configured playback speed.

If visual QA exposes a renderer bug, fix the reusable renderer/config and add a focused regression test before rerendering. Do not patch only the exported MP4.

## Handoff

Provide clickable paths to the final MP4, audio clip, manifest, match report, corrected marked transcript, override/alignment file, timed transcript, and render report. State the boundary source, playback speed, test result, and whether subtitle timing is word-aligned or estimated.
