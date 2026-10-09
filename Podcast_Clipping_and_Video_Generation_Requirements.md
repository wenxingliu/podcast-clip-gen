# StellaxAmy·自定义 — Podcast Clipping & Video Generation

**Product Requirements & Technical Specification (PRD)**  
**Version:** 1.0 (MVP)  
**Date:** 2026-10-08  
**Status:** Ready for implementation planning  
**Primary language:** Mandarin Chinese (allow English/code-switching)

## 1. Summary

Build a **local-first, non-interactive, file-driven pipeline** with two independent modules:

1. **Transcript-Guided Audio Clipping:** Given one full-length podcast audio recording and its annotated transcript, locate the passages marked by the editor, align them with the audio timeline, and export individual audio clips with transcript and metadata.
2. **Branded Audiogram Video Generation:** Given each audio clip and associated time-aligned text, render a consistent 9:16 short video in the agreed **StellaxAmy·自定义** visual style: a dark teal canvas, softly blurred podcast cover with margins (not edge-to-edge), centered animated Chinese subtitles, gold animated waveform, progress indicator, and brand badge.

**Editorial workflow:** The host chooses excerpts in the transcript; software performs alignment, clipping, and rendering. No GUI, visual editor, or AI clip selection is required for MVP.

### Goals

- Convert explicit transcript selections into reliably synchronized audio clips.
- Create repeatable, branded, publishable social-video assets from the clips.
- Support multiple excerpts from one episode in one command.
- Make Module 1 and Module 2 runnable, testable, and replaceable independently.
- Work on macOS locally; provide CLI and machine-readable outputs.

### Out of scope (MVP)

- Interactive transcript editor / timeline editor.
- AI recommendation of clips or creative rearrangement of non-contiguous passages.
- Generative AI B-roll, illustrations, avatars, or stock-footage search.
- Direct publication to Xiaohongshu, Douyin, WeChat Channels, or YouTube.
- Translation, voice cloning, automatic summarization or rewriting of the spoken audio.
- Automatic removal of fillers or pauses inside a marked passage.

## 2. Users and workflow

**Primary user:** Podcast creator editing Mandarin interview recordings, potentially with some English words and multiple speakers.

**Happy path**

1. Export/prepare `episode.mp3` (or `.wav`, `.m4a`) and an accurate transcript.
2. Insert clip-start / clip-end markers around one or more desired passages.
3. Run `podcast-clips cut --audio ... --transcript ... --out ...`.
4. Inspect the resulting audio clips and a match report; correct markers/transcript if any boundaries are ambiguous.
5. Run `podcast-clips render --manifest ... --cover ... --out ...`.
6. Receive one `.mp4` per successful audio clip, along with timestamps, subtitle timing, and logs.

Module 2 must also accept an independently supplied audio clip + its transcript/timed-subtitle file.

## 3. Input and annotation format

### 3.1 Canonical MVP format: Markdown or plain text with explicit markers

Use robust standalone marker lines. Multiple selected passages become multiple **separate output clips**. Each selected passage is contiguous in the source recording.

```md
主持人：今天我们聊一聊兴趣和成长。

<!-- CLIP_START id=clip-001 -->
嘉宾：我觉得很多时候，你不需要很早就知道答案，而是先去尝试。
主持人：是的，我觉得这个特别重要。
<!-- CLIP_END id=clip-001 -->

主持人：接下来再聊聊别的话题。

<!-- CLIP_START id=clip-002 -->
嘉宾：我小时候很喜欢观察昆虫，尤其是它们不同的习性。
<!-- CLIP_END id=clip-002 -->
```

**Rules**

- `id` is mandatory, unique within the transcript, and safe for use as a filename (`[A-Za-z0-9_-]+`).
- Exactly one start and one end per ID; no nesting or overlaps in MVP.
- The exact text *between* markers is the selected content. Keep speaker labels for human readability but strip them from alignment text if they are not spoken.
- Preserve punctuation and wording in exported transcript; normalize punctuation, whitespace, full/half-width characters, and common Chinese transcription variants **only for matching**.
- Never silently reorder content or join distant passages.
- Transcript may omit exact timestamps; software must derive them.

**Decision:** Markdown/TXT is the guaranteed MVP input. DOCX highlighting, Word comments, and other rich-text annotation are **Phase 2** conveniences. A future DOCX parser should convert highlights to the same canonical clip format rather than implementing a separate cutting engine.

### 3.2 Audio

