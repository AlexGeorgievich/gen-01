from .models import TranslationRow
from .sentences import SentenceSpan, sentence_spans


def rows_between(
    rows: list[TranslationRow],
    first_line: int,
    second_line: int,
) -> list[TranslationRow]:
    """Return rows inside an inclusive line range, independent of marker order."""
    start, end = sorted((first_line, second_line))
    return [row for row in rows if start <= row.index <= end]


def build_translation_rows(
    source: str, translation: str = "", transcription: str = ""
) -> list[TranslationRow]:
    """Build stable row mappings from the three editor documents."""
    source_lines = source.split("\n")
    translation_lines = translation.split("\n")
    transcription_lines = transcription.split("\n")
    rows: list[TranslationRow] = []
    for index, source_line in enumerate(source_lines):
        source_text = source_line.strip()
        if not source_text:
            continue
        rows.append(
            TranslationRow(
                index=index,
                source=source_text,
                translation=(
                    translation_lines[index].strip() if index < len(translation_lines) else ""
                ),
                transcription=(
                    transcription_lines[index].strip()
                    if index < len(transcription_lines)
                    else ""
                ),
            )
        )
    return rows


def build_sentence_translation_rows(
    source: str, translation: str = "", transcription: str = ""
) -> list[TranslationRow]:
    """Build sentence-level playback rows without changing editor layout."""
    source_by_line = _spans_by_line(source)
    translation_by_line = _spans_by_line(translation)
    transcription_by_line = _spans_by_line(transcription)
    rows: list[TranslationRow] = []
    for line_number, source_segments in source_by_line.items():
        translated = translation_by_line.get(line_number, [])
        transcribed = transcription_by_line.get(line_number, [])
        if len(source_segments) == 1:
            rows.append(
                _row_from_spans(
                    line_number,
                    source_segments[0],
                    _combined_span(translated),
                    _combined_span(transcribed),
                )
            )
            continue
        if translated and len(translated) != len(source_segments):
            for position, translated_segment in enumerate(translated):
                rows.append(
                    _row_from_spans(
                        line_number,
                        _proportional_span(
                            source_segments,
                            position,
                            len(translated),
                        ),
                        translated_segment,
                        _proportional_span(
                            transcribed,
                            position,
                            len(translated),
                        ),
                    )
                )
            continue
        for position, source_segment in enumerate(source_segments):
            rows.append(
                _row_from_spans(
                    line_number,
                    source_segment,
                    translated[position] if position < len(translated) else None,
                    transcribed[position]
                    if len(transcribed) == len(source_segments)
                    else _combined_span(transcribed),
                )
            )
    return rows


def _spans_by_line(text: str) -> dict[int, list[SentenceSpan]]:
    result: dict[int, list[SentenceSpan]] = {}
    for span in sentence_spans(text):
        result.setdefault(span.line, []).append(span)
    return result


def _combined_span(spans: list[SentenceSpan]) -> SentenceSpan | None:
    if not spans:
        return None
    return SentenceSpan(
        " ".join(span.text for span in spans),
        spans[0].start,
        spans[-1].end,
        spans[0].line,
    )


def _proportional_span(
    spans: list[SentenceSpan], position: int, total: int
) -> SentenceSpan | None:
    if not spans or total <= 0:
        return None
    start = min(len(spans) - 1, position * len(spans) // total)
    end = min(len(spans), (position + 1) * len(spans) // total)
    if end <= start:
        end = start + 1
    return _combined_span(spans[start:end])


def _row_from_spans(
    line_number: int,
    source: SentenceSpan,
    translation: SentenceSpan | None,
    transcription: SentenceSpan | None,
) -> TranslationRow:
    return TranslationRow(
        index=line_number,
        source=source.text,
        translation=translation.text if translation else "",
        transcription=transcription.text if transcription else "",
        source_start=source.start,
        source_end=source.end,
        translation_start=translation.start if translation else None,
        translation_end=translation.end if translation else None,
        transcription_start=transcription.start if transcription else None,
        transcription_end=transcription.end if transcription else None,
    )
