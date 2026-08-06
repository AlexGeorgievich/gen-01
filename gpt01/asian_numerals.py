from __future__ import annotations

import re
from collections.abc import Callable
from typing import Protocol


class TranslationProviderLike(Protocol):
    target_language: str
    source_language: str

    def translate(
        self,
        text: str,
        cancelled: Callable[[], bool] | None = None,
    ) -> str: ...


_RUSSIAN_VALUES = {
    "ноль": 0,
    "один": 1,
    "одна": 1,
    "одно": 1,
    "два": 2,
    "две": 2,
    "три": 3,
    "четыре": 4,
    "пять": 5,
    "шесть": 6,
    "семь": 7,
    "восемь": 8,
    "девять": 9,
    "десять": 10,
    "одиннадцать": 11,
    "двенадцать": 12,
    "тринадцать": 13,
    "четырнадцать": 14,
    "пятнадцать": 15,
    "шестнадцать": 16,
    "семнадцать": 17,
    "восемнадцать": 18,
    "девятнадцать": 19,
    "двадцать": 20,
    "тридцать": 30,
    "сорок": 40,
    "пятьдесят": 50,
    "шестьдесят": 60,
    "семьдесят": 70,
    "восемьдесят": 80,
    "девяносто": 90,
    "сто": 100,
    "двести": 200,
    "триста": 300,
    "четыреста": 400,
    "пятьсот": 500,
    "шестьсот": 600,
    "семьсот": 700,
    "восемьсот": 800,
    "девятьсот": 900,
}
_RUSSIAN_SCALES = {
    "тысяча": 1_000,
    "тысячи": 1_000,
    "тысяч": 1_000,
    "миллион": 1_000_000,
    "миллиона": 1_000_000,
    "миллионов": 1_000_000,
}
_STANDALONE_WORDS = re.compile(r"[А-Яа-яЁёA-Za-z -]+")
_INTEGER = re.compile(r"\d+")
_JAPANESE_DIGIT_TRANSLATION = re.compile(r"(?P<number>\d+)\s*(?:つ)?")
_ASIAN_CARDINAL = re.compile(r"[零一二三四五六七八九十百千万億亿]+")
_DIGITS = "零一二三四五六七八九"
_DIGIT_VALUES = {character: value for value, character in enumerate(_DIGITS)}


def parse_russian_cardinal(text: str) -> int | None:
    """Parse a standalone Russian cardinal number up to 999,999,999."""
    value = text.strip().casefold().replace("ё", "е")
    if not value or not _STANDALONE_WORDS.fullmatch(value):
        return None
    tokens = value.replace("-", " ").split()
    total = 0
    group = 0
    matched = False
    previous_scale = 1_000_000_000
    previous_value = 1_000
    for token in tokens:
        if token in _RUSSIAN_VALUES:
            token_value = _RUSSIAN_VALUES[token]
            if token_value == 0 and len(tokens) != 1:
                return None
            if 10 <= previous_value <= 19:
                return None
            if group and token_value >= previous_value:
                return None
            group += token_value
            previous_value = token_value
            matched = True
            continue
        scale = _RUSSIAN_SCALES.get(token)
        if scale is None or scale >= previous_scale or group > 999:
            return None
        total += (group or 1) * scale
        group = 0
        previous_value = 1_000
        previous_scale = scale
        matched = True
    result = total + group
    return result if matched and result <= 999_999_999 else None


