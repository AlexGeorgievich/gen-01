from gpt01.transliteration import to_pinyin


def test_empty_text():
    assert to_pinyin("") == ""


def test_chinese_text_uses_tone_marks():
    assert to_pinyin("你好") == "nǐ hǎo"


def test_line_breaks_are_preserved():
    assert to_pinyin("你\n好") == "nǐ\nhǎo"


def test_punctuation_is_preserved():
    result = to_pinyin("你好！")
    assert result == "nǐ hǎo ！"
