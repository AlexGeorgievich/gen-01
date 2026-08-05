from __future__ import annotations

from dataclasses import dataclass, field

from .models import TranslationRow


@dataclass(slots=True)
class PlaybackSequence:
    """Pure state machine for sequential row playback."""

    rows: list[TranslationRow] = field(default_factory=list)
    position: int = 0
    generation: int = 0
    active: bool = False

    def start(self, rows: list[TranslationRow]) -> int:
        self.generation += 1
        self.rows = list(rows)
        self.position = 0
        self.active = bool(self.rows)
        return self.generation

    @property
    def current(self) -> TranslationRow | None:
        if not self.active or self.position >= len(self.rows):
            return None
        return self.rows[self.position]

    @property
    def progress(self) -> tuple[int, int]:
        return self.position + 1, len(self.rows)

    def advance(self) -> TranslationRow | None:
        if not self.active:
            return None
        self.position += 1
        if self.position >= len(self.rows):
            self.complete()
            return None
        return self.current

    def matches(self, generation: int) -> bool:
        return self.active and self.generation == generation

    def complete(self) -> None:
        self.active = False
        self.rows = []
        self.position = 0

    def stop(self) -> bool:
        was_active = self.active
        self.generation += 1
        self.complete()
        return was_active
