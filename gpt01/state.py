from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class AppState:
    version: int = 1
    original: str = ""
    translation: str = ""
    transliteration: str = ""
    selected_voice: str = ""
    translation_visible: bool = True
    splitter_sizes: list[int] = field(default_factory=lambda: [420, 420, 420])
    window_geometry: str = ""
    volume: float = 0.9
    current_source_path: str = ""
    audio_file: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppState:
        defaults = cls()
        sizes = data.get("splitter_sizes", defaults.splitter_sizes)
        if not isinstance(sizes, list) or not all(isinstance(item, int) for item in sizes):
            sizes = defaults.splitter_sizes
        return cls(
            original=str(data.get("original", "")),
            translation=str(data.get("translation", "")),
            transliteration=str(data.get("transliteration", "")),
            selected_voice=str(data.get("selected_voice", "")),
            translation_visible=bool(data.get("translation_visible", True)),
            splitter_sizes=sizes,
            window_geometry=str(data.get("window_geometry", "")),
            volume=min(1.0, max(0.0, float(data.get("volume", 0.9)))),
            current_source_path=str(data.get("current_source_path", "")),
            audio_file=str(data.get("audio_file", "")),
        )


def load_app_state(path: Path) -> AppState:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return AppState.from_dict(data) if isinstance(data, dict) else AppState()
    except (OSError, ValueError, TypeError):
        return AppState()


def save_app_state(path: Path, state: AppState) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(asdict(state), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)
