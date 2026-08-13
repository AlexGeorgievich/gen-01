import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app import MainWindow  # noqa: E402
from gpt01.models import Document, TranslationRow  # noqa: E402
from gpt01.packages import load_package_history, save_package_document  # noqa: E402
from gpt01.preferences import AudioPreparationMode  # noqa: E402
from gpt01.session import SessionRepository  # noqa: E402
from gpt01.timed_audio import (  # noqa: E402
    TimedAudioManifest,
    save_manifest,
    timed_line_from_row,
)
from gpt01.tts import TtsSettings  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class FakeTranslator:
    def translate(self, text, _cancelled=None):
        return "\n".join(f"translated {line}" for line in text.splitlines())


def test_translate_builds_complete_mp3_manifest_and_srt(qapp, tmp_path):
    window = MainWindow(SessionRepository(tmp_path))
    window.audio_preparation_mode = AudioPreparationMode.COMPLETE_PACKAGE.value
    window.language_controller.translator = FakeTranslator()
    window.source_edit.setPlainText("one\n\ntwo")

    def synthesize_timed(text, _voice, output, _cancelled, *, settings=None):
        output.write_bytes(text.encode("utf-8"))
        return 750

    window.speech.synthesize_timed = synthesize_timed
    window._run_progress_task = lambda function, on_result, *_args: on_result(
        function(lambda: False, lambda *_report: None)
    )

    window.translate_text()

    assert window.translation_edit.toPlainText() == (
        "translated one\n\ntranslated two"
    )
    assert window._timed_audio_ready()
    assert window.audio_path.read_bytes() == b"translated onetranslated two"
    assert [line.line for line in window.timed_manifest.lines] == [0, 2]
    assert [line.start_ms for line in window.timed_manifest.lines] == [0, 750]
    assert [line.end_ms for line in window.timed_manifest.lines] == [750, 1500]
    assert "00:00:00,750 --> 00:00:01,500" in window.audio_srt_path.read_text(
        encoding="utf-8"
    )

    window._reset_audio_state()
    window._dirty = False
    window.close()


def test_fast_mode_translates_without_waiting_for_audio(qapp, tmp_path):
    window = MainWindow(SessionRepository(tmp_path))
    window.language_controller.translator = FakeTranslator()
    window.source_edit.setPlainText("one\ntwo")
    synthesized = []

    def unexpected_synthesis(*args, **kwargs):
        synthesized.append((args, kwargs))
        raise AssertionError("fast translation must not synthesize audio")

    window.speech.synthesize_timed = unexpected_synthesis
    window._run_progress_task = lambda function, on_result, *_args: on_result(
        function(lambda: False, lambda *_report: None)
    )

    window.translate_text()

    assert window.translation_edit.toPlainText() == "translated one\ntranslated two"
    assert synthesized == []
    assert not window._timed_audio_ready()

    started = []
    window._start_sequence = lambda: started.append(True)
    window.speak_text()
    assert started == [True]

    window._dirty = False
    window.close()


def test_open_offline_package_restores_document_audio_and_history(
    qapp, tmp_path, monkeypatch
):
    repository = SessionRepository(tmp_path)
    language_directory = repository.data_root / "English"
    language_directory.mkdir(parents=True)
    audio = language_directory / "lesson_en.mp3"
    document = Document("one\ntwo", "one\ntwo", "/wʌn/\n/tuː/")
    rows = [
        TranslationRow(0, "one", "one", "/wʌn/"),
        TranslationRow(1, "two", "two", "/tuː/"),
    ]
    manifest = TimedAudioManifest.create(
        "English",
        "en-US-GuyNeural",
        TtsSettings(rate=10),
        [
            timed_line_from_row(rows[0], 0, 500),
            timed_line_from_row(rows[1], 500, 500),
        ],
    )
    audio.write_bytes(b"audio")
    save_manifest(audio.with_suffix(".json"), manifest)
    audio.with_suffix(".srt").write_text("subtitles", encoding="utf-8")
    save_package_document(audio, "English", document)
    window = MainWindow(repository)
    monkeypatch.setattr(window.player, "setSource", lambda _source: None)

    assert window._open_offline_package(audio, "English")
    assert window.current_language.key == "English"
    assert window.source_edit.toPlainText() == "one\ntwo"
    assert window.translation_edit.toPlainText() == "one\ntwo"
    assert window.transcription_edit.toPlainText() == "/wʌn/\n/tuː/"
    assert window.audio_path == audio
    assert window.timed_manifest is not None
    assert window.timed_manifest.total_duration_ms == manifest.total_duration_ms
    assert [line.source_start for line in window.timed_manifest.lines] == [0, 4]
    assert window._timed_audio_ready()
    assert load_package_history(repository.package_history_path)[0].name == "lesson_en"

    window._dirty = False
    window.close()
