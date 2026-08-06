from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SubtitleCue:
    index: str
    timing: str
    source_lines: tuple[str, ...]
    text: str


@dataclass(slots=True)
class Document:
    original: str = ""
    translation: str = ""
    transcription: str = ""
    subtitles: tuple[SubtitleCue, ...] = ()


@dataclass(frozen=True, slots=True)
class Voice:
    short_name: str
    locale: str
    gender: str


@dataclass(frozen=True, slots=True)
class TranslationRow:
    index: int
    source: str
    translation: str = ""
    transcription: str = ""
