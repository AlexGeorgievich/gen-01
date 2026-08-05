import pytest

from gpt01.errors import OperationCancelled
from gpt01.rows import build_translation_rows
from gpt01.structured_translation import sentence_chunks, translate_preserving_layout


class RecordingTranslator:
    def __init__(self):
        self.calls = []

    def translate(self, text, cancelled=None):
        self.calls.append(text)
        return f"<{text}>"


def test_sentence_chunks_prefers_sentence_boundaries():
    assert sentence_chunks("First sentence. Second sentence! Third?", limit=32) == [
        "First sentence. Second sentence!",
        "Third?",
    ]


def test_sentence_chunks_splits_single_oversized_sentence():
    assert sentence_chunks("abcdefghij.", limit=4) == ["abcd", "efgh", "ij."]


def test_translation_preserves_blank_lines_and_line_count():
    translator = RecordingTranslator()

    result = translate_preserving_layout("first\n\nthird\n", translator)

    assert result.text == "<first>\n\n<third>\n"
    assert result.translated_lines == 2
    assert result.translated_chunks == 2
    assert translator.calls == ["first", "third"]


def test_translated_document_keeps_row_mapping_for_playback():
    translator = RecordingTranslator()
    source = "first\n\nthird"

    translated = translate_preserving_layout(source, translator).text
    rows = build_translation_rows(source, translated)

    assert [(row.index, row.translation) for row in rows] == [
        (0, "<first>"),
        (2, "<third>"),
    ]


def test_translation_reports_chunk_progress():
    translator = RecordingTranslator()
    updates = []

    translate_preserving_layout(
        "One. Two.\nThree.",
        translator,
        progress=lambda current, total: updates.append((current, total)),
        limit=6,
    )

    assert updates == [(1, 3), (2, 3), (3, 3)]


def test_adjacent_short_lines_are_translated_in_one_request():
    translator = RecordingTranslator()

    result = translate_preserving_layout("one\ntwo\nthree", translator)

    assert translator.calls == ["one\ntwo\nthree"]
    assert result.text == "<one\ntwo\nthree>"


def test_translation_honours_cancellation_between_chunks():
    translator = RecordingTranslator()

    with pytest.raises(OperationCancelled):
        translate_preserving_layout(
            "one\ntwo",
            translator,
            cancelled=lambda: bool(translator.calls),
            limit=3,
        )

    assert translator.calls == ["one"]
