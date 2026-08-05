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
    chunk_groups = [sentence_chunks(line, limit) for line in source_lines]
    total_chunks = sum(len(group) for group in chunk_groups)
    completed = 0
    translated_lines = 0
    output_lines: list[str] = []

    for chunks in chunk_groups:
        if not chunks:
            output_lines.append("")
            continue
        translated_parts: list[str] = []
        for chunk in chunks:
            if cancelled and cancelled():
                raise OperationCancelled("Перевод отменён.")
            translated_parts.append(provider.translate(chunk, cancelled).strip())
            completed += 1
            if progress:
                progress(completed, total_chunks)
        output_lines.append(" ".join(part for part in translated_parts if part))
        translated_lines += 1

    return StructuredTranslationResult(
        text="\n".join(output_lines),
        translated_lines=translated_lines,
        translated_chunks=completed,
    )
