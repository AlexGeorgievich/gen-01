from __future__ import annotations

import shutil
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .errors import StorageError
from .models import Document
from .storage import ORIGINAL_MARKER, TRANSLATION_MARKER, serialize_document


class ExportKind(StrEnum):
    FULL = "full"
    TRANSLATION = "translation"
    BILINGUAL = "bilingual"
    LEARNING_KIT = "learning_kit"


EXPORT_LABELS = {
    ExportKind.FULL: "Полный документ: оригинал + перевод + транскрипция",
    ExportKind.TRANSLATION: "Только перевод",
    ExportKind.BILINGUAL: "Двуязычный документ: оригинал + перевод",
    ExportKind.LEARNING_KIT: "Учебный комплект: полный TXT + MP3",
}


@dataclass(frozen=True, slots=True)
class ExportResult:
    text_path: Path
    audio_path: Path | None = None


def render_export(document: Document, kind: ExportKind) -> str:
    if kind == ExportKind.TRANSLATION:
        return f"{document.translation.rstrip()}\n"
    if kind == ExportKind.BILINGUAL:
        return (
            f"{ORIGINAL_MARKER}\n{document.original.rstrip()}\n\n"
            f"{TRANSLATION_MARKER}\n{document.translation.rstrip()}\n"
        )
    return serialize_document(document)


def export_document(
    path: Path,
    document: Document,
    kind: ExportKind,
    audio_source: Path | None = None,
) -> ExportResult:
    if kind == ExportKind.LEARNING_KIT and (
        audio_source is None or not audio_source.is_file()
    ):
        raise StorageError("Для учебного комплекта сначала создайте аудио.")

    try:
        path.write_text(render_export(document, kind), encoding="utf-8", newline="\n")
        audio_target: Path | None = None
        if kind == ExportKind.LEARNING_KIT and audio_source:
            audio_target = path.with_suffix(".mp3")
            if audio_source.resolve() != audio_target.resolve():
                shutil.copyfile(audio_source, audio_target)
        return ExportResult(text_path=path, audio_path=audio_target)
    except OSError as exc:
        raise StorageError(f"Не удалось экспортировать документ: {exc}") from exc
