from __future__ import annotations

import logging
import re
import threading
from functools import lru_cache

from pykakasi import kakasi
from pypinyin import Style, lazy_pinyin

try:
    import gruut
except ImportError:  # Приложение остаётся работоспособным без опциональных словарей.
    gruut = None

from .asian_numerals import japanese_cardinal_romaji
from .languages import TranscriptionMode

LOGGER = logging.getLogger(__name__)
_IPA_LANGUAGES = {"ipa_en": "en-us", "ipa_fr": "fr-fr", "ipa_es": "es-es"}
_IPA_VOWEL = re.compile(r"[aeiouyæɑɒɔɛəɚɝɜɞɪʊʌøœɐɨʉɯɤɶɵɘ]", re.IGNORECASE)
_WRITTEN_VOWEL_GROUP = re.compile(r"[aeiouáéíóúü]+", re.IGNORECASE)
_GRUUT_LOCK = threading.RLock()
_RUSSIAN_LETTERS = frozenset("абвгдеёжзийклмнопрстуфхцчшщъыьэюя")
_RUSSIAN_VOWELS = frozenset("аеёиоуыэюя")
_RUSSIAN_PALATALIZING = frozenset("еёиюяь")
_RUSSIAN_ALWAYS_HARD = frozenset("жшц")
_RUSSIAN_CONSONANTS = {
    "б": "b",
    "в": "v",
    "г": "ɡ",
    "д": "d",
    "ж": "ʐ",
    "з": "z",
    "й": "j",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "ф": "f",
    "х": "x",
    "ц": "ts",
    "ч": "tɕ",
    "ш": "ʂ",
    "щ": "ɕː",
}
_RUSSIAN_VOWEL_IPA = {
    "а": "a",
    "е": "e",
    "ё": "o",
    "и": "i",
    "о": "o",
    "у": "u",
    "ы": "ɨ",
    "э": "e",
    "ю": "u",
    "я": "a",
}
_RUSSIAN_IOTATED = frozenset("еёюя")


def to_pinyin(text: str) -> str:
    """Convert Chinese text to readable pinyin while preserving line breaks."""
    lines: list[str] = []
    for line in text.split("\n"):
        syllables = lazy_pinyin(
            line,
            style=Style.TONE,
            neutral_tone_with_five=False,
            errors=lambda chars: list(chars),
        )
        lines.append(" ".join(syllables))
    return "\n".join(lines)


def to_romaji(text: str) -> str:
    """Convert Japanese text to Hepburn romaji while preserving line breaks."""
    converter = kakasi()
    lines: list[str] = []
    for line in text.split("\n"):
        numeral_reading = japanese_cardinal_romaji(line)
        if numeral_reading is not None:
            lines.append(numeral_reading)
            continue
        parts = converter.convert(line)
        lines.append(" ".join(str(part["hepburn"]) for part in parts))
    return "\n".join(lines)


def _move_stress_to_syllable_start(phonemes: list[str]) -> list[str]:
    normalized = list(phonemes)
    for marker in ("ˈ", "ˌ"):
        stressed_indices = [index for index, phone in enumerate(normalized) if marker in phone]
        for stressed_index in stressed_indices:
            normalized[stressed_index] = normalized[stressed_index].replace(marker, "")
            previous_vowel = next(
                (
                    index
                    for index in range(stressed_index - 1, -1, -1)
                    if _IPA_VOWEL.search(normalized[index])
                ),
                None,
            )
            onset_index = 0 if previous_vowel is None else previous_vowel + 1
            normalized[onset_index] = marker + normalized[onset_index]
    return normalized


def _add_spanish_stress(word: str, phonemes: list[str]) -> list[str]:
    if any("ˈ" in phone for phone in phonemes):
        return phonemes
    vowel_indices = [
        index for index, phone in enumerate(phonemes) if _IPA_VOWEL.search(phone)
    ]
    if not vowel_indices:
        return phonemes

    written_groups = list(_WRITTEN_VOWEL_GROUP.finditer(word.lower()))
    accented_group = next(
        (
            index
            for index, group in enumerate(written_groups)
            if any(character in "áéíóú" for character in group.group())
        ),
        None,
    )
    if accented_group is not None:
        stressed_syllable = min(accented_group, len(vowel_indices) - 1)
    elif word.lower().endswith(("a", "e", "i", "o", "u", "n", "s")):
        stressed_syllable = max(0, len(vowel_indices) - 2)
    else:
        stressed_syllable = len(vowel_indices) - 1

    onset_index = 0 if stressed_syllable == 0 else vowel_indices[stressed_syllable - 1] + 1
    stressed = list(phonemes)
    stressed[onset_index] = "ˈ" + stressed[onset_index]
    return stressed


@lru_cache(maxsize=4096)
def _phonemize_line(line: str, language: str) -> str:
    if gruut is None:
        return line
    words: list[str] = []
    with _GRUUT_LOCK:
        sentences = gruut.sentences(line, lang=language)
        for sentence in sentences:
            for word in sentence:
                phonemes = list(word.phonemes or [])
                if not phonemes:
                    continue
                phonemes = _move_stress_to_syllable_start(phonemes)
                if language == "es-es":
                    phonemes = _add_spanish_stress(str(word.text), phonemes)
                words.append("".join(phonemes))
    return f"/{' '.join(words)}/" if words else line


def to_ipa(text: str, language: str) -> str:
    """Convert European-language text to broad IPA while preserving line positions."""
    output: list[str] = []
    for line in text.split("\n"):
        if not line.strip():
            output.append("")
            continue
        try:
            output.append(_phonemize_line(line, language))
        except Exception:
            LOGGER.exception("IPA transcription failed for language %s", language)
            output.append(line)
    return "\n".join(output)


def to_russian_ipa(text: str) -> str:
    """Create a broad phonemic IPA rendering of Russian Cyrillic text."""
    output: list[str] = []
    for line in text.split("\n"):
        if not line.strip():
            output.append("")
            continue
        rendered: list[str] = []
        for index, character in enumerate(line):
            letter = character.casefold()
            if letter in _RUSSIAN_CONSONANTS:
                phone = _RUSSIAN_CONSONANTS[letter]
                next_letter = line[index + 1].casefold() if index + 1 < len(line) else ""
                if next_letter in _RUSSIAN_PALATALIZING and letter not in _RUSSIAN_ALWAYS_HARD:
                    phone += "ʲ"
                rendered.append(phone)
                continue
            if letter in _RUSSIAN_VOWEL_IPA:
                previous = line[index - 1].casefold() if index else ""
                if letter in _RUSSIAN_IOTATED and (
                    not previous or previous in _RUSSIAN_VOWELS or previous in "ьъ"
                    or previous not in _RUSSIAN_LETTERS
                ):
                    rendered.append("j")
                rendered.append(_RUSSIAN_VOWEL_IPA[letter])
                continue
            if letter not in "ьъ":
                rendered.append(character)
        output.append(f"/{''.join(rendered).strip()}/")
    return "\n".join(output)


def transcribe(text: str, mode: TranscriptionMode) -> str:
    if mode == "pinyin":
        return to_pinyin(text)
    if mode == "romaji":
        return to_romaji(text)
    if mode == "ipa_ru":
        return to_russian_ipa(text)
    if mode in _IPA_LANGUAGES:
        return to_ipa(text, _IPA_LANGUAGES[mode])
    return text
