from __future__ import annotations

import json
import logging
import shutil
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .languages import (
    LanguageProfile,
    load_selected_language,
    save_selected_language,
)
from .preferences import Preferences, load_preferences, save_preferences
from .state import AppState, load_app_state, save_app_state

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RestoredSession:
    state: AppState
    audio_path: Path | None


class SessionRepository:
    """Own persistent paths and serialization for language-specific sessions."""

    def __init__(self, application_root: Path) -> None:
        self.application_root = application_root
        self.data_root = application_root / "language_data"
        self.selection_path = application_root / "language_selection.json"
        self.preferences_path = application_root / "settings.json"
        self.legacy_state_path = application_root / "app_state.json"
        self.legacy_audio_path = application_root / "last_audio.mp3"

    def language_directory(self, profile: LanguageProfile) -> Path:
        return self.data_root / profile.key

    def ensure_language_directory(self, profile: LanguageProfile) -> Path:
        directory = self.language_directory(profile)
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def state_path(self, profile: LanguageProfile) -> Path:
        return self.language_directory(profile) / "app_state.json"

    def audio_path(self, profile: LanguageProfile) -> Path:
        return self.language_directory(profile) / "last_audio.mp3"

    def voice_cache_path(self, profile: LanguageProfile) -> Path:
        return self.language_directory(profile) / "voices_cache.json"

    def french_lexicon_path(self) -> Path:
        return self.data_root / "French" / "lexicon.json"

    def load_selected_language(self) -> str:
        return load_selected_language(self.selection_path)

    def save_selected_language(self, key: str) -> None:
        save_selected_language(self.selection_path, key)

    def load_preferences(self) -> Preferences:
        return load_preferences(self.preferences_path)

    def save_preferences(self, preferences: Preferences) -> None:
        save_preferences(self.preferences_path, preferences)

    def load_voices(self, profile: LanguageProfile) -> list[dict[str, Any]]:
        try:
            data = json.loads(self.voice_cache_path(profile).read_text(encoding="utf-8"))
            if isinstance(data, list) and data:
                return data
        except (OSError, ValueError, TypeError):
            pass
        return list(profile.fallback_voices)

    def save_voices(self, profile: LanguageProfile, voices: list[dict[str, Any]]) -> None:
        self.ensure_language_directory(profile)
        self.voice_cache_path(profile).write_text(
            json.dumps(voices, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def export_path(self, profile: LanguageProfile, selected: str, extension: str) -> Path:
        extension = extension if extension.startswith(".") else f".{extension}"
        selected_path = Path(selected)
        stem = selected_path.stem if selected_path.suffix else selected_path.name
        suffix = f"_{profile.file_suffix}"
        if not stem.lower().endswith(suffix.lower()):
            stem += suffix
        return self.ensure_language_directory(profile) / f"{stem}{extension}"

    def load_session(self, profile: LanguageProfile) -> RestoredSession:
        state_path = self.state_path(profile)
        load_path = state_path
        if not state_path.exists() and profile.key == "Chine" and self.legacy_state_path.exists():
            load_path = self.legacy_state_path
        state = load_app_state(load_path)
        audio_path: Path | None = None
        if state.audio_file:
            candidate = load_path.parent / state.audio_file
            if candidate.is_file():
                audio_path = candidate
        elif load_path == self.legacy_state_path and self.legacy_audio_path.is_file():
            audio_path = self.legacy_audio_path
        return RestoredSession(state, audio_path)

    def save_session(
        self,
        profile: LanguageProfile,
        state: AppState,
        current_audio: Path | None,
    ) -> None:
        self.ensure_language_directory(profile)
        persistent_audio = self.audio_path(profile)
        audio_file = ""
        if current_audio and current_audio.is_file():
            if current_audio.resolve() != persistent_audio.resolve():
                shutil.copyfile(current_audio, persistent_audio)
            audio_file = persistent_audio.name
        save_app_state(self.state_path(profile), replace(state, audio_file=audio_file))

    @staticmethod
    def delete_temporary_audio(path: Path | None) -> None:
        if not path:
            return
        try:
            temp_root = Path(tempfile.gettempdir()).resolve()
            if path.parent.resolve() == temp_root and path.name.startswith("gpt01_"):
                path.unlink(missing_ok=True)
        except OSError:
            LOGGER.warning("Could not remove temporary audio: %s", path)
