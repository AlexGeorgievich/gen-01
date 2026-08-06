from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .tts import TtsSettings


@dataclass(slots=True)
class AppState:
    version: int = 3
    original: str = ""
    translation: str = ""
    transcription: str = ""
    selected_voice: str = ""
    transcription_visible: bool = True
    translation_window_visible: bool = True
    splitter_sizes: list[int] = field(default_factory=lambda: [420, 420, 420])
    window_geometry: str = ""
    volume: float = 0.9
    current_source_path: str = ""
    audio_file: str = ""
    tts_rate: int = 0
    tts_pitch: int = 0
    tts_volume: int = 0

    @property
    def tts_settings(self) -> TtsSettings:
        return TtsSettings.normalized(self.tts_rate, self.tts_pitch, self.tts_volume)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppState:
        defaults = cls()
        sizes = data.get("splitter_sizes", defaults.splitter_sizes)
        if not isinstance(sizes, list) or not all(isinstance(item, int) for item in sizes):
            sizes = defaults.splitter_sizes
        tts = TtsSettings.normalized(
            data.get("tts_rate", 0),
            data.get("tts_pitch", 0),
            data.get("tts_volume", 0),
        )
        return cls(
            original=str(data.get("original", "")),
            translation=str(data.get("translation", "")),
            transcription=str(data.get("transcription", data.get("transliteration", ""))),
            selected_voice=str(data.get("selected_voice", "")),
            transcription_visible=bool(
                data.get("transcription_visible", data.get("translation_visible", True))
            ),
            translation_window_visible=bool(
                data.get("translation_window_visible", True)
            ),
            splitter_sizes=sizes,
            window_geometry=str(data.get("window_geometry", "")),
            volume=min(1.0, max(0.0, float(data.get("volume", 0.9)))),
            current_source_path=str(data.get("current_source_path", "")),
            audio_file=str(data.get("audio_file", "")),
            tts_rate=tts.rate,
            tts_pitch=tts.pitch,
            tts_volume=tts.volume,
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
