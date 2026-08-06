from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

LOGGER = logging.getLogger(__name__)

_SENTENCE_END = re.compile(r"[.!?…。！？][\"'»”\)\]]*\s*$")
_DETERMINER = re.compile(
    r"^(?:le|la|les|l['’]|un|une|des|du|de\s+la|de\s+l['’]|au|aux|"
    r"ce|cet|cette|ces|mon|ma|mes|ton|ta|tes|son|sa|ses|notre|nos|"
    r"votre|vos|leur|leurs)\b",
    re.IGNORECASE,
)
_SINGLE_WORD = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿŒœÆæÇç'’\-]+$")
_EDGE_PUNCTUATION = " \t\r\n\"'«»“”„()[]{}.,;:!?…"
_VOWELS = frozenset("aàâäæeéèêëiîïoôöœuùûüyÿ")


class FrenchArticleMode(StrEnum):
    AUTO = "auto"
    DEFINITE = "definite"
    INDEFINITE = "indefinite"
    OFF = "off"

    @classmethod
    def parse(cls, value: object) -> FrenchArticleMode:
        try:
            return cls(str(value))
        except ValueError:
            return cls.AUTO


@dataclass(frozen=True, slots=True)
class FrenchLexiconEntry:
    gender: str
    elision: bool = False

    @classmethod
    def from_dict(cls, data: object) -> FrenchLexiconEntry | None:
        if not isinstance(data, dict):
            return None
        gender = str(data.get("gender", "")).casefold()
        if gender not in {"masculine", "feminine"}:
            return None
        return cls(gender=gender, elision=bool(data.get("elision", False)))


