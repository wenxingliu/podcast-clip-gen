from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from .media import duration, require_ffmpeg


DEFAULTS = {
    "brand": {"title": "StellaxAmy·自定义", "background_color": "#123B37", "accent_color": "#E2AD3E", "subtitle_color": "#FFF6DE", "subtitle_outline_color": "#092724"},
    "video": {"width": 1080, "height": 1920, "fps": 30, "codec": "h264", "playback_speed": 1.0},
    "template": {"cover_scale": .82, "cover_blur_px": 20, "cover_opacity": .52, "cover_brightness": .78, "subtitle_mode": "single", "subtitle_anchor_y": .49, "waveform_anchor_y": .64, "progress_anchor_y": .70, "subtitles_max_lines": 3, "subtitle_chars_per_line": 12, "subtitle_max_chars_per_phrase": 24, "font_size": 68, "fade_ms": 120, "rollup_context": 2, "rollup_inactive_alpha": 150, "rollup_far_alpha": 205, "rollup_inactive_scale": .78},
}


def _merge(base: dict, extra: dict) -> dict:
    result = {**base}
    for key, value in extra.items():
        result[key] = _merge(result.get(key, {}), value) if isinstance(value, dict) else value
    return result


def _font(config: dict, size: int, role: str = "default") -> ImageFont.FreeTypeFont:
    brand = config.get("brand", {})
    requested = brand.get(f"{role}_font") or brand.get("font")
    subtitle_bold = "/System/Library/Fonts/STHeiti Medium.ttc" if role == "subtitle" else None
    choices = [requested, subtitle_bold, "/System/Library/Fonts/Hiragino Sans GB.ttc", "/System/Library/Fonts/STHeiti Medium.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]
    for path in choices:
        if path and Path(path).exists():
            return ImageFont.truetype(path, size=size)
    raise RuntimeError("No Chinese-capable font found; set brand.font in the YAML config")


def _background(cover_path: Path, target: Path, cfg: dict) -> None:
    width, height = int(cfg["video"]["width"]), int(cfg["video"]["height"])
    bg = Image.new("RGB", (width, height), cfg["brand"]["background_color"])
    cover = Image.open(cover_path).convert("RGB")
    box_w = int(width * float(cfg["template"]["cover_scale"]))
    box_h = int(height * .68)
    cover.thumbnail((box_w, box_h), Image.Resampling.LANCZOS)
    cover = cover.filter(ImageFilter.GaussianBlur(float(cfg["template"]["cover_blur_px"])))
    cover = ImageEnhance.Brightness(cover).enhance(float(cfg["template"].get("cover_brightness", .78)))
    layer = Image.new("RGBA", bg.size)
    x, y = (width - cover.width) // 2, (height - cover.height) // 2
    cover_rgba = cover.convert("RGBA")
    cover_rgba.putalpha(Image.new("L", cover.size, int(255 * float(cfg["template"]["cover_opacity"]))))
    # alpha_composite applies the configured opacity once. Using the RGBA image
    # as both paste source and mask squares the alpha and makes the cover vanish.
    layer.alpha_composite(cover_rgba, (x, y))
    bg = Image.alpha_composite(bg.convert("RGBA"), layer)
    draw = ImageDraw.Draw(bg)
    title = cfg["brand"]["title"]
    font = _font(cfg, max(28, int(width * .038)))
    bounds = draw.textbbox((0, 0), title, font=font)
    tw, th = bounds[2] - bounds[0], bounds[3] - bounds[1]
    pad_x, pad_y = 28, 13
    rect = ((width - tw) // 2 - pad_x, int(height * .085), (width + tw) // 2 + pad_x, int(height * .085) + th + pad_y * 2)
    draw.rounded_rectangle(rect, radius=(th + pad_y * 2) // 2, outline=cfg["brand"]["accent_color"], width=3)
    draw.text((width // 2, rect[1] + pad_y), title, fill=cfg["brand"]["accent_color"], font=font, anchor="ma")
    bg.convert("RGB").save(target)


def _ass_time(value: float) -> str:
    value = max(0, value)
    hours = int(value // 3600); value %= 3600
    minutes = int(value // 60); seconds = value % 60
    return f"{hours}:{minutes:02d}:{seconds:05.2f}"


def _escape_ass(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def _split_display_chunks(text: str, max_chars: int) -> list[str]:
    """Hard-wrap CJK while avoiding line breaks inside Latin words."""
    chunks: list[str] = []
    remaining = text.strip()
    while len(remaining) > max_chars:
        cut = max_chars
        if remaining[cut - 1].isascii() and remaining[cut - 1].isalnum() and remaining[cut].isascii() and remaining[cut].isalnum():
            word_start = cut
            while word_start > 0 and remaining[word_start - 1].isascii() and remaining[word_start - 1].isalnum():
                word_start -= 1
            if word_start > 0:
                cut = word_start
            else:
                while cut < len(remaining) and remaining[cut].isascii() and remaining[cut].isalnum():
                    cut += 1
        chunk = remaining[:cut].rstrip()
        if not chunk:
            cut = max_chars
            chunk = remaining[:cut]
        chunks.append(chunk)
        remaining = remaining[cut:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


def _phrases(timed: dict, max_chars: int = 24) -> list[dict]:
    source = timed.get("segments", [])
    expanded: list[dict] = []
    # Segment-only/manual timings may cover a long paragraph. Split on natural
    # punctuation, then hard-wrap if needed, distributing time by character count.
    for item in source:
        raw = str(item.get("text", "")).strip()
        if not raw:
            continue
        pieces = [part.strip() for part in re.findall(r"[^。！？!?；;，,\n]+[。！？!?；;，,]?", raw) if part.strip()]
        chunks: list[str] = []
        for piece in pieces or [raw]:
            chunks.extend(_split_display_chunks(piece, max_chars))
        total = max(1, sum(len(chunk) for chunk in chunks))
        cursor = float(item["start"])
        span = max(0.01, float(item["end"]) - cursor)
        for chunk in chunks:
            end = cursor + span * len(chunk) / total
            expanded.append({"text": chunk, "start": cursor, "end": end})
            cursor = end
    result, current = [], []
    for item in expanded:
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        prior = "".join(str(x.get("text", "")).strip() for x in current)
        if current and len(prior) + len(text) > max_chars:
            result.append({"text": prior, "start": float(current[0]["start"]), "end": float(current[-1]["end"])})
            current = []
        current.append(item)
        joined = "".join(str(x.get("text", "")).strip() for x in current)
        terminal = any(joined.endswith(p) for p in "。！？!?；;")
        if len(joined) >= max_chars or terminal:
            result.append({"text": joined, "start": float(current[0]["start"]), "end": float(current[-1]["end"])})
            current = []
    if current:
        result.append({"text": "".join(str(x.get("text", "")).strip() for x in current), "start": float(current[0]["start"]), "end": float(current[-1]["end"])})
    return result


def _wrapped_phrase(text: str, chars_per_line: int, max_lines: int) -> str:
    lines = _split_display_chunks(text, chars_per_line)[:max_lines]
    return _escape_ass("\n".join(lines))


def _rollup_text(phrases: list[dict], active: int, cfg: dict) -> str:
    """Build a centered transcript window with the active phrase emphasized."""
    context = max(1, int(cfg.get("rollup_context", 2)))
    chars_per_line = int(cfg.get("subtitle_chars_per_line", 12))
    # Roll-up rows stay compact so five phrase groups fit without covering the waveform.
    max_lines = min(2, int(cfg.get("subtitles_max_lines", 3)))
    active_size = int(cfg["font_size"])
    inactive_size = max(24, int(active_size * float(cfg.get("rollup_inactive_scale", .78))))
    near_alpha = max(0, min(255, int(cfg.get("rollup_inactive_alpha", 150))))
    far_alpha = max(near_alpha, min(255, int(cfg.get("rollup_far_alpha", 205))))
    rows: list[str] = []
    for index in range(max(0, active - context), min(len(phrases), active + context + 1)):
        distance = abs(index - active)
        text = _wrapped_phrase(str(phrases[index]["text"]), chars_per_line, max_lines)
        if distance == 0:
            rows.append(f"{{\\alpha&H00&\\fs{active_size}}}{text}")
        else:
            alpha = near_alpha if distance == 1 else far_alpha
            rows.append(f"{{\\alpha&H{alpha:02X}&\\fs{inactive_size}}}{text}")
    separator = r"\N\N" if bool(cfg.get("rollup_blank_line_between_phrases", False)) else r"\N"
    return separator.join(rows)


def _write_ass(path: Path, timed: dict, cfg: dict, playback_speed: float = 1.0) -> None:
    v, t = cfg["video"], cfg["template"]
    accent = cfg["brand"]["subtitle_color"].lstrip("#")
    bgr = f"{accent[4:6]}{accent[2:4]}{accent[0:2]}"
    outline = cfg["brand"].get("subtitle_outline_color", "#092724").lstrip("#")
    outline_bgr = f"{outline[4:6]}{outline[2:4]}{outline[0:2]}"
    font_name = _font(cfg, int(t["font_size"]), "subtitle").getname()[0]
    y = int(float(t["subtitle_anchor_y"]) * int(v["height"]))
    header = f"""[Script Info]\nScriptType: v4.00+\nPlayResX: {v['width']}\nPlayResY: {v['height']}\nWrapStyle: 0\n[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\nStyle: Default,{font_name},{t['font_size']},&H00{bgr},&H00{bgr},&H00{outline_bgr},&H70000000,-1,0,0,0,100,100,0,0,1,2.6,1.4,5,90,90,0,1\n[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"""
    events = []
    chars_per_line = int(t.get("subtitle_chars_per_line", 12))
    max_lines = int(t.get("subtitles_max_lines", 3))
    max_phrase = min(int(t.get("subtitle_max_chars_per_phrase", chars_per_line * max_lines)), chars_per_line * max_lines)
    phrases = _phrases(timed, max_chars=max_phrase)
    mode = str(t.get("subtitle_mode", "single"))
    if mode not in {"single", "roll_up"}:
        raise ValueError("template.subtitle_mode must be 'single' or 'roll_up'")
    for index, phrase in enumerate(phrases):
        if mode == "roll_up":
            text = _rollup_text(phrases, index, t)
        else:
            text = _wrapped_phrase(str(phrase["text"]), chars_per_line, max_lines)
        # Never extend a cue into the following cue: libass draws both events,
        # creating doubled/garbled captions at phrase boundaries.
        end = float(phrase["end"])
        if index + 1 < len(phrases):
            end = min(end, float(phrases[index + 1]["start"]))
        events.append(f"Dialogue: 0,{_ass_time(float(phrase['start']) / playback_speed)},{_ass_time(end / playback_speed)},Default,,0,0,0,,{{\\pos({int(v['width'])//2},{y})}}{text}")
    path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")


def render_one(audio: Path, timed_path: Path, cover: Path, target: Path, cfg: dict) -> list[str]:
    require_ffmpeg()
    warnings: list[str] = []
    timed = json.loads(timed_path.read_text(encoding="utf-8"))
    if not timed.get("segments"):
        warnings.append("timed transcript contains no segments; video has no subtitles")
    if str(timed.get("timing_quality", "")).startswith("manual_"):
        warnings.append("subtitle phrase timing is proportionally estimated within manual speech boundaries; word alignment was not available")
    source_dur = duration(audio)
    speed = float(cfg["video"].get("playback_speed", 1.0))
    if not .5 <= speed <= 2.0:
        raise ValueError("video.playback_speed must be between 0.5 and 2.0")
    dur = source_dur / speed
    width, height, fps = int(cfg["video"]["width"]), int(cfg["video"]["height"]), int(cfg["video"]["fps"])
    wave_y = int(float(cfg["template"]["waveform_anchor_y"]) * height)
    progress_y = int(float(cfg["template"]["progress_anchor_y"]) * height)
    with tempfile.TemporaryDirectory(prefix="podcast-clips-") as temp:
        temp_path = Path(temp)
        background, ass = temp_path / "background.png", temp_path / "captions.ass"
        _background(cover, background, cfg)
        _write_ass(ass, timed, cfg, speed)
        target.parent.mkdir(parents=True, exist_ok=True)
        accent = cfg["brand"]["accent_color"]
        ff_accent = "0x" + accent.lstrip("#")
        progress_x = int(width * .14)
        progress_w = int(width * .72)
        # Audio-driven waveform is generated from the real clip, overlaid under subtitles.
        accent_rgb = tuple(int(accent.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
        graph = (f"[1:a]atempo={speed:.6f},asplit=2[sped_audio][wave_audio];"
                 f"[wave_audio]aformat=channel_layouts=mono,showwaves=s={progress_w}x140:mode=cline:rate={fps}:colors=white,format=rgba,"
                 f"lutrgb=r={accent_rgb[0]}:g={accent_rgb[1]}:b={accent_rgb[2]},colorchannelmixer=aa=0.9[wave];"
                 f"[0:v][wave]overlay=x=(W-w)/2:y={wave_y}-h/2:shortest=1[wv];"
                 f"[wv]drawbox=x={progress_x}:y={progress_y}:w={progress_w}:h=5:color=white@0.25:t=fill[track];"
                 f"color=c={ff_accent}:s={progress_w}x5:r={fps}:d={dur:.6f}[bar0];"
                 f"[bar0]scale=w='max(1,iw*min(t/{dur:.6f},1))':h=5:eval=frame[bar];"
                 f"[track][bar]overlay=x={progress_x}:y={progress_y}:shortest=1[pb];"
                 f"color=c={ff_accent}:s=14x14:r={fps}:d={dur:.6f}[dot];"
                 f"[pb][dot]overlay=x='{progress_x}+{progress_w}*min(t/{dur:.6f},1)-7':y={progress_y-5}:shortest=1,"
                 f"ass='{str(ass).replace(chr(39), chr(92)+chr(39))}'[outv]")
        codec = "libx264" if cfg["video"].get("codec", "h264") == "h264" else cfg["video"]["codec"]
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-loop", "1", "-framerate", str(fps), "-i", str(background), "-i", str(audio), "-filter_complex", graph, "-map", "[outv]", "-map", "[sped_audio]", "-t", f"{dur:.6f}", "-r", str(fps), "-c:v", codec, "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(target)]
        subprocess.run(cmd, check=True)
    return warnings


def run_render(*, manifest_path: str | None, audio_path: str | None, timed_path: str | None,
               cover_path: str, config_path: str | None, out: str, clip_id: str | None = None) -> tuple[dict, int]:
    cfg = DEFAULTS
    if config_path:
        cfg = _merge(DEFAULTS, yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {})
    cover = Path(cover_path).resolve()
    if not cover.is_file():
        raise FileNotFoundError(f"Cover image not found: {cover}")
    output = Path(out).resolve(); output.mkdir(parents=True, exist_ok=True)
    jobs = []
    if manifest_path:
        manifest_file = Path(manifest_path).resolve()
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        base = manifest_file.parent
        for clip in manifest.get("clips", []):
            if clip.get("status") == "exported" and (not clip_id or clip["id"] == clip_id):
                jobs.append((clip["id"], (base / clip["audio_path"]).resolve(), (base / clip["timed_transcript_path"]).resolve()))
    else:
        if not audio_path or not timed_path:
            raise ValueError("render requires --manifest, or both --audio and --timed-transcript")
        jobs.append((clip_id or Path(audio_path).stem, Path(audio_path).resolve(), Path(timed_path).resolve()))
    if not jobs:
        raise ValueError("No exported clips eligible for rendering")
    records, failed = [], 0
    for cid, audio, timed in jobs:
        target = output / f"{cid}.mp4"
        try:
            warnings = render_one(audio, timed, cover, target, cfg)
            records.append({"id": cid, "status": "rendered", "audio_path": str(audio), "timed_transcript_path": str(timed), "video_path": str(target), "codec": "H.264/AAC", "width": cfg["video"]["width"], "height": cfg["video"]["height"], "fps": cfg["video"]["fps"], "playback_speed": cfg["video"].get("playback_speed", 1.0), "duration_sec": round(duration(target), 3), "warnings": warnings})
        except Exception as exc:
            failed += 1
            records.append({"id": cid, "status": "failed", "audio_path": str(audio), "timed_transcript_path": str(timed), "video_path": None, "warnings": [str(exc)]})
    report = {
        "schema_version": 1,
        "template": "blurred-cover-audiogram-v1",
        "cover_path": str(cover),
        "renders": records,
    }
    (output / "render-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report, 2 if failed else 0

