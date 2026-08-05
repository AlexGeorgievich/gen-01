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


class ExportLayout(StrEnum):
    SEQUENTIAL = "sequential"
    THREE_COLUMNS = "three_columns"


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


def render_columns(
    document: Document,
    kind: ExportKind,
    block_size: int = 10,
) -> str:
    if block_size <= 0:
        raise ValueError("block_size must be greater than zero")

    def lines(text: str) -> list[str]:
        values = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        while values and not values[-1]:
            values.pop()
        return values

    if kind == ExportKind.TRANSLATION:
        definitions = [("Перевод", document.translation)]
    elif kind == ExportKind.BILINGUAL:
        definitions = [
            ("Исходный текст", document.original),
            ("Перевод", document.translation),
        ]
    else:
        definitions = [
            ("Исходный текст", document.original),
            ("Перевод", document.translation),
            ("Транскрипция", document.transcription),
        ]
    headers = tuple(header for header, _text in definitions)
    columns = [lines(text) for _header, text in definitions]
    row_count = max((len(column) for column in columns), default=0)
    blocks: list[str] = []
    for start in range(0, row_count, block_size):
        rows = ["\t".join(headers)]
        for row_index in range(start, min(start + block_size, row_count)):
            cells = [
                column[row_index].replace("\t", "    ") if row_index < len(column) else ""
                for column in columns
            ]
            rows.append("\t".join(cells))
        blocks.append("\n".join(rows))
    return "\n\n".join(blocks) + "\n" if blocks else "\t".join(headers) + "\n"


def render_three_columns(document: Document, block_size: int = 10) -> str:
    """Backward-compatible full-document column renderer."""
    return render_columns(document, ExportKind.FULL, block_size)


def render_export(
    document: Document,
    kind: ExportKind,
    layout: ExportLayout = ExportLayout.SEQUENTIAL,
) -> str:
    if layout == ExportLayout.THREE_COLUMNS:
        return render_columns(document, kind)
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
    *,
    layout: ExportLayout = ExportLayout.SEQUENTIAL,
) -> ExportResult:
    if kind == ExportKind.LEARNING_KIT and (
        audio_source is None or not audio_source.is_file()
    ):
        raise StorageError("Для учебного комплекта сначала создайте аудио.")

    try:
        path.write_text(
            render_export(document, kind, layout),
            encoding="utf-8",
            newline="\n",
        )
        audio_target: Path | None = None
        if kind == ExportKind.LEARNING_KIT and audio_source:
            audio_target = path.with_suffix(".mp3")
            if audio_source.resolve() != audio_target.resolve():
                shutil.copyfile(audio_source, audio_target)
        return ExportResult(text_path=path, audio_path=audio_target)
    except OSError as exc:
        raise StorageError(f"Не удалось экспортировать документ: {exc}") from exc
