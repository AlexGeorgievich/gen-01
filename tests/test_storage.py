from gpt01.models import Document
from gpt01.storage import (
    LEGACY_TRANSLATION_MARKER,
    ORIGINAL_MARKER,
    TRANSCRIPTION_MARKER,
    TRANSLATION_MARKER,
    decode_text,
    parse_document,
    serialize_document,
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
