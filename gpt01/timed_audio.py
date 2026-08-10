from __future__ import annotations

import hashlib
import json
import shutil
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
    source_start: int | None = None
    source_end: int | None = None
    translation_start: int | None = None
    translation_end: int | None = None
    transcription_start: int | None = None
    transcription_end: int | None = None

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
            source_start=_optional_int(data.get("source_start")),
            source_end=_optional_int(data.get("source_end")),
            translation_start=_optional_int(data.get("translation_start")),
            translation_end=_optional_int(data.get("translation_end")),
            transcription_start=_optional_int(data.get("transcription_start")),
            transcription_end=_optional_int(data.get("transcription_end")),
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
    resume_root: Path | None = None,
) -> TimedAudioPackage:
    if not rows:
        raise ValueError("timed audio requires at least one translated row")
    prepare_speech = speech_text or (lambda text: text)
    timed_lines: list[TimedLine] = []
    cursor_ms = 0
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    job_directory: Path | None = None
    checkpoint_path: Path | None = None
    completed: dict[str, int] = {}
    if resume_root is not None:
        fingerprint = timed_audio_fingerprint(rows, language, voice, settings, prepare_speech)
        job_directory = resume_root / fingerprint
        job_directory.mkdir(parents=True, exist_ok=True)
        checkpoint_path = job_directory / "checkpoint.json"
        completed = _load_checkpoint(checkpoint_path, fingerprint)
    try:
        temporary_directory = None
        if job_directory is None:
            temporary_directory = tempfile.TemporaryDirectory(
                prefix="gpt01_timed_parts_"
            )
            part_root = Path(temporary_directory.name)
        else:
            part_root = job_directory
        try:
            with audio_path.open("wb") as combined_audio:
                for current, row in enumerate(rows, start=1):
                    part = part_root / f"{current:06d}.mp3"
                    part_key = str(current)
                    duration_ms = completed.get(part_key, 0)
                    if duration_ms <= 0 or not part.is_file() or part.stat().st_size == 0:
                        part.unlink(missing_ok=True)
                        duration_ms = synthesize(prepare_speech(row.translation), part)
                        if not part.is_file() or part.stat().st_size == 0:
                            raise OSError(f"TTS did not create audio part {current}")
                        if checkpoint_path is not None:
                            completed[part_key] = duration_ms
                            _save_checkpoint(
                                checkpoint_path,
                                fingerprint,
                                completed,
                                len(rows),
                            )
                    combined_audio.write(part.read_bytes())
                    timed_line = timed_line_from_row(row, cursor_ms, duration_ms)
                    timed_lines.append(timed_line)
                    cursor_ms = timed_line.end_ms
                    if progress:
                        progress(current, len(rows))
        finally:
            if temporary_directory is not None:
                temporary_directory.cleanup()
        manifest = TimedAudioManifest.create(
            language,
            voice,
            settings,
            timed_lines,
        )
        save_manifest(manifest_path, manifest)
        save_srt(srt_path, manifest)
        if job_directory is not None:
            shutil.rmtree(job_directory, ignore_errors=True)
        return TimedAudioPackage(audio_path, manifest_path, srt_path, manifest)
    except Exception:
        audio_path.unlink(missing_ok=True)
        manifest_path.unlink(missing_ok=True)
        srt_path.unlink(missing_ok=True)
        raise


def timed_audio_fingerprint(
    rows: list[TranslationRow],
    language: str,
    voice: str,
    settings: TtsSettings,
    speech_text: Callable[[str], str] | None = None,
) -> str:
    prepare_speech = speech_text or (lambda text: text)
    payload = {
        "version": 1,
        "language": language,
        "voice": voice,
        "rate": settings.rate,
        "pitch": settings.pitch,
        "volume": settings.volume,
        "rows": [
            {
                "line": row.index,
                "source": row.source,
                "translation": row.translation,
                "speech": prepare_speech(row.translation),
                "transcription": row.transcription,
            }
            for row in rows
        ],
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_checkpoint(path: Path, fingerprint: str) -> dict[str, int]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") != 1 or data.get("fingerprint") != fingerprint:
            return {}
        completed = data.get("completed", {})
        if not isinstance(completed, dict):
            return {}
        return {
            str(key): int(value)
            for key, value in completed.items()
            if int(value) > 0
        }
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


def _save_checkpoint(
    path: Path,
    fingerprint: str,
    completed: dict[str, int],
    total: int,
) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {
                "version": 1,
                "fingerprint": fingerprint,
                "total": total,
                "completed": completed,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    temporary.replace(path)


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
        source_start=row.source_start,
        source_end=row.source_end,
        translation_start=row.translation_start,
        translation_end=row.translation_end,
        transcription_start=row.transcription_start,
        transcription_end=row.transcription_end,
    )


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
