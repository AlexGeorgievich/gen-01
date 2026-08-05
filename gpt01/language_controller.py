from __future__ import annotations

from typing import Any

from .languages import LanguageProfile, get_language
from .services import GoogleTranslationProvider
from .transcription import transcribe


class LanguageController:
    """Coordinate target profile, source language, translation and transcription."""

    def __init__(self, target_key: str, source_key: str = "auto") -> None:
        self.profile = get_language(target_key)
        self.source_key = source_key
        self.translator = self._build_translator()

    @property
    def source_code(self) -> str:
        if self.source_key == "auto":
            return "auto"
        return get_language(self.source_key).translation_code

    def select_target(self, key: str) -> LanguageProfile:
        self.profile = get_language(key)
        self.translator = self._build_translator()
        return self.profile

    def select_source(self, key: str) -> None:
        self.source_key = key
        self.translator = self._build_translator()

    def transcribe(self, text: str) -> str:
        return transcribe(text, self.profile.transcription_mode)

    def filter_voices(self, voices: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            (
                voice
                for voice in voices
                if str(voice.get("Locale", "")).startswith(self.profile.voice_prefix)
            ),
            key=lambda voice: (str(voice.get("Locale")), str(voice.get("ShortName"))),
        )

    def _build_translator(self) -> GoogleTranslationProvider:
        return GoogleTranslationProvider(self.profile.translation_code, self.source_code)