DEFAULT_FRENCH_LEXICON: dict[str, Any] = {
    "entries": {
        "ami": {"gender": "masculine", "elision": True},
        "animal": {"gender": "masculine", "elision": True},
        "arbre": {"gender": "masculine", "elision": True},
        "avion": {"gender": "masculine", "elision": True},
        "bureau": {"gender": "masculine", "elision": False},
        "chaise": {"gender": "feminine", "elision": False},
        "chambre": {"gender": "feminine", "elision": False},
        "chat": {"gender": "masculine", "elision": False},
        "chien": {"gender": "masculine", "elision": False},
        "école": {"gender": "feminine", "elision": True},
        "église": {"gender": "feminine", "elision": True},
        "enfant": {"gender": "masculine", "elision": True},
        "été": {"gender": "masculine", "elision": True},
        "femme": {"gender": "feminine", "elision": False},
        "fille": {"gender": "feminine", "elision": False},
        "film": {"gender": "masculine", "elision": False},
        "fleur": {"gender": "feminine", "elision": False},
        "fromage": {"gender": "masculine", "elision": False},
        "frère": {"gender": "masculine", "elision": False},
        "famille": {"gender": "feminine", "elision": False},
        "fenêtre": {"gender": "feminine", "elision": False},
        "garçon": {"gender": "masculine", "elision": False},
        "hache": {"gender": "feminine", "elision": False},
        "haine": {"gender": "feminine", "elision": False},
        "haricot": {"gender": "masculine", "elision": False},
        "hasard": {"gender": "masculine", "elision": False},
        "héros": {"gender": "masculine", "elision": False},
        "heure": {"gender": "feminine", "elision": True},
        "histoire": {"gender": "feminine", "elision": True},
        "homme": {"gender": "masculine", "elision": True},
        "hôpital": {"gender": "masculine", "elision": True},
        "hôtel": {"gender": "masculine", "elision": True},
        "huile": {"gender": "feminine", "elision": True},
        "idée": {"gender": "feminine", "elision": True},
        "île": {"gender": "feminine", "elision": True},
        "image": {"gender": "feminine", "elision": True},
        "jardin": {"gender": "masculine", "elision": False},
        "journal": {"gender": "masculine", "elision": False},
        "lampe": {"gender": "feminine", "elision": False},
        "livre": {"gender": "masculine", "elision": False},
        "maison": {"gender": "feminine", "elision": False},
        "marché": {"gender": "masculine", "elision": False},
        "mer": {"gender": "feminine", "elision": False},
        "mère": {"gender": "feminine", "elision": False},
        "montagne": {"gender": "feminine", "elision": False},
        "musée": {"gender": "masculine", "elision": False},
        "musique": {"gender": "feminine", "elision": False},
        "nuit": {"gender": "feminine", "elision": False},
        "œuf": {"gender": "masculine", "elision": True},
        "oiseau": {"gender": "masculine", "elision": True},
        "ordinateur": {"gender": "masculine", "elision": True},
        "orange": {"gender": "feminine", "elision": True},
        "pain": {"gender": "masculine", "elision": False},
        "père": {"gender": "masculine", "elision": False},
        "porte": {"gender": "feminine", "elision": False},
        "promenade": {"gender": "feminine", "elision": False},
        "question": {"gender": "feminine", "elision": False},
        "réponse": {"gender": "feminine", "elision": False},
        "restaurant": {"gender": "masculine", "elision": False},
        "rivière": {"gender": "feminine", "elision": False},
        "route": {"gender": "feminine", "elision": False},
        "rue": {"gender": "feminine", "elision": False},
        "soleil": {"gender": "masculine", "elision": False},
        "sœur": {"gender": "feminine", "elision": False},
        "table": {"gender": "feminine", "elision": False},
        "tableau": {"gender": "masculine", "elision": False},
        "téléphone": {"gender": "masculine", "elision": False},
        "train": {"gender": "masculine", "elision": False},
        "travail": {"gender": "masculine", "elision": False},
        "usine": {"gender": "feminine", "elision": True},
        "vélo": {"gender": "masculine", "elision": False},
        "ville": {"gender": "feminine", "elision": False},
        "voiture": {"gender": "feminine", "elision": False},
        "voyage": {"gender": "masculine", "elision": False},
    },
    "source_overrides": {
        "апельсин": "orange",
        "автомобиль": "voiture",
        "автомобили": "voitures",
        "больница": "hôpital",
        "брат": "frère",
        "велосипед": "vélo",
        "велосипеды": "vélos",
        "герой": "héros",
        "город": "ville",
        "города": "villes",
        "гора": "montagne",
        "газета": "journal",
        "дерево": "arbre",
        "деревья": "arbres",
        "девочка": "fille",
        "дети": "enfants",
        "дом": "maison",
        "дома": "maisons",
        "дверь": "porte",
        "дорога": "route",
        "друг": "ami",
        "женщина": "femme",
        "женщины": "femmes",
        "животное": "animal",
        "завод": "usine",
        "изображение": "image",
        "идея": "idée",
        "картина": "tableau",
        "книга": "livre",
        "книги": "livres",
        "комната": "chambre",
        "компьютер": "ordinateur",
        "компьютеры": "ordinateurs",
        "кот": "chat",
        "коты": "chats",
        "лампа": "lampe",
        "лето": "été",
        "мальчик": "garçon",
        "мальчики": "garçons",
        "масло": "huile",
        "мать": "mère",
        "море": "mer",
        "моря": "mers",
        "мужчина": "homme",
        "музей": "musée",
        "музеи": "musées",
        "музыка": "musique",
        "ненависть": "haine",
        "ночь": "nuit",
        "офис": "bureau",
        "офисы": "bureaux",
        "окно": "fenêtre",
        "окна": "fenêtres",
        "остров": "île",
        "ответ": "réponse",
        "отель": "hôtel",
        "отец": "père",
        "птица": "oiseau",
        "поезд": "train",
        "поезда": "trains",
        "прогулка": "promenade",
        "путешествие": "voyage",
        "работа": "travail",
        "рынок": "marché",
        "рынки": "marchés",
        "река": "rivière",
        "ребёнок": "enfant",
        "ресторан": "restaurant",
        "рестораны": "restaurants",
        "сад": "jardin",
        "сады": "jardins",
        "самолёт": "avion",
        "семья": "famille",
        "семьи": "familles",
        "сестра": "sœur",
        "случай": "hasard",
        "собака": "chien",
        "собаки": "chiens",
        "солнце": "soleil",
        "стол": "table",
        "столы": "tables",
        "стул": "chaise",
        "стулья": "chaises",
        "сыр": "fromage",
        "телефон": "téléphone",
        "телефоны": "téléphones",
        "топор": "hache",
        "улица": "rue",
        "фасоль": "haricot",
        "фильм": "film",
        "фильмы": "films",
        "вопрос": "question",
        "цветок": "fleur",
        "цветы": "fleurs",
        "церковь": "église",
        "час": "heure",
        "хлеб": "pain",
        "школа": "école",
        "школы": "écoles",
        "яйцо": "œuf",
        "история": "histoire",
    },
}


class TranslationProviderLike(Protocol):
    target_language: str
    source_language: str

    def translate(
        self,
        text: str,
        cancelled: Callable[[], bool] | None = None,
    ) -> str: ...


