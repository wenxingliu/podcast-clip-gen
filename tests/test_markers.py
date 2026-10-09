from pathlib import Path

import pytest

from podcast_shorts.transcript_markers import MarkerError, parse_transcript


def test_parse_multiple_markers(tmp_path: Path):
    path = tmp_path / "episode.md"
    path.write_text("前文\n<!-- CLIP_START id=a -->\n甲：你好。\n<!-- CLIP_END id=a -->\n中间\n<!-- CLIP_START id=b-2 -->\nB: hello 世界\n<!-- CLIP_END id=b-2 -->", encoding="utf-8")
    clips, full = parse_transcript(path)
    assert [c.id for c in clips] == ["a", "b-2"]
    assert clips[0].alignment_text == "你好。"
    assert "前文" in full and "CLIP_START" not in full


@pytest.mark.parametrize("text, expected", [
    ("<!-- CLIP_START id=a -->\nx\n<!-- CLIP_END id=b -->", "Mismatched"),
    ("<!-- CLIP_START id=a -->\nx", "has no end"),
    ("<!-- CLIP_END id=a -->", "has no start"),
    ("<!-- CLIP_START id=bad id -->", "Malformed"),
])
def test_invalid_markers(tmp_path: Path, text: str, expected: str):
    path = tmp_path / "bad.md"; path.write_text(text, encoding="utf-8")
    with pytest.raises(MarkerError, match=expected):
        parse_transcript(path)