def _four_digit_group(number: int, *, include_leading_one: bool, chinese: bool) -> str:
    units = ("", "十", "百", "千")
    digits = [number // 1000, number // 100 % 10, number // 10 % 10, number % 10]
    output: list[str] = []
    pending_zero = False
    for index, digit in enumerate(digits):
        power = 3 - index
        if digit == 0:
            if output and any(digits[index + 1 :]):
                pending_zero = True
            continue
        if pending_zero and chinese:
            output.append("零")
        pending_zero = False
        omit_one = digit == 1 and (
            (chinese and not output and power == 1 and not include_leading_one)
            or (not chinese and power > 0)
        )
        if not omit_one:
            output.append(_DIGITS[digit])
        output.append(units[power])
    return "".join(output)


def format_asian_cardinal(number: int, target_key: str) -> str:
    """Render a non-negative integer with Chinese or Japanese number characters."""
    if number < 0 or number > 999_999_999:
        raise ValueError("number must be between 0 and 999,999,999")
    if target_key not in {"Chine", "Japan"}:
        raise ValueError("target_key must be Chine or Japan")
    if number == 0:
        return "零"

    chinese = target_key == "Chine"
    group_units = ("", "万", "亿" if chinese else "億")
    groups: list[int] = []
    remaining = number
    while remaining:
        remaining, group = divmod(remaining, 10_000)
        groups.append(group)

    parts: list[str] = []
    pending_zero = False
    for group_index in range(len(groups) - 1, -1, -1):
        group = groups[group_index]
        if not group:
            if parts and any(groups[:group_index]):
                pending_zero = True
            continue
        if chinese and parts and (pending_zero or group < 1_000):
            parts.append("零")
        pending_zero = False
        parts.append(
            _four_digit_group(
                group,
                include_leading_one=chinese and bool(parts) and group_index == 0,
                chinese=chinese,
            )
        )
        parts.append(group_units[group_index])
    return "".join(parts)


def parse_asian_cardinal(text: str) -> int | None:
    """Parse the canonical Chinese/Japanese integer form produced by this module."""
    value = text.strip()
    if not value or not _ASIAN_CARDINAL.fullmatch(value):
        return None
    total = 0
    group = 0
    digit: int | None = None
    for character in value:
        if character in _DIGIT_VALUES:
            digit = _DIGIT_VALUES[character]
            continue
        if character in "十百千":
            unit = {"十": 10, "百": 100, "千": 1_000}[character]
            group += (1 if digit is None else digit) * unit
            digit = None
            continue
        large_unit = 10_000 if character == "万" else 100_000_000
        total += (group + (digit or 0) or 1) * large_unit
        group = 0
        digit = None
    return total + group + (digit or 0)


def _japanese_cardinal_reading(text: str, *, kana: bool) -> str | None:
    number = parse_asian_cardinal(text)
    if number is None:
        return None
    if number == 0:
        return "れい" if kana else "rei"

    if kana:
        digits = ("", "いち", "に", "さん", "よん", "ご", "ろく", "なな", "はち", "きゅう")
        hundreds = (
            "", "ひゃく", "にひゃく", "さんびゃく", "よんひゃく", "ごひゃく",
            "ろっぴゃく", "ななひゃく", "はっぴゃく", "きゅうひゃく",
        )
        thousands = (
            "", "せん", "にせん", "さんぜん", "よんせん", "ごせん", "ろくせん",
            "ななせん", "はっせん", "きゅうせん",
        )
        ten = "じゅう"
        group_units = ("", "まん", "おく")
    else:
        digits = (
            "", "ichi", "ni", "san", "yon", "go", "roku", "nana", "hachi", "kyuu",
        )
        hundreds = (
            "", "hyaku", "nihyaku", "sanbyaku", "yonhyaku", "gohyaku",
            "roppyaku", "nanahyaku", "happyaku", "kyuuhyaku",
        )
        thousands = (
            "", "sen", "nisen", "sanzen", "yonsen", "gosen", "rokusen",
            "nanasen", "hassen", "kyuusen",
        )
        ten = "juu"
        group_units = ("", "man", "oku")

    def read_group(group: int) -> list[str]:
        output: list[str] = []
        if group // 1_000:
            output.append(thousands[group // 1_000])
        if group // 100 % 10:
            output.append(hundreds[group // 100 % 10])
        if group // 10 % 10:
            tens = group // 10 % 10
            output.append(ten if tens == 1 else f"{digits[tens]}{ten}")
        if group % 10:
            output.append(digits[group % 10])
        return output

    groups: list[int] = []
    remaining = number
    while remaining:
        remaining, group = divmod(remaining, 10_000)
        groups.append(group)
    reading: list[str] = []
    for group_index in range(len(groups) - 1, -1, -1):
        if groups[group_index]:
            reading.extend(read_group(groups[group_index]))
            if group_index:
                reading.append(group_units[group_index])
    return "".join(reading)


def japanese_cardinal_romaji(text: str) -> str | None:
    """Return the preferred standalone Japanese counting reading in romaji."""
    return _japanese_cardinal_reading(text, kana=False)


def japanese_cardinal_kana(text: str) -> str | None:
    """Return an unambiguous kana reading suitable for Japanese TTS."""
    return _japanese_cardinal_reading(text, kana=True)


class AsianNumeralProcessor:
    """Normalize standalone study-card numerals for Chinese and Japanese."""

    def __init__(self, target_key: str) -> None:
        if target_key not in {"Chine", "Japan"}:
            raise ValueError("target_key must be Chine or Japan")
        self.target_key = target_key

    def process(self, source: str, translated: str) -> str:
        source_lines = source.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        translated_lines = (
            translated.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        )
        if len(source_lines) != len(translated_lines):
            return self._process_line(source, translated)
        return "\n".join(
            self._process_line(source_line, translated_line)
            for source_line, translated_line in zip(
                source_lines,
                translated_lines,
                strict=True,
            )
        )

    def prepare_speech(self, text: str) -> str:
        if self.target_key != "Japan":
            return text
        return "\n".join(
            japanese_cardinal_kana(line) or line for line in text.split("\n")
        )

    def _process_line(self, source: str, translated: str) -> str:
        number = parse_russian_cardinal(source)
        if number is None and _INTEGER.fullmatch(source.strip()):
            number = int(source.strip())
        if number is None and _STANDALONE_WORDS.fullmatch(source.strip()):
            pattern = (
                _JAPANESE_DIGIT_TRANSLATION
                if self.target_key == "Japan"
                else _INTEGER
            )
            match = pattern.fullmatch(translated.strip())
            if match:
                number = int(match.groupdict().get("number") or match.group())
        if number is None or number > 999_999_999:
            return translated
        return format_asian_cardinal(number, self.target_key)


class AsianNumeralTranslationProvider:
    """Decorate a translation provider with standalone numeral normalization."""

    def __init__(
        self,
        provider: TranslationProviderLike,
        processor: AsianNumeralProcessor,
    ) -> None:
        self.provider = provider
        self.processor = processor

    @property
    def target_language(self) -> str:
        return self.provider.target_language

    @property
    def source_language(self) -> str:
        return self.provider.source_language

    def translate(
        self,
        text: str,
        cancelled: Callable[[], bool] | None = None,
    ) -> str:
        translated = self.provider.translate(text, cancelled)
        return self.processor.process(text, translated)
