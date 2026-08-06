import pytest

from gpt01.errors import StorageError
from gpt01.exporting import (
    ExportKind,
    ExportLayout,
    export_document,
    render_columns,
    render_export,
    render_three_columns,
)
from gpt01.models import Document
from gpt01.storage import load_document

DOCUMENT = Document("source", "translation", "transcription")


def test_translation_only_export_contains_no_markers():
    assert render_export(DOCUMENT, ExportKind.TRANSLATION) == "translation\n"


def test_bilingual_export_omits_transcription():
    rendered = render_export(DOCUMENT, ExportKind.BILINGUAL)

    assert "source" in rendered
    assert "translation" in rendered
    assert "transcription" not in rendered


def test_full_export_round_trip(tmp_path):
    target = tmp_path / "lesson.txt"

    export_document(target, DOCUMENT, ExportKind.FULL)

    assert load_document(target) == DOCUMENT


def test_learning_kit_copies_audio_with_matching_stem(tmp_path):
    audio = tmp_path / "source.mp3"
    audio.write_bytes(b"mp3")
    target = tmp_path / "lesson.txt"

    result = export_document(target, DOCUMENT, ExportKind.LEARNING_KIT, audio)

    assert result.audio_path == tmp_path / "lesson.mp3"
    assert result.audio_path.read_bytes() == b"mp3"
    assert load_document(result.text_path) == DOCUMENT


def test_learning_kit_requires_audio(tmp_path):
    with pytest.raises(StorageError, match="создайте аудио"):
        export_document(tmp_path / "lesson.txt", DOCUMENT, ExportKind.LEARNING_KIT)


def test_three_column_export_has_titles_and_synchronised_rows():
    document = Document("one\ntwo", "un\ndeux", "un\ndeux")

    rendered = render_three_columns(document)

    assert rendered.splitlines() == [
        "Исходный текст\tПеревод\tТранскрипция",
        "one\tun\tun",
        "two\tdeux\tdeux",
    ]


def test_three_column_export_has_one_title_and_breaks_after_ten_complete_sentences():
    values = "\n".join(f"line {index}." for index in range(21))

    rendered = render_three_columns(Document(values, values, values))

    assert rendered.count("Исходный текст\tПеревод\tТранскрипция") == 1
    assert "line 9.\tline 9.\tline 9.\n\nline 10." in rendered
    assert "line 19.\tline 19.\tline 19.\n\nline 20." in rendered


def test_column_break_moves_to_end_of_sentence():
    lines = [f"Sentence {index}." for index in range(9)]
    lines.extend(["Long sentence", "continues", "ends here.", "Next sentence."])
    values = "\n".join(lines)

    rendered = render_three_columns(Document(values, values, values))

    assert "Long sentence\tLong sentence\tLong sentence\n\n" not in rendered
    assert "continues\tcontinues\tcontinues\n\n" not in rendered
    assert "ends here.\tends here.\tends here.\n\nNext sentence." in rendered


def test_three_column_export_preserves_missing_parallel_lines():
    rendered = render_three_columns(Document("one\ntwo", "un", ""))

    assert "one\tun\t" in rendered
    assert "two\t\t" in rendered


def test_learning_kit_supports_three_column_layout(tmp_path):
    audio = tmp_path / "source.mp3"
    audio.write_bytes(b"mp3")
    target = tmp_path / "lesson.txt"

    export_document(
        target,
        DOCUMENT,
        ExportKind.LEARNING_KIT,
        audio,
        layout=ExportLayout.THREE_COLUMNS,
    )

    assert target.read_text(encoding="utf-8").startswith(
        "Исходный текст\tПеревод\tТранскрипция"
    )


def test_translation_only_supports_column_layout_and_ten_row_blocks():
    values = "\n".join(f"translation {index}." for index in range(11))

    rendered = render_columns(Document(translation=values), ExportKind.TRANSLATION)

    assert rendered.count("Перевод") == 1
    assert "translation 9.\n\ntranslation 10." in rendered
    assert "Исходный текст" not in rendered


def test_bilingual_supports_two_column_layout():
    rendered = render_export(
        Document("one\ntwo", "un\ndeux", "ignored"),
        ExportKind.BILINGUAL,
        ExportLayout.THREE_COLUMNS,
    )

    assert rendered.splitlines() == [
        "Исходный текст\tПеревод",
        "one\tun",
        "two\tdeux",
    ]