Accept MP3/WAV/M4A via FFmpeg decoding. Preserve original source file; use a consistent decoded PCM analysis copy for alignment. Prefer final 48 kHz audio export; allow MP3 192 kbps and WAV PCM output via options. Source sample rate/channels may vary.

### 3.3 Visual assets

- Original uploaded podcast cover image (user-provided asset; required for default template).
- Badge text must be **`StellaxAmy·自定义`** (exact spelling and punctuation).
- A font capable of Simplified Chinese, with configurable fallback.

## 4. Module 1 — Transcript-Guided Audio Clipping

### 4.1 Functional requirements

| ID | Priority | Requirement |
|---|---|---|
| AC-01 | Must | Parse annotated transcript and validate markers and clip IDs. |
| AC-02 | Must | Align the full transcript to the recording and recover source start/end times for each marked passage. |
| AC-03 | Must | Match Chinese text with mixed English and multiple speakers as far as supported by selected models. |
| AC-04 | Must | Output a separate clip for every marked passage in source order, without changing spoken content. |
| AC-05 | Must | Cut at utterance/word boundaries with configurable padding (default 150 ms at each end, clipped to file bounds). |
| AC-06 | Must | Emit a match confidence/diagnostics report; low-confidence matches must be flagged and never silently substituted. |
| AC-07 | Must | Produce clip-specific text and time-aligned segments for rendering. |
| AC-08 | Must | Support `--dry-run` to inspect all selected regions and timestamp matches without exporting audio. |
| AC-09 | Must | Allow independent run of audio-cutting module and reruns without requiring video rendering. |
| AC-10 | Should | Cache episode transcription/alignment for subsequent runs with revised selections. |
| AC-11 | Should | Provide optional manual timestamp overrides in a sidecar JSON for difficult matches. |

### 4.2 Alignment and boundary strategy

**Do not assume that the text selection directly maps to exact timestamps.** Implement a multistage pipeline:

1. Parse selected spans and the transcript context immediately before and after each span.
2. Obtain a time-coded ASR transcription of the original recording (WhisperX/faster-whisper candidate) and/or align supplied transcript against decoded audio using a Chinese-capable alignment model.
3. Apply punctuation-insensitive text normalization, then monotonic/fuzzy matching between the editor's transcript and the audio-derived word/character tokens; use nearby context to disambiguate repeated phrases.
4. Map each selection's beginning and end onto supported time-aligned tokens; derive cutpoints, considering natural silence or speech boundaries near the edge.
5. Validate nonnegative durations, ordering, and overlap; report ambiguity and confidence signals.
6. Extract exact source segment (prefer accurate re-encoding over approximate MP3 stream copy), retaining original language and speaker order.

**Important:** Alignment model output is not authoritative, especially with informal Mandarin, names, dialects, overlapping speech, transcript edits, or English code-switching. Alignment must support an explicit unresolved/needs-review status. Do not imply guaranteed word-perfect timestamps.

### 4.3 Error handling

- Invalid/unbalanced/duplicate markers → stop with actionable validation error.
- Text that does not appear in source audio, multiple equally plausible matches, or scores below threshold → mark clip `needs_review`; exclude from export by default, unless timestamp override is supplied.
- Missing model or model download / CPU-memory limitations → clear diagnostic; configurable CPU fallback if available.
- Audio errors / empty or out-of-range clips → fail per clip and continue with valid clips where safe; overall command returns a nonzero exit code if any clips fail.
- Distinguish `matched`, `needs_review`, `failed`, and `exported` in the manifest.

### 4.4 Deliverables

```text
output/episode-id/
  alignment-cache/             # internal, regenerable
  clips/
    clip-001.mp3
    clip-002.mp3
  transcripts/
    clip-001.txt
    clip-001.timed.json
  manifest.json
  match-report.json
  run.log
```

Manifest entries should contain clip ID, text, source file, source timestamps, final duration, padding, match status, relevant confidence diagnostics, transcript asset paths, and audio asset path.

Example **illustrative schema, not real timestamps**:

```json
{
  "episode_id": "episode-001",
  "source_audio": "episode.mp3",
  "clips": [
    {
      "id": "clip-001",
      "status": "exported",
      "source_start_sec": 1122.15,
      "source_end_sec": 1147.30,
      "audio_path": "clips/clip-001.mp3",
      "transcript_path": "transcripts/clip-001.txt",
      "timed_transcript_path": "transcripts/clip-001.timed.json",
      "match_diagnostics": {"status": "matched"}
    }
  ]
}
```

