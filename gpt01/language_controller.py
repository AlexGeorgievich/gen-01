from __future__ import annotations

from pathlib import Path
from typing import Any

from .asian_numerals import AsianNumeralProcessor, AsianNumeralTranslationProvider
from .french_grammar import (
    FrenchArticleMode,
    FrenchGrammarProcessor,
    FrenchTranslationProvider,
)
from .languages import LanguageProfile, get_language
from .services import GoogleTranslationProvider, TranslationProvider
from .transcription import transcribe


class LanguageController:
    """Coordinate target profile, source language, translation and transcription."""

    def __init__(
        self,
        target_key: str,
        source_key: str = "auto",
        french_article_mode: FrenchArticleMode | str = FrenchArticleMode.AUTO,
        french_lexicon_path: Path | None = None,
    ) -> None:
        self.profile = get_language(target_key)
        self.source_key = source_key
        self.french_processor = FrenchGrammarProcessor(
            french_article_mode,
            french_lexicon_path,
        )
        self.asian_numeral_processor = (
            AsianNumeralProcessor(self.profile.key)
            if self.profile.key in {"Chine", "Japan"}
            else None
        )
        self.translator = self._build_translator()

    @property
    def source_code(self) -> str:
        if self.source_key == "auto":
            return "auto"
        return get_language(self.source_key).translation_code

    def select_target(self, key: str) -> LanguageProfile:
        self.profile = get_language(key)
        self.asian_numeral_processor = (
            AsianNumeralProcessor(self.profile.key)
            if self.profile.key in {"Chine", "Japan"}
            else None
        )
        self.translator = self._build_translator()
        return self.profile

    def select_source(self, key: str) -> None:
        self.source_key = key
        self.translator = self._build_translator()

    def set_french_article_mode(self, mode: FrenchArticleMode | str) -> None:
        self.french_processor.set_mode(mode)
        self.translator = self._build_translator()

    def prepare_translation(self, source: str, translated: str) -> str:
        if self.profile.key == "French":
            return self.french_processor.process(source, translated)
        if self.asian_numeral_processor:
            return self.asian_numeral_processor.process(source, translated)
        return translated

    def transcribe(self, text: str) -> str:
        return transcribe(text, self.profile.transcription_mode)

    def prepare_speech(self, text: str) -> str:
        if self.asian_numeral_processor:
            return self.asian_numeral_processor.prepare_speech(text)
        return text

    def filter_voices(self, voices: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            (
                voice
                for voice in voices
                if str(voice.get("Locale", "")).startswith(self.profile.voice_prefix)
            ),
            key=lambda voice: (str(voice.get("Locale")), str(voice.get("ShortName"))),
        )

    def _build_translator(self) -> TranslationProvider:
        provider = GoogleTranslationProvider(
            self.profile.translation_code,
            self.source_code,
        )
        if self.profile.key == "French":
            return FrenchTranslationProvider(provider, self.french_processor)
        if self.asian_numeral_processor:
            return AsianNumeralTranslationProvider(
                provider,
                self.asian_numeral_processor,
            )
        return provider
