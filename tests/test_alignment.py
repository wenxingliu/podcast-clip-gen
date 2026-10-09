import json
from pathlib import Path

from podcast_shorts.alignment import load_alignment, token_corpus


def test_segment_fallback_builds_timed_chars(tmp_path: Path):
    path = tmp_path / "a.json"
    path.write_text(json.dumps({"segments": [{"start": 1, "end": 2, "text": "你好！"}]}), encoding="utf-8")
    tokens = load_alignment(path)
    corpus, owners = token_corpus(tokens)
    assert corpus == "你好"
    assert tokens[0].start == 1
    assert tokens[-1].end == 2
    assert owners == [0, 1]

