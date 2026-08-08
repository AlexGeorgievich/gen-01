from __future__ import annotations

import re
import shutil
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .errors import StorageError
from .languages import LanguageProfile
from .models import Document
from .storage import ORIGINAL_MARKER, TRANSLATION_MARKER, serialize_document

_SENTENCE_END = re.compile(r"[.!?…。！？][\"'»”\)\]]*\s*$")
# Keep every rendered table at 79 characters. Text editors commonly wrap at
# 80 columns; a wider logical row visually moves later columns under the first
# one even though the saved delimiters are correct.
_COLUMN_WIDTHS = {1: 75, 2: 36, 3: 23}


class ExportKind(StrEnum):
    FULL = "full"
    SOURCE = "source"
    TRANSLATION = "translation"
    BILINGUAL = "bilingual"
    LEARNING_KIT = "learning_kit"


class ExportLayout(StrEnum):
    SEQUENTIAL = "sequential"
    THREE_COLUMNS = "three_columns"


EXPORT_LABELS = {
    ExportKind.FULL: "Полный документ: оригинал + перевод + транскрипция",
    ExportKind.SOURCE: "Сохранить только текст",
    ExportKind.TRANSLATION: "Только перевод",
    ExportKind.BILINGUAL: "Двуязычный документ: оригинал + перевод/транскрипция",
    ExportKind.LEARNING_KIT: "Учебный комплект: полный TXT + MP3",
}


@dataclass(frozen=True, slots=True)
class ExportResult:
    text_path: Path
    audio_path: Path | None = None


def display_width(text: str) -> int:
    width = 0
    for character in text:
        if unicodedata.combining(character):
            continue
        width += 2 if unicodedata.east_asian_width(character) in {"W", "F"} else 1
    return width


def _split_visual(text: str, width: int) -> list[str]:
    parts: list[str] = []
    current = ""
    current_width = 0
    for character in text:
        character_width = display_width(character)
        if current and current_width + character_width > width:
            parts.append(current)
            current = ""
            current_width = 0
        current += character
        current_width += character_width
    if current or not parts:
        parts.append(current)
    return parts


def _wrap_cell(text: str, width: int) -> list[str]:
    words = text.replace("\t", "    ").split()
    if not words:
        return [""]
    lines: list[str] = []
    current = ""
    for word in words:
        if display_width(word) > width:
            if current:
                lines.append(current)
                current = ""
            pieces = _split_visual(word, width)
            lines.extend(pieces[:-1])
            current = pieces[-1]
            continue
        candidate = f"{current} {word}" if current else word
        if current and display_width(candidate) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


def _pad_cell(text: str, width: int) -> str:
    return text + " " * max(0, width - display_width(text))


def _table_row(cells: list[str], widths: list[int]) -> str:
    return "|" + "|".join(
        f" {_pad_cell(cell, width)} " for cell, width in zip(cells, widths, strict=True)
    ) + "|"


def _table_border(widths: list[int]) -> str:
    return "+" + "+".join("-" * (width + 2) for width in widths) + "+"


def render_columns(
    document: Document,
    kind: ExportKind,
    block_size: int = 10,
    *,
    profile: LanguageProfile | None = None,
) -> str:
    if block_size <= 0:
        raise ValueError("block_size must be greater than zero")
    if kind == ExportKind.SOURCE:
        return document.original.replace("\r\n", "\n").replace("\r", "\n")

    def lines(text: str) -> list[str]:
        values = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        while values and not values[-1]:
            values.pop()
        return values

    if kind == ExportKind.TRANSLATION:
        definitions = [("Перевод", document.translation)]
    elif kind == ExportKind.BILINGUAL:
        secondary_header = "Перевод"
        secondary_text = document.translation
        if profile and profile.transcription_mode == "pinyin":
            secondary_header = "Пиньинь"
            secondary_text = document.transcription
        elif profile and profile.transcription_mode == "romaji":
            secondary_header = "Ромадзи"
            secondary_text = document.transcription
        definitions = [
            ("Исходный текст", document.original),
            (secondary_header, secondary_text),
        ]
    else:
        definitions = [
            ("Исходный текст", document.original),
            ("Перевод", document.translation),
            ("Транскрипция", document.transcription),
        ]
    headers = [header for header, _text in definitions]
    columns = [lines(text) for _header, text in definitions]
    widths = [_COLUMN_WIDTHS[len(columns)]] * len(columns)
    border = _table_border(widths)
    row_count = max((len(column) for column in columns), default=0)
    blocks: list[str] = []
    start = 0
    while start < row_count:
        end = min(start + block_size, row_count)
        while end < row_count:
            boundary_cells = [
                column[end - 1] if end - 1 < len(column) else "" for column in columns
            ]
            boundary_text = next((cell.strip() for cell in boundary_cells if cell.strip()), "")
            if not boundary_text or _SENTENCE_END.search(boundary_text):
                break
            end += 1

        rows = [border]
        if not blocks:
            rows.extend([_table_row(headers, widths), border])
        for row_index in range(start, end):
            cells = [
                column[row_index] if row_index < len(column) else ""
                for column in columns
            ]
            wrapped_cells = [
                _wrap_cell(cell, width)
                for cell, width in zip(cells, widths, strict=True)
            ]
            physical_height = max(len(cell_lines) for cell_lines in wrapped_cells)
            for physical_index in range(physical_height):
                physical_cells = [
                    cell_lines[physical_index] if physical_index < len(cell_lines) else ""
                    for cell_lines in wrapped_cells
                ]
                rows.append(_table_row(physical_cells, widths))
            rows.append(border)
        blocks.append("\n".join(rows))
        start = end
    if blocks:
        return "\n\n".join(blocks) + "\n"
    return "\n".join((border, _table_row(headers, widths), border)) + "\n"


def render_three_columns(document: Document, block_size: int = 10) -> str:
    """Backward-compatible full-document column renderer."""
    return render_columns(document, ExportKind.FULL, block_size)


def render_export(
    document: Document,
    kind: ExportKind,
    layout: ExportLayout = ExportLayout.SEQUENTIAL,
    *,
    profile: LanguageProfile | None = None,
) -> str:
    if kind == ExportKind.SOURCE:
        return document.original.replace("\r\n", "\n").replace("\r", "\n")
    if layout == ExportLayout.THREE_COLUMNS:
        return render_columns(document, kind, profile=profile)
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
    profile: LanguageProfile | None = None,
) -> ExportResult:
    if kind == ExportKind.LEARNING_KIT and (
        audio_source is None or not audio_source.is_file()
    ):
        raise StorageError("Для учебного комплекта сначала создайте аудио.")

    try:
        path.write_text(
            render_export(document, kind, layout, profile=profile),
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
