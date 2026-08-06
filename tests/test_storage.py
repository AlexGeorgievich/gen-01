import zipfile

import pytest

from gpt01.errors import StorageError
from gpt01.models import Document, SubtitleCue
from gpt01.storage import (
    LEGACY_TRANSLATION_MARKER,
    ORIGINAL_MARKER,
    TRANSCRIPTION_MARKER,
    TRANSLATION_MARKER,
    decode_text,
    load_document,
    parse_document,
    parse_srt,
    save_document,
    serialize_document,
    serialize_srt,
)


def test_decode_utf8_bom():
    assert decode_text(b"\xef\xbb\xbfhello") == "hello"


def test_decode_cp1251():
    assert decode_text("привет".encode("cp1251")) == "привет"


def test_plain_text_becomes_original():
    assert parse_document("plain") == Document(original="plain")


def test_parse_current_format():
    text = f"{ORIGINAL_MARKER}\nsource\n{TRANSLATION_MARKER}\ntranslation"
    assert parse_document(text) == Document("source", "translation")


def test_parse_legacy_format():
    text = f"{ORIGINAL_MARKER}\nsource\n{LEGACY_TRANSLATION_MARKER}\ntranslation"
    assert parse_document(text) == Document("source", "translation")


def test_document_round_trip():
    document = Document("source\n", "translation\n", "pinyin\n")
    restored = parse_document(serialize_document(document))
    assert restored == Document("source", "translation", "pinyin")


def test_serialized_document_has_trailing_newline():
    assert serialize_document(Document("a", "b")).endswith("\n")


def test_parse_three_column_format():
    text = (
        f"{ORIGINAL_MARKER}\nsource\n{TRANSLATION_MARKER}\ntranslation\n"
        f"{TRANSCRIPTION_MARKER}\npinyin"
    )
    assert parse_document(text) == Document("source", "translation", "pinyin")


def test_parse_srt_keeps_one_text_line_per_cue():
    text = (
        "1\r\n00:00:01,000 --> 00:00:03,000\r\n<i>Hello</i> world\r\n\r\n"
        "2\r\n00:00:04,000 --> 00:00:06,000\r\nSecond\r\nline"
    )

    document = parse_srt(text)

    assert document.original == "Hello world\nSecond line"
    assert document.subtitles == (
        SubtitleCue(
            "1",
            "00:00:01,000 --> 00:00:03,000",
            ("<i>Hello</i> world",),
            "Hello world",
        ),
        SubtitleCue(
            "2",
            "00:00:04,000 --> 00:00:06,000",
            ("Second", "line"),
            "Second line",
        ),
    )


def test_srt_round_trip_preserves_indices_timings_settings_and_outer_markup():
    source = (
        "7\n00:00:01,250 --> 00:00:03,500 position:50% align:middle\n"
        "<i>Hello\nworld</i>\n\n"
        "9\n00:00:04.000 --> 00:00:06.000\nSecond cue"
    )
    document = parse_srt(source)
    document.translation = "Bonjour le monde\nDeuxième réplique"

    rendered = serialize_srt(document)

    assert rendered == (
        "7\n00:00:01,250 --> 00:00:03,500 position:50% align:middle\n"
        "<i>Bonjour le monde</i>\n\n"
        "9\n00:00:04.000 --> 00:00:06.000\nDeuxième réplique\n"
    )


def test_srt_export_rejects_translation_with_different_cue_count():
    document = parse_srt(
        "1\n00:00:01,000 --> 00:00:02,000\nOne\n\n"
        "2\n00:00:03,000 --> 00:00:04,000\nTwo"
    )
    document.translation = "Une seule ligne"

    with pytest.raises(StorageError, match="Количество строк перевода"):
        serialize_srt(document)


def test_save_document_uses_srt_format_for_srt_extension(tmp_path):
    path = tmp_path / "lesson_fr.srt"
    document = parse_srt("1\n00:00:01,000 --> 00:00:02,000\nHello")
    document.translation = "Bonjour"

    save_document(path, document)

    assert path.read_text(encoding="utf-8") == (
        "1\n00:00:01,000 --> 00:00:02,000\nBonjour\n"
    )


def test_invalid_srt_raises_storage_error():
    with pytest.raises(StorageError, match="не содержит"):
        parse_srt("not subtitles")


def test_srt_parser_accepts_long_hour_values_and_missing_numeric_index():
    document = parse_srt("125:00:01,000 --> 126:00:02,000\nLong subtitle")

    assert document.subtitles[0].index == "1"
    assert document.subtitles[0].timing == "125:00:01,000 --> 126:00:02,000"


def test_load_docx_extracts_paragraphs(tmp_path):
    path = tmp_path / "lesson.docx"
    document_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p><w:r><w:t>First paragraph</w:t></w:r></w:p>
        <w:p><w:r><w:t>Second</w:t><w:tab/><w:t>part</w:t></w:r></w:p>
      </w:body>
    </w:document>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", document_xml)

    assert load_document(path) == Document("First paragraph\nSecond\tpart")


def test_corrupt_docx_raises_storage_error(tmp_path):
    path = tmp_path / "broken.docx"
    path.write_bytes(b"not a zip")

    with pytest.raises(StorageError, match="DOCX"):
        load_document(path)
