import gpt01.transcription as transcription
from gpt01.transcription import to_ipa, to_pinyin, to_romaji, transcribe


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


def test_english_uses_broad_ipa():
    assert transcribe("table", "ipa_en") == "/ˈteɪbəl/"


def test_french_uses_broad_ipa():
    assert transcribe("bonjour table", "ipa_fr") == "/bɔ̃ʒuʁ tabl/"


def test_spanish_uses_broad_ipa_with_stress():
    assert transcribe("mesa gracias", "ipa_es") == "/ˈmesa ˈgɾaθʝas/"


def test_russian_uses_broad_phonemic_ipa():
    assert transcribe("Привет, мир!", "ipa_ru") == "/prʲivʲet, mʲir!/"


def test_russian_ipa_preserves_line_positions_and_iotation():
    assert transcribe("Яблоко\n\nРоссия", "ipa_ru") == "/jabloko/\n\n/rossʲija/"


def test_ipa_preserves_line_breaks():
    result = to_ipa("table\n\nworld", "en-us")
    assert result.split("\n") == ["/ˈteɪbəl/", "", "/ˈwɚld/"]


def test_ipa_falls_back_to_original_line_without_dictionary(monkeypatch):
    monkeypatch.setattr(transcription, "gruut", None)
    transcription._phonemize_line.cache_clear()

    assert to_ipa("Unavailable dictionary", "en-us") == "Unavailable dictionary"


def test_transcription_dispatches_pinyin():
    assert transcribe("你好", "pinyin") == "nǐ hǎo"
