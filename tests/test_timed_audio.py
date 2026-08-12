import pytest

from gpt01.errors import NetworkServiceError
from gpt01.models import TranslationRow
from gpt01.rows import build_sentence_translation_rows
from gpt01.timed_audio import (
    TimedAudioManifest,
    build_timed_audio_package,
    format_srt_timestamp,
    load_manifest,
    render_srt,
    save_manifest,
    timed_line_from_row,
)
from gpt01.tts import TtsSettings


def _manifest() -> TimedAudioManifest:
    rows = [
        TranslationRow(0, "one", "un", "un"),
        TranslationRow(2, "three", "trois", "tʁwa"),
    ]
    lines = [
        timed_line_from_row(rows[0], 0, 1250),
        timed_line_from_row(rows[1], 1250, 2000),
    ]
    return TimedAudioManifest.create(
        "French",
        "fr-FR-DeniseNeural",
        TtsSettings(rate=10, pitch=-2, volume=5),
        lines,
    )


def test_manifest_round_trip_and_line_lookup(tmp_path):
    path = tmp_path / "lesson.json"
    expected = _manifest()

    save_manifest(path, expected)
    restored = load_manifest(path)

    assert restored == expected
    assert restored.line_at(0).line == 0
    assert restored.line_at(1249).line == 0
    assert restored.line_at(1250).line == 2
    assert restored.interval(2, 0) == (0, 3250)


def test_srt_uses_translation_and_shared_timestamps():
    rendered = render_srt(_manifest())

    assert "00:00:00,000 --> 00:00:01,250\nun" in rendered
    assert "00:00:01,250 --> 00:00:03,250\ntrois" in rendered
    assert "one" not in rendered


def test_srt_timestamp_supports_long_audio():
    assert format_srt_timestamp(450_061_007) == "125:01:01,007"


def test_invalid_manifest_is_rejected(tmp_path):
    path = tmp_path / "invalid.json"
    path.write_text('{"version": 1, "lines": []}', encoding="utf-8")

    assert load_manifest(path) is None


def test_build_package_concatenates_rows_and_writes_matching_json_srt(tmp_path):
    rows = [
        TranslationRow(0, "one", "un", "un"),
        TranslationRow(2, "three", "trois", "tʁwa"),
    ]
    audio = tmp_path / "lesson.mp3"
    manifest_path = tmp_path / "lesson.json"
    srt_path = tmp_path / "lesson.srt"
    progress = []

    def synthesize(text, output):
        output.write_bytes(text.encode("utf-8"))
        return {"un": 1000, "trois": 1500}[text]

    package = build_timed_audio_package(
        rows,
        audio,
        manifest_path,
        srt_path,
        "French",
        "fr-FR-DeniseNeural",
        TtsSettings(),
        synthesize,
        progress=lambda current, total: progress.append((current, total)),
    )

    assert package.audio_path.read_bytes() == b"untrois"
    assert package.manifest.total_duration_ms == 2500
    assert load_manifest(manifest_path) == package.manifest
    assert "00:00:01,000 --> 00:00:02,500\ntrois" in srt_path.read_text(
        encoding="utf-8"
    )
    assert progress == [(1, 2), (2, 2)]


def test_package_uses_sentence_rows_and_persists_highlight_ranges(tmp_path):
    rows = build_sentence_translation_rows("One. Two.", "Un. Deux.")
    audio = tmp_path / "sentences.mp3"
    manifest_path = tmp_path / "sentences.json"
    srt_path = tmp_path / "sentences.srt"

    package = build_timed_audio_package(
        rows,
        audio,
        manifest_path,
        srt_path,
        "French",
        "voice",
        TtsSettings(),
        lambda text, output: (output.write_bytes(text.encode()), 500)[1],
    )

    assert [line.translation for line in package.manifest.lines] == ["Un.", "Deux."]
    assert [line.line for line in package.manifest.lines] == [0, 0]
    assert package.manifest.lines[1].source_start == 5
    assert package.manifest.lines[1].translation_start == 4
    assert render_srt(package.manifest).count(" --> ") == 2


def test_failed_package_resumes_from_persisted_audio_parts(tmp_path):
    rows = [
        TranslationRow(0, "one", "un", "un"),
        TranslationRow(1, "two", "deux", "dø"),
        TranslationRow(2, "three", "trois", "tʁwa"),
    ]
    audio = tmp_path / "lesson.mp3"
    manifest_path = tmp_path / "lesson.json"
    srt_path = tmp_path / "lesson.srt"
    resume_root = tmp_path / "tts_jobs"
    first_calls = []

    def interrupted_synthesis(text, output):
        first_calls.append(text)
        if text == "deux":
            raise NetworkServiceError("network interruption")
        output.write_bytes(text.encode())
        return 500

    with pytest.raises(NetworkServiceError, match="готово 1 из 3"):
        build_timed_audio_package(
            rows,
            audio,
            manifest_path,
            srt_path,
            "French",
            "voice",
            TtsSettings(),
            interrupted_synthesis,
            resume_root=resume_root,
        )

    assert first_calls == ["un", "deux"]
    assert list(resume_root.rglob("checkpoint.json"))
    resumed_calls = []

    def resumed_synthesis(text, output):
        resumed_calls.append(text)
        output.write_bytes(text.encode())
        return 500

    package = build_timed_audio_package(
        rows,
        audio,
        manifest_path,
        srt_path,
        "French",
        "voice",
        TtsSettings(),
        resumed_synthesis,
        resume_root=resume_root,
    )

    assert resumed_calls == ["deux", "trois"]
    assert package.audio_path.read_bytes() == b"undeuxtrois"
    assert not list(resume_root.rglob("checkpoint.json"))
