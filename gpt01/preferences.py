from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .french_grammar import FrenchArticleMode
from .languages import LANGUAGE_BY_KEY


@dataclass(slots=True)
class Preferences:
    source_language_key: str = "auto"
    editor_font_size: int = 11
    french_article_mode: str = FrenchArticleMode.AUTO.value
    last_open_directory: str = ""
    last_export_directory: str = ""
    interface_language: str = "en"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Preferences:
        source = str(data.get("source_language_key", "auto"))
        if source != "auto" and source not in LANGUAGE_BY_KEY:
            source = "auto"
        try:
            font_size = int(data.get("editor_font_size", 11))
        except (TypeError, ValueError):
            font_size = 11
        last_open_directory = data.get("last_open_directory", "")
        last_export_directory = data.get("last_export_directory", "")
        french_article_mode = FrenchArticleMode.parse(
            data.get("french_article_mode", FrenchArticleMode.AUTO.value)
        )
        interface_language = str(data.get("interface_language", "en")).lower()
        if interface_language not in {"en", "ru"}:
            interface_language = "en"
        return cls(
            source_language_key=source,
            editor_font_size=min(32, max(8, font_size)),
            french_article_mode=french_article_mode.value,
            last_open_directory=(
                last_open_directory.strip() if isinstance(last_open_directory, str) else ""
            ),
            last_export_directory=(
                last_export_directory.strip() if isinstance(last_export_directory, str) else ""
            ),
            interface_language=interface_language,
        )


def load_preferences(path: Path) -> Preferences:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Preferences.from_dict(data) if isinstance(data, dict) else Preferences()
    except (OSError, ValueError, TypeError):
        return Preferences()


def save_preferences(path: Path, preferences: Preferences) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(asdict(preferences), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)
