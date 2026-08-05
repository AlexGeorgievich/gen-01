from dataclasses import dataclass


@dataclass(slots=True)
class Document:
    original: str = ""
    translation: str = ""
    transliteration: str = ""


@dataclass(frozen=True, slots=True)
class Voice:
    short_name: str
    locale: str
    gender: str
