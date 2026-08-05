from gpt01.transcription import to_pinyin, to_romaji, transcribe


def test_empty_text():
    assert to_pinyin("") == ""


def test_chinese_text_uses_tone_marks():
    assert to_pinyin("你好") == "nǐ hǎo"


def test_line_breaks_are_preserved():
    assert to_pinyin("你\n好") == "nǐ\nhǎo"


def test_punctuation_is_preserved():
    result = to_pinyin("你好！")
    assert result == "nǐ hǎo ！"


def test_japanese_text_is_converted_to_romaji():
    result = to_romaji("こんにちは")
    assert result
    assert result.isascii()


def test_latin_transcription_keeps_french_text():
    assert transcribe("Bonjour le monde", "latin") == "Bonjour le monde"


def test_transcription_dispatches_pinyin():
    assert transcribe("你好", "pinyin") == "nǐ hǎo"
