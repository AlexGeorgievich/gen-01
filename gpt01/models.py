from dataclasses import dataclass


@dataclass(slots=True)
class Document:
    original: str = ""
    translation: str = ""
    transcription: str = ""


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
