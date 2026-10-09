from podcast_shorts.cutter import _overrides


def test_override_list_and_mapping_formats(tmp_path):
    mapping = tmp_path / "mapping.json"
    mapping.write_text('{"clips":{"x":{"start_sec":1,"end_sec":2}}}', encoding="utf-8")
    assert _overrides(str(mapping))["x"]["end_sec"] == 2

    items = tmp_path / "items.json"
    items.write_text('{"clips":[{"id":"y","start_sec":3,"end_sec":4}]}', encoding="utf-8")
    assert _overrides(str(items))["y"]["start_sec"] == 3
