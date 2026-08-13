from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from .errors import StorageError
from .models import Document
from .mp3 import mp3_duration_ms
from .rows import build_sentence_translation_rows
from .storage import save_document
from .timed_audio import TimedAudioManifest, load_manifest


@dataclass(frozen=True, slots=True)
class OfflinePackage:
    language: str
    stem: str
    base_path: Path
    document: Document
    manifest: TimedAudioManifest

    @property
    def text_path(self) -> Path:
        return self.base_path.with_suffix(".txt")

    @property
    def document_path(self) -> Path:
        return self.base_path.with_suffix(".document.json")

    @property
    def audio_path(self) -> Path:
        return self.base_path.with_suffix(".mp3")

    @property
    def manifest_path(self) -> Path:
        return self.base_path.with_suffix(".json")

    @property
    def srt_path(self) -> Path:
        return self.base_path.with_suffix(".srt")


@dataclass(frozen=True, slots=True)
class PackageHistoryEntry:
    language: str
    name: str
    audio_path: str
    last_used: str


def save_package_document(
    audio_path: Path,
    language: str,
    document: Document,
) -> None:
    save_document(audio_path.with_suffix(".txt"), document)
    target = audio_path.with_suffix(".document.json")
    temporary = target.with_suffix(f"{target.suffix}.tmp")
    temporary.write_text(
        json.dumps(
            {
                "version": 1,
                "language": language,
                "original": document.original,
                "translation": document.translation,
                "transcription": document.transcription,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    temporary.replace(target)


def discover_packages(language_directory: Path, language: str) -> list[OfflinePackage]:
    packages: list[OfflinePackage] = []
    if not language_directory.is_dir():
        return packages
    for audio_path in sorted(language_directory.glob("*.mp3"), key=lambda path: path.name.lower()):
        try:
            packages.append(load_offline_package(audio_path, language))
        except StorageError:
            continue
    return packages


def load_offline_package(audio_path: Path, language: str) -> OfflinePackage:
    base_path = audio_path.with_suffix("")
    paths = {
        "TXT": base_path.with_suffix(".txt"),
        "document.json": base_path.with_suffix(".document.json"),
        "MP3": base_path.with_suffix(".mp3"),
        "JSON": base_path.with_suffix(".json"),
        "SRT": base_path.with_suffix(".srt"),
    }
    missing = [label for label, path in paths.items() if not path.is_file()]
    if missing:
        raise StorageError("Неполный автономный пакет. Отсутствует: " + ", ".join(missing))
    if paths["MP3"].stat().st_size <= 0:
        raise StorageError("MP3-файл автономного пакета пуст.")
    try:
        payload = json.loads(paths["document.json"].read_text(encoding="utf-8"))
        if payload.get("version") != 1 or payload.get("language") != language:
            raise StorageError("Документ пакета не соответствует выбранному языку.")
        document = Document(
            str(payload.get("original", "")),
            str(payload.get("translation", "")),
            str(payload.get("transcription", "")),
        )
    except StorageError:
        raise
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        raise StorageError(f"Не удалось прочитать документ пакета: {exc}") from exc
    manifest = load_manifest(paths["JSON"])
    if manifest is None:
        raise StorageError("JSON временных меток повреждён или пуст.")
    if manifest.language != language:
        raise StorageError("JSON временных меток не соответствует выбранному языку.")
    actual_duration = mp3_duration_ms(paths["MP3"])
    if actual_duration is not None and abs(actual_duration - manifest.total_duration_ms) > 1000:
        raise StorageError(
            "MP3 и JSON временных меток рассинхронизированы. "
            "Сформируйте аудиопакет повторно."
        )
    expected_rows = build_sentence_translation_rows(
        document.original, document.translation, document.transcription
    )
    if len(manifest.lines) != len(expected_rows):
        raise StorageError(
            "Пакет не содержит временные метки для всего документа."
        )
    if any(
        timed.line != row.index
        or timed.source != row.source
        or timed.translation != row.translation
        or timed.transcription != row.transcription
        or (
            timed.source_start is not None
            and timed.source_start != row.source_start
        )
        or (timed.source_end is not None and timed.source_end != row.source_end)
        for timed, row in zip(manifest.lines, expected_rows, strict=True)
    ):
        raise StorageError(
            "Текст документа не соответствует временным меткам пакета. "
            "Сформируйте пакет повторно."
        )
    normalized_lines = tuple(
        replace(
            timed,
            source_start=(
                timed.source_start
                if timed.source_start is not None
                else row.source_start
            ),
            source_end=(
                timed.source_end if timed.source_end is not None else row.source_end
            ),
            translation_start=(
                timed.translation_start
                if timed.translation_start is not None
                else row.translation_start
            ),
            translation_end=(
                timed.translation_end
                if timed.translation_end is not None
                else row.translation_end
            ),
            transcription_start=(
                timed.transcription_start
                if timed.transcription_start is not None
                else row.transcription_start
            ),
            transcription_end=(
                timed.transcription_end
                if timed.transcription_end is not None
                else row.transcription_end
            ),
        )
        for timed, row in zip(manifest.lines, expected_rows, strict=True)
    )
    if normalized_lines != manifest.lines:
        manifest = replace(manifest, lines=normalized_lines)
    return OfflinePackage(language, audio_path.stem, base_path, document, manifest)


def load_package_history(path: Path, limit: int = 10) -> list[PackageHistoryEntry]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        entries = []
        for item in payload.get("packages", []):
            if not isinstance(item, dict):
                continue
            entries.append(
                PackageHistoryEntry(
                    language=str(item.get("language", "")),
                    name=str(item.get("name", "")),
                    audio_path=str(item.get("audio_path", "")),
                    last_used=str(item.get("last_used", "")),
                )
            )
        return [entry for entry in entries if entry.audio_path][:limit]
    except (OSError, ValueError, TypeError, AttributeError):
        return []


def touch_package_history(
    path: Path,
    language: str,
    audio_path: Path,
    limit: int = 10,
) -> None:
    resolved = str(audio_path.resolve())
    entries = [
        entry
        for entry in load_package_history(path, limit)
        if str(Path(entry.audio_path).resolve()) != resolved
    ]
    entries.insert(
        0,
        PackageHistoryEntry(
            language,
            audio_path.stem,
            resolved,
            datetime.now(UTC).astimezone().isoformat(timespec="seconds"),
        ),
    )
    save_package_history(path, entries[:limit])


def save_package_history(path: Path, entries: list[PackageHistoryEntry]) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(
            {"version": 1, "packages": [asdict(entry) for entry in entries[:10]]},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    temporary.replace(path)