`timed.json` timestamps must be **clip-relative**, not episode-relative. Preserve full transcript timing in alignment cache for debugging.

## 5. Module 2 — Branded Audiogram Video Generation

### 5.1 Visual specification (agreed reference)

**Output:** portrait 1080 × 1920, 9:16, MP4 H.264 + AAC, configurable FPS (default 30). Design should remain readable in platform UI safe areas.

| Element | Required V1 behavior |
|---|---|
| Canvas | Solid deep teal / dark green base (#123B37 as an initial approximation; sample precise colors from original artwork during implementation). |
| Background artwork | Reuse **original cover image**, scale down within canvas with visible dark-green margins instead of full-bleed. Apply **strong Gaussian blur**, lower opacity / darken and optionally feather edges. It is a brand texture, not the foreground focal point. |
| Badge | At top, small gold outline rounded capsule, exact text `StellaxAmy·自定义` in gold. |
| Dynamic subtitles | Primary focal point at the **middle of the image**, white, bold, centered Chinese type; typical 1–3 lines in a controlled safe text box. Display successive phrases synchronized to actual speech. |
| Audio bars | Warm-gold stylized vertical waveform directly **below central subtitles**, moving with audio amplitude. Visual design may smooth and compress levels but should respond to the actual sound. |
| Progress | Thin horizontal track beneath waveform, gold played section, muted remaining section, small gold position dot, synchronized to clip duration. |
| Color | Preserve dark teal + warm gold + white visual identity of the podcast cover. |
| Animation | Restrained transitions (subtle fades/phrase changes); no distracting zooms or AI-generated scenes for V1. |

**Layout principle:** The subtitle + waveform + progress components form a visually centered cluster. Cover artwork is reduced and blurred within generous teal margins; its exact placement must not compete with subtitle legibility. Expose positions as normalized percentages to permit iteration without code rewrites.

**Source of truth:** The **final visual mockup approved in the conversation** and the user-provided original cover. The generated mockup is a design reference, **not** a composited asset to use as a video background; implementation must reconstruct components from the original cover, clean fonts, and actual audio.

### 5.2 Subtitle rules

- Render at phrase/short-sentence level, timed to spoken content rather than as one giant persistent quote.
- Target 1–3 lines, with readable Chinese line wrapping; avoid cutting words/names unnaturally.
- White foreground, appropriate shadow or subtle dark backing for contrast, configurable font size and line spacing.
- Handle English and punctuation naturally; preserve the transcript rather than paraphrasing it.
- Handle absence of reliable word timing with sentence-level timing and report the fallback.
- MVP: phrase change/fade only. Word-by-word highlighting and kinetic typography are Phase 2.
- Empty/pause intervals should not show stale text indefinitely; allow short persistence rules configurable in the template.

### 5.3 Waveform and progress

- Read actual clip audio levels (RMS/peak envelope). Normalize/smooth over short windows to create balanced, rounded gold bars; avoid raw erratic spikes.
- Animation synchronized to actual frames or time-based audio sampling.
- During silence, bars reduce toward a small baseline.
- Progress = elapsed clip time / clip duration, clamped to [0, 1].
- Rendering must be deterministic given identical inputs/configuration.

### 5.4 Configuration example

```yaml
brand:
  title: "StellaxAmy·自定义"
  cover: "assets/podcast-cover.png"
  background_color: "#123B37"
  accent_color: "#E2AD3E"  # approximate; verify from cover
  subtitle_color: "#FFFFFF"
video:
  width: 1080
  height: 1920
  fps: 30
  codec: "h264"
template:
  name: "blurred-cover-audiogram-v1"
  cover_mode: "contained-blurred"
  cover_scale: 0.82
  cover_blur_px: 32
  cover_opacity: 0.32
  subtitle_anchor_y: 0.49
  waveform_anchor_y: 0.64
  progress_anchor_y: 0.70
  subtitles_max_lines: 3
  subtitles_mode: "phrases"
  waveform_mode: "audio-reactive-stylized"
```

All sizes/anchors are **initial tuning defaults**, subject to visual regression against the approved reference and safe-area checks.

### 5.5 Module 2 deliverables

```text
output/episode-id/
  videos/
    clip-001.mp4
    clip-002.mp4
  render-report.json
```

Render report includes input clip and alignment paths, export codec, dimensions, FPS, duration, render status, final video path, and warning list.

## 6. Architecture and stack

```text
[episode audio] + [annotated transcript]
              |
       Marker Parser & Validator (Python)
              |
       Transcription/Alignment (WhisperX or equivalent)
              |
       Match & Boundary Resolution (Python)
              |
       FFmpeg Audio Cutter
              |
       [clips + manifest + timed transcript]
              |
       Template Rendering (Remotion + React)
              |
       FFmpeg / video encoding
              |
       [9:16 MP4 clips]
```

**Recommended components**

- **Python 3.11+** for CLI, parsing, orchestration, file validation, fuzzy matching and manifests.
- **WhisperX** for speech transcription/alignment, evaluating Mandarin accuracy empirically; **faster-whisper** may support the ASR step. Validate Chinese mixed-language alignment on sample episodes before finalizing model choice.
- **FFmpeg/ffprobe** for audio decoding, cutting, normalizing output formats, video encoding/inspection.
- **Remotion + React/TypeScript** for reproducible dynamic subtitle, cover composition, waveform bars, and progress animation.
- **Pillow/OpenCV (optional)** for preprocessing blurred/contained cover background once per brand/template.

**Licensing caution:** Remotion source is available, but its license is conditional. Confirm current license terms for organization size and any productized automation use before commercial deployment; provide a rendering-engine abstraction so a fully permissive alternative (FFmpeg + ASS/Python compositor) remains viable if necessary. Also audit FFmpeg build licensing and model/font licenses.

### Integration boundary

Make `manifest.json` + `timed.json` the documented data contract. Rendering must not load the full episode or recompute alignments. Audio cutting must not depend on Node/Remotion. Clip IDs stay stable between modules.

### Suggested repo structure

```text
podcast-shorts/
  README.md
  pyproject.toml
  src/podcast_shorts/
    cli.py
    transcript_markers.py
    normalize_match.py
    align.py
    cut.py
    manifest.py
  renderer/
    package.json
    src/
      PodcastClip.tsx
      components/BrandBadge.tsx
      components/BlurredCover.tsx
      components/AnimatedSubtitles.tsx
      components/AudioWaveform.tsx
      components/ProgressBar.tsx
  assets/
    podcast-cover.png
  configs/
    stellaxamy.yaml
  tests/
    fixtures/
    test_markers.py
    test_matching.py
    test_manifest.py
  docs/
    requirements.md
```

### Example commands (target CLI interface; not implemented yet)

```bash
podcast-clips cut \
  --audio input/episode.mp3 \
  --transcript input/episode.marked.md \
  --episode-id episode-001 \
  --out output/episode-001

podcast-clips render \
  --manifest output/episode-001/manifest.json \
  --config configs/stellaxamy.yaml \
  --out output/episode-001/videos

podcast-clips all \
  --audio input/episode.mp3 \
  --transcript input/episode.marked.md \
  --config configs/stellaxamy.yaml \
  --out output/episode-001
```

## 7. Nonfunctional requirements

- **Local-first:** default no uploads of private audio/transcripts to third-party APIs. Model download during setup is allowed with disclosure.
- **Reproducible:** pinned dependency versions, deterministic visual rendering, cached alignment keyed by source hash/version.
- **Robust:** clear errors; failure of one clip need not invalidate all valid outputs; resumable batch rendering.
- **Traceable:** manifests store file hashes, processing versions, match decisions and explicit manual overrides.
- **Usable without a GPU:** document CPU-capable path (slower) and an optional GPU-accelerated setup.
- **Privacy:** no telemetry without opt-in; logs should not unnecessarily reproduce full private transcript.
- **Portability:** target macOS first; Linux support desirable.
- **Quality:** avoid clipping speech onset/end; no silent missing words, unintended speed changes, or desynchronization.

## 8. Acceptance criteria

### Audio clipping

1. Given a transcript with three valid, distinct marker pairs and a matching source recording, the command creates three distinct audio files and associated metadata.
2. A selected passage beginning/ending mid-episode is matched using speech and surrounding context, not guessed from paragraph position.
3. Repeated phrases or unclear matches are flagged `needs_review`; the tool must not quietly export a different occurrence.
4. Output starts before first spoken phoneme and ends after last spoken phoneme within a tunable padding budget. Evaluate a representative multilingual test set against manually checked ground-truth boundaries; **target median boundary error ≤ 300 ms, and require review for larger or ambiguous discrepancies**. This is a target, not a guarantee of a chosen alignment model.
5. Run `cut` repeatedly with the same input and cached alignment without recomputing ASR unnecessarily.
6. Bad markers lead to informative error messages naming ID and location.
7. Clip-relative timed transcript aligns with the exported file including any padding.

### Video generation

1. One accepted audio clip yields one 1080×1920 playable MP4 with original speech and branded visual composition.
2. Badge spells **`StellaxAmy·自定义`** correctly.
3. Cover remains softly blurred and **contained with visible margins**; subtitle cluster sits near visual center; waveform/progress directly beneath it.
4. Dynamic subtitle timing follows speech; no obvious >300 ms drift in manually checked example clips (timing quality depends on alignment input).
5. Bars respond to actual audio, falling back to baseline in silence; progress completes at video end.
6. Font renders Chinese and mixed English correctly, without clipped lines.
7. Using the same input/parameters produces materially the same visual output.
8. Module 2 renders from a pre-existing clip and timed transcript without Module 1.

### Demo/test corpus

At minimum test (a) solo Mandarin speech, (b) two-person dialogue, (c) Chinese + English phrases, (d) repeated sentence, (e) inaccurate editorial transcript, (f) 60–90 second clip, and (g) clip with extended pause.

## 9. Iteration roadmap

### MVP / V1: Build this now

- Markdown/TXT explicit transcript markers.
- One contiguous selection = one audio clip; batch several clips.
- Audio matching, ambiguity reporting, accurate trim, manifests, timed text.
- One fixed `blurred-cover-audiogram-v1` 9:16 video template.
- Centered phrase-level subtitles, audio-reactive gold waveform, gold progress, top badge.
- CLI; local batch outputs; basic tests.

### V1.1: Workflow convenience

- DOCX highlighted passages → convert to canonical selections.
- Adjustable text/waveform positions via config and preview still-frame generation.
- More robust local timing override file; optional concise audio QC reports.
- Optional run Module 1 only or video rendering only on chosen IDs.

### V2: Visual enhancements

- Word-level highlight karaoke captions; multiple template presets (Minimal/Balanced/Rich).
- Title cards, outro CTAs, per-platform text safe-area presets.
- Still illustrations/images as timed B-roll using structured shot lists.
- Alternate audio waveform styles and simple animated typography.

### V3: AI-assisted discovery and rich visuals

- AI recommends candidate excerpts; editor approves selections.
- Optional AI generated visual inserts and automated storyboarding.
- Evaluation loop using viewer retention and engagement signals, when available.
- Optional publication integrations.

## 10. Implementation order for Codex

1. Scaffold repository, CLI, schemas, config, sample marked transcript, tests.
2. Build marker parser, strict validation, clip metadata serialization.
3. Integrate audio decoding + alignment, match disambiguation, diagnostics; unit and fixture tests.
4. Integrate cut/export with FFmpeg, clip-relative timed subtitles, `--dry-run` and caching.
5. Build Remotion reference template using real original cover and configurable visual constants.
6. Add audio-reactive waveform, subtitle phrase timing and progress; write render reports.
7. Connect both modules via the manifest; add end-to-end CLI and repeatable sample fixture.
8. Review exported MP4 visually against approved reference; tune colors/margins/blur/positions using config only.
9. Document local setup (FFmpeg, Python, Node, model setup), CPU vs GPU execution, and model/license limitations.

## 11. Open decisions (not blocking implementation)

- **Rich-text input:** MVP is Markdown/TXT. Whether highlighted DOCX should be supported next depends on the author's preferred annotation workflow.
- **Source format:** For stereo/multi-track episodes, V1 assumes a final mixed recording; multi-track synchronization is a possible future extension.
- **Time alignment accuracy:** Select and benchmark Chinese/English speech models on a small real sample before imposing confidence thresholds.
- **Visual calibration:** Final colors, blur strength, cover frame placement and title font should be tuned against the actual brand cover and approved mockup, not the approximated palette alone.

## 12. Useful official references

- WhisperX: https://github.com/m-bain/whisperX
- FFmpeg: https://ffmpeg.org/
- Remotion documentation: https://www.remotion.dev/docs/
- Remotion licensing: https://www.remotion.dev/docs/license/pricing

---

**Definition of done for MVP:** A single marked transcript + full episode audio creates correct independent audio clips; a second fully automated command creates the approved branded short-video style for each, without hand-editing a timeline.
