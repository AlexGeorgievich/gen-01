from __future__ import annotations

import re
from dataclasses import dataclass

_CLOSING_MARKS = '"\'»”’)]}'
_KNOWN_ABBREVIATIONS = {
    "г.",
    "гг.",
    "им.",
    "кв.",
    "рис.",
    "руб.",
    "см.",
    "стр.",
    "т.е.",
    "т.д.",
    "т.п.",
    "ул.",
    "e.g.",
    "etc.",
    "i.e.",
    "mr.",
    "mrs.",
    "ms.",
    "dr.",
    "prof.",
    "sr.",
    "jr.",
    "vs.",
}


@dataclass(frozen=True, slots=True)
class SentenceSpan:
    """A spoken sentence and its half-open character range in a document."""

    text: str
    start: int
    end: int
    line: int


def sentence_spans(text: str) -> list[SentenceSpan]:
    """Split document lines into speakable sentences while preserving offsets."""
    spans: list[SentenceSpan] = []
    offset = 0
    for line_number, line in enumerate(text.split("\n")):
        spans.extend(_line_sentence_spans(line, offset, line_number))
        offset += len(line) + 1
    return spans


def _line_sentence_spans(
    line: str,
    document_offset: int,
    line_number: int,
) -> list[SentenceSpan]:
    spans: list[SentenceSpan] = []
    start = _skip_space(line, 0)
    index = start
    while index < len(line):
        if line[index] not in ".!?…。！？":
            index += 1
            continue
        punctuation_end = index + 1
        while punctuation_end < len(line) and line[punctuation_end] in ".!?…。！？":
            punctuation_end += 1
        end = punctuation_end
        while end < len(line) and line[end] in _CLOSING_MARKS:
            end += 1
        if _is_boundary(line, index, end):
            _append_span(spans, line, start, end, document_offset, line_number)
            start = _skip_space(line, end)
            index = start
            continue
        index = punctuation_end
    _append_span(spans, line, start, len(line), document_offset, line_number)
    return spans


def _is_boundary(line: str, punctuation: int, end: int) -> bool:
    mark = line[punctuation]
    if mark in "!?…。！？" or line[punctuation:end].count(".") > 1:
        return True
    if _period_belongs_to_number_or_address(line, punctuation):
        return False
    prefix = line[: punctuation + 1].lower()
    token = re.search(r"[^\s]+$", prefix)
    if token and token.group() in _KNOWN_ABBREVIATIONS:
        return False
    if re.search(r"(?:\b[^\W\d_]\.){2,}$", prefix, flags=re.UNICODE):
        return False
    word = re.search(r"([^\W\d_]+)\.$", prefix, flags=re.UNICODE)
    if word and len(word.group(1)) == 1 and _next_nonspace(line, end):
        return False
    return True


def _period_belongs_to_number_or_address(line: str, index: int) -> bool:
    if index <= 0 or index + 1 >= len(line):
        return False
    before, after = line[index - 1], line[index + 1]
    if before.isdigit() and after.isdigit():
        return True
    return before.isalnum() and after.isalpha()


def _next_nonspace(line: str, start: int) -> str:
    index = _skip_space(line, start)
    return line[index] if index < len(line) else ""


def _skip_space(text: str, start: int) -> int:
    while start < len(text) and text[start].isspace():
        start += 1
    return start


def _append_span(
    result: list[SentenceSpan],
    line: str,
    start: int,
    end: int,
    document_offset: int,
    line_number: int,
) -> None:
    while end > start and line[end - 1].isspace():
        end -= 1
    if end <= start:
        return
    result.append(
        SentenceSpan(
            line[start:end],
            document_offset + start,
            document_offset + end,
            line_number,
        )
    )
