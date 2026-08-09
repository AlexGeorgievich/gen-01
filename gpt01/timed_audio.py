from __future__ import annotations

import json
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .models import TranslationRow
from .tts import TtsSettings

SynthesizeTimed = Callable[[str, Path], int]
ProgressCallback = Callable[[int, int], None]


@dataclass(frozen=True, slots=True)
class TimedLine:
    line: int
    start_ms: int
    end_ms: int
    source: str
    translation: str
    transcription: str

    @classmethod
    def from_dict(cls, data: object) -> TimedLine | None:
        if not isinstance(data, dict):
            return None
        try:
            line = int(data["line"])
            start_ms = int(data["start_ms"])
            end_ms = int(data["end_ms"])
        except (KeyError, TypeError, ValueError):
            return None
        if line < 0 or start_ms < 0 or end_ms <= start_ms:
            return None
        return cls(
            line=line,
            start_ms=start_ms,
            end_ms=end_ms,
            source=str(data.get("source", "")),
            translation=str(data.get("translation", "")),
            transcription=str(data.get("transcription", "")),
        )


@dataclass(frozen=True, slots=True)
class TimedAudioManifest:
    language: str
    voice: str
    rate: int
    pitch: int
    volume: int
    total_duration_ms: int
    lines: tuple[TimedLine, ...]
    version: int = 1

    @classmethod
    def create(
        cls,
        language: str,
        voice: str,
        settings: TtsSettings,
        lines: list[TimedLine],
    ) -> TimedAudioManifest:
        return cls(
            language=language,
            voice=voice,
            rate=settings.rate,
            pitch=settings.pitch,
            volume=settings.volume,
            total_duration_ms=lines[-1].end_ms if lines else 0,
            lines=tuple(lines),
        )

    @classmethod
    def from_dict(cls, data: object) -> TimedAudioManifest | None:
        if not isinstance(data, dict):
            return None
        parsed_lines = tuple(
            line
            for item in data.get("lines", [])
            if (line := TimedLine.from_dict(item)) is not None
        )
        try:
            manifest = cls(
                version=int(data.get("version", 1)),
                language=str(data["language"]),
                voice=str(data["voice"]),
                rate=int(data.get("rate", 0)),
                pitch=int(data.get("pitch", 0)),
                volume=int(data.get("volume", 0)),
                total_duration_ms=int(data.get("total_duration_ms", 0)),
                lines=parsed_lines,
            )
        except (KeyError, TypeError, ValueError):
            return None
        if manifest.version != 1 or not manifest.lines:
            return None
        if manifest.total_duration_ms != manifest.lines[-1].end_ms:
            return None
        return manifest

    def line_at(self, position_ms: int) -> TimedLine | None:
        for line in self.lines:
            if line.start_ms <= position_ms < line.end_ms:
                return line
        if self.lines and position_ms >= self.lines[-1].end_ms:
            return self.lines[-1]
        return None

    def interval(self, first_line: int, second_line: int) -> tuple[int, int] | None:
        start_line, end_line = sorted((first_line, second_line))
        selected = [
            line for line in self.lines if start_line <= line.line <= end_line
        ]
        if not selected:
            return None
        return selected[0].start_ms, selected[-1].end_ms


@dataclass(frozen=True, slots=True)
class TimedAudioPackage:
    audio_path: Path
    manifest_path: Path
    srt_path: Path
    manifest: TimedAudioManifest


def build_timed_audio_package(
    rows: list[TranslationRow],
    audio_path: Path,
    manifest_path: Path,
    srt_path: Path,
    language: str,
    voice: str,
    settings: TtsSettings,
    synthesize: SynthesizeTimed,
    *,
    speech_text: Callable[[str], str] | None = None,
    progress: ProgressCallback | None = None,
) -> TimedAudioPackage:
    if not rows:
        raise ValueError("timed audio requires at least one translated row")
    prepare_speech = speech_text or (lambda text: text)
    timed_lines: list[TimedLine] = []
    cursor_ms = 0
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="gpt01_timed_parts_") as directory:
            part_root = Path(directory)
            with audio_path.open("wb") as combined_audio:
                for current, row in enumerate(rows, start=1):
                    part = part_root / f"{current:06d}.mp3"
                    duration_ms = synthesize(prepare_speech(row.translation), part)
                    combined_audio.write(part.read_bytes())
                    timed_line = timed_line_from_row(row, cursor_ms, duration_ms)
                    timed_lines.append(timed_line)
                    cursor_ms = timed_line.end_ms
                    if progress:
                        progress(current, len(rows))
        manifest = TimedAudioManifest.create(
            language,
            voice,
            settings,
            timed_lines,
        )
        save_manifest(manifest_path, manifest)
        save_srt(srt_path, manifest)
        return TimedAudioPackage(audio_path, manifest_path, srt_path, manifest)
    except Exception:
        audio_path.unlink(missing_ok=True)
        manifest_path.unlink(missing_ok=True)
        srt_path.unlink(missing_ok=True)
        raise


def save_manifest(path: Path, manifest: TimedAudioManifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(asdict(manifest), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def load_manifest(path: Path) -> TimedAudioManifest | None:
    try:
        return TimedAudioManifest.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return None


def format_srt_timestamp(milliseconds: int) -> str:
    value = max(0, milliseconds)
    hours, remainder = divmod(value, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def render_srt(manifest: TimedAudioManifest) -> str:
    cues = []
    for index, line in enumerate(manifest.lines, start=1):
        cues.append(
            "\n".join(
                (
                    str(index),
                    f"{format_srt_timestamp(line.start_ms)} --> "
                    f"{format_srt_timestamp(line.end_ms)}",
                    line.translation,
                )
            )
        )
    return "\n\n".join(cues) + ("\n" if cues else "")


def save_srt(path: Path, manifest: TimedAudioManifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(render_srt(manifest), encoding="utf-8", newline="\n")
    temporary.replace(path)


def manifest_payload(manifest: TimedAudioManifest) -> dict[str, Any]:
    """Return a JSON-ready representation for tests and external integrations."""
    return asdict(manifest)


def timed_line_from_row(
    row: TranslationRow,
    start_ms: int,
    duration_ms: int,
) -> TimedLine:
    return TimedLine(
        line=row.index,
        start_ms=start_ms,
        end_ms=start_ms + max(1, duration_ms),
        source=row.source,
        translation=row.translation,
        transcription=row.transcription,
    )
