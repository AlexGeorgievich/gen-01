import pytest

from gpt01.errors import StorageError
from gpt01.exporting import ExportKind, export_document, render_export
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