def ensure_french_lexicon(path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(DEFAULT_FRENCH_LEXICON, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


class FrenchGrammarProcessor:
    """Conservatively add articles to known standalone French nouns."""

    def __init__(
        self,
        mode: FrenchArticleMode | str = FrenchArticleMode.AUTO,
        lexicon_path: Path | None = None,
    ) -> None:
        self.mode = FrenchArticleMode.parse(mode)
        self.lexicon_path = lexicon_path
        self.entries: dict[str, FrenchLexiconEntry] = {}
        self.source_overrides: dict[str, str] = {}
        self.reload()

    def reload(self) -> None:
        self.entries = self._parse_entries(DEFAULT_FRENCH_LEXICON.get("entries"))
        self.source_overrides = self._parse_overrides(
            DEFAULT_FRENCH_LEXICON.get("source_overrides")
        )
        if self.lexicon_path is None:
            return
        try:
            ensure_french_lexicon(self.lexicon_path)
            data = json.loads(self.lexicon_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return
            # Accept both the documented flat entry map and the extended format.
            entries_data = data.get("entries", data)
            self.entries.update(self._parse_entries(entries_data))
            self.source_overrides.update(
                self._parse_overrides(data.get("source_overrides"))
            )
        except (OSError, ValueError, TypeError):
            LOGGER.warning("Could not load French lexicon: %s", self.lexicon_path)

    def set_mode(self, mode: FrenchArticleMode | str) -> None:
        self.mode = FrenchArticleMode.parse(mode)

    def process(self, source: str, translated: str) -> str:
        if self.mode == FrenchArticleMode.OFF or not translated.strip():
            return translated

        source_lines = source.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        translated_lines = (
            translated.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        )
        if len(source_lines) == len(translated_lines):
            return "\n".join(
                self._process_phrase(source_line, translated_line)
                for source_line, translated_line in zip(
                    source_lines, translated_lines, strict=True
                )
            )
        return self._process_phrase(source, translated)

    def _process_phrase(self, source: str, translated: str) -> str:
        value = translated.strip()
        if not value or "\n" in value or _SENTENCE_END.search(value):
            return translated
        if _DETERMINER.match(value):
            return translated

        normalized_source = source.strip(_EDGE_PUNCTUATION).casefold()
        override = self.source_overrides.get(normalized_source)
        if override and self._is_standalone_term(source):
            value = override

        if not _SINGLE_WORD.fullmatch(value):
            return translated

        normalized = value.casefold().replace("’", "'")
        entry = self.entries.get(normalized)
        plural = False
        if entry is None:
            for suffix in ("s", "x"):
                if normalized.endswith(suffix) and len(normalized) > 2:
                    entry = self.entries.get(normalized[: -len(suffix)])
                    if entry is not None:
                        plural = True
                        break
        if entry is None:
            return translated

        article_mode = (
            FrenchArticleMode.INDEFINITE
            if self.mode == FrenchArticleMode.AUTO
            else self.mode
        )
        article = self._article(value, entry, plural, article_mode)
        separator = "" if article.endswith("’") else " "
        return f"{article}{separator}{value}"

    @staticmethod
    def _article(
        word: str,
        entry: FrenchLexiconEntry,
        plural: bool,
        mode: FrenchArticleMode,
    ) -> str:
        if mode == FrenchArticleMode.INDEFINITE:
            if plural:
                return "des"
            return "une" if entry.gender == "feminine" else "un"
        if plural:
            return "les"
        starts_with_vowel = word[0].casefold() in _VOWELS
        if entry.elision or starts_with_vowel:
            return "l’"
        return "la" if entry.gender == "feminine" else "le"

    @staticmethod
    def _is_standalone_term(text: str) -> bool:
        value = text.strip(_EDGE_PUNCTUATION)
        return bool(value) and not any(character.isspace() for character in value)

    @staticmethod
    def _parse_entries(data: object) -> dict[str, FrenchLexiconEntry]:
        if not isinstance(data, dict):
            return {}
        result: dict[str, FrenchLexiconEntry] = {}
        for word, raw_entry in data.items():
            entry = FrenchLexiconEntry.from_dict(raw_entry)
            if entry is not None:
                result[str(word).strip().casefold().replace("’", "'")] = entry
        return result

    @staticmethod
    def _parse_overrides(data: object) -> dict[str, str]:
        if not isinstance(data, dict):
            return {}
        return {
            str(source).strip().casefold(): str(target).strip()
            for source, target in data.items()
            if str(source).strip() and str(target).strip()
        }


class FrenchTranslationProvider:
    """Decorate a translation provider with French noun post-processing."""

    def __init__(
        self,
        provider: TranslationProviderLike,
        processor: FrenchGrammarProcessor,
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
