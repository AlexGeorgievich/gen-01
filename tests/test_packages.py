import pytest

from gpt01.errors import StorageError
from gpt01.models import Document, TranslationRow
from gpt01.packages import (
    discover_packages,
    load_offline_package,
    load_package_history,
    save_package_document,
    touch_package_history,
)
from gpt01.timed_audio import TimedAudioManifest, save_manifest, timed_line_from_row
from gpt01.tts import TtsSettings


def create_package(root, stem="lesson_en", language="English"):
    audio = root / f"{stem}.mp3"
    document = Document("one\ntwo", "one\ntwo", "/wʌn/\n/tuː/")
    rows = [
        TranslationRow(0, "one", "one", "/wʌn/"),
        TranslationRow(1, "two", "two", "/tuː/"),
    ]
    manifest = TimedAudioManifest.create(
        language,
        "en-US-GuyNeural",
        TtsSettings(rate=5),
        [
            timed_line_from_row(rows[0], 0, 500),
            timed_line_from_row(rows[1], 500, 600),
        ],
    )
    audio.write_bytes(b"mp3")
    save_manifest(audio.with_suffix(".json"), manifest)
    audio.with_suffix(".srt").write_text("subtitles", encoding="utf-8")
    save_package_document(audio, language, document)
    return audio, document, manifest


def test_complete_package_round_trip_and_discovery(tmp_path):
    audio, document, manifest = create_package(tmp_path)

    restored = load_offline_package(audio, "English")

    assert restored.document == document
    assert restored.manifest == manifest
    assert [package.stem for package in discover_packages(tmp_path, "English")] == [
        "lesson_en"
    ]


def test_incomplete_or_partial_document_package_is_rejected(tmp_path):
    audio, _document, _manifest = create_package(tmp_path)
    audio.with_suffix(".srt").unlink()

    with pytest.raises(StorageError, match="SRT"):
        load_offline_package(audio, "English")


def test_history_is_deduplicated_newest_first_and_limited_to_ten(tmp_path):
    history = tmp_path / "package_history.json"
    paths = [tmp_path / f"lesson_{index}.mp3" for index in range(11)]
    for path in paths:
        touch_package_history(history, "English", path)
    touch_package_history(history, "English", paths[5])

    entries = load_package_history(history)

    assert len(entries) == 10
    assert entries[0].audio_path == str(paths[5].resolve())
    assert len({entry.audio_path for entry in entries}) == 10
