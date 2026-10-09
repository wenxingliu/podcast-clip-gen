from pathlib import Path

from podcast_shorts.renderer import _phrases, _rollup_text, _split_display_chunks, _write_ass, DEFAULTS


def test_long_segment_is_split_and_timed_proportionally():
    timed = {"segments": [{"text": "这是第一句话，接着是第二句话。最后一句也需要显示。", "start": 1.0, "end": 11.0}]}
    phrases = _phrases(timed, max_chars=10)
    assert len(phrases) >= 3
    assert phrases[0]["start"] == 1.0
    assert abs(phrases[-1]["end"] - 11.0) < 1e-6
    assert all(len(item["text"]) <= 10 for item in phrases)


def test_ass_hard_wraps_cjk_lines(tmp_path: Path):
    target = tmp_path / "captions.ass"
    timed = {"segments": [{"text": "比如说中国人在几千年前就已经开始观星了", "start": 1, "end": 4}]}
    _write_ass(target, timed, DEFAULTS)
    event = [line for line in target.read_text(encoding="utf-8").splitlines() if line.startswith("Dialogue:")][0]
    assert r"\N" in event


def test_ass_cues_do_not_overlap_and_scale_for_speed(tmp_path: Path):
    target = tmp_path / "captions.ass"
    timed = {"segments": [{"text": "第一句话。第二句话。", "start": 1, "end": 5}]}
    _write_ass(target, timed, DEFAULTS, playback_speed=1.1)
    events = [line for line in target.read_text(encoding="utf-8").splitlines() if line.startswith("Dialogue:")]
    assert len(events) == 2
    assert "0:00:00.91" in events[0]


def test_rollup_text_shows_context_and_emphasizes_active_phrase():
    phrases = [
        {"text": f"第{i}句字幕", "start": i, "end": i + 1}
        for i in range(5)
    ]
    config = {**DEFAULTS["template"], "subtitle_mode": "roll_up"}
    text = _rollup_text(phrases, 2, config)
    assert all(f"第{i}句字幕" in text for i in range(5))
    assert r"{\alpha&H00&\fs68}第2句字幕" in text
    assert r"\alpha&H96&" in text
    assert r"\alpha&HCD&" in text
    assert r"\N\N" not in text


def test_ass_rollup_mode_writes_one_window_per_phrase(tmp_path: Path):
    target = tmp_path / "captions.ass"
    timed = {"segments": [{"text": "第一句话。第二句话。第三句话。", "start": 0, "end": 6}]}
    config = {**DEFAULTS, "template": {**DEFAULTS["template"], "subtitle_mode": "roll_up"}}
    _write_ass(target, timed, config)
    events = [line for line in target.read_text(encoding="utf-8").splitlines() if line.startswith("Dialogue:")]
    assert len(events) == 3
    assert "第一句话" in events[1]
    assert "第二句话" in events[1]
    assert "第三句话" in events[1]


def test_display_chunks_do_not_split_latin_words():
    chunks = _split_display_chunks("那些 Millennium Questions 是 question", 12)
    assert "Millennium" in chunks
    assert "Questions 是" in chunks
    assert "".join(chunks).replace(" ", "") == "那些MillenniumQuestions是question"
