from pykakasi import kakasi
from pypinyin import Style, lazy_pinyin

from .languages import TranscriptionMode


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
        parts = converter.convert(line)
        lines.append(" ".join(str(part["hepburn"]) for part in parts))
    return "\n".join(lines)


def transcribe(text: str, mode: TranscriptionMode) -> str:
    if mode == "pinyin":
        return to_pinyin(text)
    if mode == "romaji":
        return to_romaji(text)
    return text
