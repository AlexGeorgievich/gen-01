from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from .errors import OperationCancelled
from .services import TranslationProvider

ProgressCallback = Callable[[int, int], None]
_SENTENCE_PATTERN = re.compile(r"[^.!?…。！？]+(?:[.!?…。！？]+|$)")


@dataclass(frozen=True, slots=True)
class StructuredTranslationResult:
    text: str
    translated_lines: int
    translated_chunks: int


@dataclass(frozen=True, slots=True)
class _TranslationUnit:
    line_index: int
    text: str


def sentence_chunks(text: str, limit: int = 4500) -> list[str]:
    """Split a paragraph at sentence boundaries and keep every chunk under the limit."""
    if limit <= 0:
        raise ValueError("limit must be greater than zero")
    stripped = text.strip()
    if not stripped:
        return []

    sentences = [match.group().strip() for match in _SENTENCE_PATTERN.finditer(stripped)]
    if not sentences:
        sentences = [stripped]

    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        pieces = [sentence[index : index + limit] for index in range(0, len(sentence), limit)]
        for piece in pieces:
            candidate = f"{current} {piece}" if current else piece
            if current and len(candidate) > limit:
                chunks.append(current)
                current = piece
            else:
                current = candidate
    if current:
        chunks.append(current)
    return chunks


def translate_preserving_layout(
    text: str,
    provider: TranslationProvider,
    cancelled: Callable[[], bool] | None = None,
    progress: ProgressCallback | None = None,
    *,
    limit: int = 4500,
) -> StructuredTranslationResult:
    """Translate logical paragraphs while preserving source line positions."""
    source_lines = text.split("\n")
    request_groups: list[list[_TranslationUnit]] = []
    current_group: list[_TranslationUnit] = []
    current_length = 0
    translated_lines = 0

    def flush_group() -> None:
        nonlocal current_group, current_length
        if current_group:
            request_groups.append(current_group)
            current_group = []
            current_length = 0

    for line_index, line in enumerate(source_lines):
        chunks = sentence_chunks(line, limit)
        if not chunks:
            flush_group()
            continue
        translated_lines += 1
        for chunk in chunks:
            added_length = len(chunk) + (1 if current_group else 0)
            if current_group and current_length + added_length > limit:
                flush_group()
                added_length = len(chunk)
            current_group.append(_TranslationUnit(line_index, chunk))
            current_length += added_length
    flush_group()

    total_chunks = sum(len(group) for group in request_groups)
    completed = 0
    translated_parts: list[list[str]] = [[] for _line in source_lines]
    if progress:
        progress(0, total_chunks)

    for group in request_groups:
        if cancelled and cancelled():
            raise OperationCancelled("Перевод отменён.")
        request = "\n".join(unit.text for unit in group)
        response = provider.translate(request, cancelled).strip()
        response_lines = response.splitlines()

        if len(group) > 1 and len(response_lines) != len(group):
            response_lines = []
            for unit in group:
                translated = provider.translate(unit.text, cancelled)
                response_lines.append(" ".join(translated.splitlines()).strip())
        elif len(group) == 1:
            response_lines = [" ".join(response_lines).strip()]

        for unit, translated in zip(group, response_lines, strict=True):
            if translated:
                translated_parts[unit.line_index].append(translated)
            completed += 1
            if progress:
                progress(completed, total_chunks)

    output_lines = [" ".join(parts) for parts in translated_parts]

    return StructuredTranslationResult(
        text="\n".join(output_lines),
        translated_lines=translated_lines,
        translated_chunks=completed,
    )
