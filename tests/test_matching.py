from podcast_shorts.normalize_match import locate, normalize


def test_normalization_handles_width_punctuation_and_speakers():
    assert normalize("嘉宾：Ｈｅｌｌｏ，世 界！") == "hello世界"


def test_context_disambiguates_repeated_phrase():
    corpus = "开头甲重复句结尾第一中间乙重复句结尾第二"
    match = locate("重复句", corpus, before="中间乙", after="结尾第二")
    assert match is not None
    assert match.start == corpus.rfind("重复句")
    assert match.score > match.second_score


def test_fuzzy_match():
    match = locate("我很喜欢观察昆虫", "前面我喜欢观察小昆虫尤其是蝴蝶后面")
    assert match is not None
    assert match.score > .65

