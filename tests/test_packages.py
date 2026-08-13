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
from gpt01.rows import build_sentence_translation_rows
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


def test_package_with_audio_duration_far_from_manifest_is_rejected(
    tmp_path, monkeypatch
):
    audio, _document, _manifest = create_package(tmp_path)
    monkeypatch.setattr("gpt01.packages.mp3_duration_ms", lambda _path: 10_000)

    with pytest.raises(StorageError, match="рассинхронизированы"):
        load_offline_package(audio, "English")


def test_complete_package_round_trip_and_discovery(tmp_path):
    audio, document, manifest = create_package(tmp_path)

    restored = load_offline_package(audio, "English")

    assert restored.document == document
    assert restored.manifest.total_duration_ms == manifest.total_duration_ms
    assert restored.manifest.lines[0].source_start == 0
    assert restored.manifest.lines[1].source_start == 4
    assert [package.stem for package in discover_packages(tmp_path, "English")] == [
        "lesson_en"
    ]


def test_legacy_package_restores_distinct_sentence_positions_on_one_line(tmp_path):
    audio = tmp_path / "legacy_en.mp3"
    document = Document(
        "Правда? / Действительно\nКонечно",
        "Really? / Indeed\nOf course",
        "really / indeed\nof course",
    )
    current_rows = build_sentence_translation_rows(
        document.original, document.translation, document.transcription
    )
    legacy_rows = [
        TranslationRow(row.index, row.source, row.translation, row.transcription)
        for row in current_rows
    ]
    manifest = TimedAudioManifest.create(
        "English",
        "en-US-GuyNeural",
        TtsSettings(),
        [
            timed_line_from_row(legacy_rows[0], 0, 500),
            timed_line_from_row(legacy_rows[1], 500, 600),
            timed_line_from_row(legacy_rows[2], 1100, 500),
        ],
    )
    audio.write_bytes(b"mp3")
    save_manifest(audio.with_suffix(".json"), manifest)
    audio.with_suffix(".srt").write_text("subtitles", encoding="utf-8")
    save_package_document(audio, "English", document)

    restored = load_offline_package(audio, "English")

    first, second, third = restored.manifest.lines
    assert first.source_start == 0
    assert second.source_start == document.original.index("/ Действительно")
    assert third.source_start == document.original.index("Конечно")
    assert len({first.source_start, second.source_start, third.source_start}) == 3


def test_incomplete_or_partial_document_package_is_rejected(tmp_path):
    audio, _document, _manifest = create_package(tmp_path)
    audio.with_suffix(".srt").unlink()

    with pytest.raises(StorageError, match="SRT"):
        load_offline_package(audio, "English")


def test_package_with_timestamps_for_different_text_is_rejected(tmp_path):
    audio, _document, manifest = create_package(tmp_path)
    changed = TimedAudioManifest.create(
        manifest.language,
        manifest.voice,
        TtsSettings(rate=manifest.rate),
        [
            timed_line_from_row(
                TranslationRow(0, "different", "one", "/wʌn/"), 0, 500
            ),
            manifest.lines[1],
        ],
    )
    save_manifest(audio.with_suffix(".json"), changed)

    with pytest.raises(StorageError, match="не соответствует временным меткам"):
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
