from __future__ import annotations

from dataclasses import dataclass


def _bounded_int(value: object, minimum: int, maximum: int, default: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return min(maximum, max(minimum, parsed))


@dataclass(frozen=True, slots=True)
class TtsSettings:
    rate: int = 0
    pitch: int = 0
    volume: int = 0

    @classmethod
    def normalized(
        cls,
        rate: object = 0,
        pitch: object = 0,
        volume: object = 0,
    ) -> TtsSettings:
        return cls(
            rate=_bounded_int(rate, -100, 100),
            pitch=_bounded_int(pitch, -100, 100),
            volume=_bounded_int(volume, -100, 100),
        )

    def edge_options(self) -> dict[str, str]:
        return {
            "rate": f"{self.rate:+d}%",
            "pitch": f"{self.pitch:+d}Hz",
            "volume": f"{self.volume:+d}%",
        }
