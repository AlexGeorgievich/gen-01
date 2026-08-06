import pytest

from gpt01.asian_numerals import (
    AsianNumeralProcessor,
    AsianNumeralTranslationProvider,
    format_asian_cardinal,
    japanese_cardinal_kana,
    japanese_cardinal_romaji,
    parse_asian_cardinal,
    parse_russian_cardinal,
)


class StubTranslator:
    target_language = "ja"
    source_language = "ru"

    def __init__(self, result: str) -> None:
        self.result = result

    def translate(self, _text, _cancelled=None):
        return self.result


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("ноль", 0),
        ("один", 1),
        ("двадцать пять", 25),
        ("сто один", 101),
        ("две тысячи двадцать шесть", 2026),
        ("один миллион двести тысяч триста", 1_200_300),
    ],
)
def test_parse_russian_cardinal(source, expected):
    assert parse_russian_cardinal(source) == expected


@pytest.mark.parametrize(
    "source",
    ["первый", "два стола", "версия 2", "12.08.2026", "один два", "десять один"],
)
def test_non_cardinal_or_contextual_text_is_not_parsed(source):
    assert parse_russian_cardinal(source) is None


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        (0, "零"),
        (10, "十"),
        (11, "十一"),
        (20, "二十"),
        (101, "一百零一"),
        (110, "一百一十"),
        (1001, "一千零一"),
        (10_010, "一万零一十"),
        (100_000, "十万"),
        (100_000_001, "一亿零一"),
    ],
)
def test_format_chinese_cardinal(number, expected):
    assert format_asian_cardinal(number, "Chine") == expected


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        (0, "零"),
        (10, "十"),
        (11, "十一"),
        (20, "二十"),
        (101, "百一"),
        (110, "百十"),
        (1001, "千一"),
        (10_010, "一万十"),
        (100_000, "十万"),
        (100_000_001, "一億一"),
    ],
)
def test_format_japanese_cardinal(number, expected):
    assert format_asian_cardinal(number, "Japan") == expected


@pytest.mark.parametrize(
    ("written", "number", "reading"),
    [
        ("四", 4, "yon"),
        ("七", 7, "nana"),
        ("十八", 18, "juuhachi"),
        ("二十", 20, "nijuu"),
        ("三百", 300, "sanbyaku"),
        ("六百", 600, "roppyaku"),
        ("八千", 8000, "hassen"),
        ("一万十", 10_010, "ichimanjuu"),
    ],
)
def test_japanese_cardinal_uses_preferred_study_reading(written, number, reading):
    assert parse_asian_cardinal(written) == number
    assert japanese_cardinal_romaji(written) == reading


def test_japanese_cardinal_provides_unambiguous_kana_for_tts():
    assert japanese_cardinal_kana("四") == "よん"
    assert japanese_cardinal_kana("七") == "なな"
    assert japanese_cardinal_kana("三百") == "さんびゃく"
    assert japanese_cardinal_kana("八千") == "はっせん"


def test_japanese_processor_replaces_digits_and_counter_suffixes():
    processor = AsianNumeralProcessor("Japan")

    assert processor.process(
        "один\nдва\nвосемнадцать\nдвадцать",
        "1つ\n2つ\n十八\n20",
    ) == "一\n二\n十八\n二十"
    assert processor.prepare_speech("四\n七\n普通の文") == "よん\nなな\n普通の文"


def test_chinese_processor_normalizes_cardinals_but_not_context():
    processor = AsianNumeralProcessor("Chine")

    assert processor.process("семьдесят", "70") == "七十"
    assert processor.process("у меня две книги", "我有两本书") == "我有两本书"
    assert processor.process("12.08.2026", "2026年8月12日") == "2026年8月12日"


def test_processor_can_use_numeric_translation_for_another_source_language():
    processor = AsianNumeralProcessor("Chine")

    assert processor.process("twenty", "20") == "二十"


def test_translation_provider_applies_numeral_processor():
    provider = AsianNumeralTranslationProvider(
        StubTranslator("1つ"),
        AsianNumeralProcessor("Japan"),
    )

    assert provider.translate("один") == "一"
    assert provider.target_language == "ja"
    assert provider.source_language == "ru"
