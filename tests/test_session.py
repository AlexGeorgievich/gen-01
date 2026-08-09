from pathlib import Path

from gpt01.languages import get_language
from gpt01.preferences import AudioPreparationMode, Preferences
from gpt01.session import (
    MIGRATION_MARKER_NAME,
    SessionRepository,
    user_data_root,
)
from gpt01.state import AppState, save_app_state


def test_user_data_root_uses_local_app_data():
    assert user_data_root({"LOCALAPPDATA": "C:/Users/Test/AppData/Local"}) == (
        Path("C:/Users/Test/AppData/Local") / "GPT01"
    )


def test_language_paths_are_isolated(tmp_path):
    repository = SessionRepository(tmp_path)
    assert repository.state_path(get_language("French")) != repository.state_path(
        get_language("Spanish")
    )


def test_french_lexicon_has_language_specific_external_path(tmp_path):
    repository = SessionRepository(tmp_path)

    assert repository.french_lexicon_path() == (
        tmp_path / "language_data" / "French" / "lexicon.json"
    )


def test_export_path_adds_language_suffix(tmp_path):
    repository = SessionRepository(tmp_path)
    target = repository.export_path(get_language("Japan"), "lesson.txt", ".txt")
    assert target == tmp_path / "language_data" / "Japan" / "lesson_jp.txt"


def test_russian_export_uses_isolated_directory_and_suffix(tmp_path):
    repository = SessionRepository(tmp_path)

    target = repository.export_path(get_language("Russian"), "lesson.txt", ".txt")

    assert target == tmp_path / "language_data" / "Russian" / "lesson_ru.txt"


def test_new_language_exports_use_isolated_directories_and_suffixes(tmp_path):
    repository = SessionRepository(tmp_path)

    for language, suffix in (("German", "de"), ("Italian", "it"), ("Turkish", "tr")):
        target = repository.export_path(get_language(language), "lesson.txt", ".txt")
        assert target == (
            tmp_path / "language_data" / language / f"lesson_{suffix}.txt"
        )


def test_export_path_does_not_duplicate_suffix(tmp_path):
    repository = SessionRepository(tmp_path)
    target = repository.export_path(get_language("English"), "lesson_en.txt", ".txt")
    assert target.name == "lesson_en.txt"


def test_session_round_trip(tmp_path):
    repository = SessionRepository(tmp_path)
    profile = get_language("Spanish")
    expected = AppState(original="source", translation="traducción")
    repository.save_session(profile, expected, None)
    assert repository.load_session(profile).state == expected


def test_audio_mode_is_stored_independently_for_each_language(tmp_path):
    repository = SessionRepository(tmp_path)
    french = get_language("French")
    spanish = get_language("Spanish")
    repository.save_session(
        french,
        AppState(
            audio_preparation_mode=AudioPreparationMode.COMPLETE_PACKAGE.value
        ),
        None,
    )
    repository.save_session(spanish, AppState(), None)

    assert repository.load_session(french).state.audio_preparation_mode == "package"
    assert repository.load_session(spanish).state.audio_preparation_mode == "line"


def test_saving_session_does_not_mutate_caller_state(tmp_path):
    repository = SessionRepository(tmp_path)
    profile = get_language("French")
    audio = tmp_path / "source.mp3"
    audio.write_bytes(b"audio")
    state = AppState(original="table")

    repository.save_session(profile, state, audio)

    assert state.audio_file == ""
    assert repository.load_session(profile).state.audio_file == "last_audio.mp3"


def test_saving_session_copies_audio_timing_companions(tmp_path):
    repository = SessionRepository(tmp_path)
    profile = get_language("English")
    audio = tmp_path / "prepared.mp3"
    audio.write_bytes(b"audio")
    audio.with_suffix(".json").write_text('{"version": 1}', encoding="utf-8")
    audio.with_suffix(".srt").write_text("subtitle", encoding="utf-8")

    repository.save_session(profile, AppState(original="lesson"), audio)

    assert repository.audio_path(profile).read_bytes() == b"audio"
    assert repository.audio_manifest_path(profile).read_text(encoding="utf-8") == (
        '{"version": 1}'
    )
    assert repository.audio_srt_path(profile).read_text(encoding="utf-8") == "subtitle"


def test_saving_audio_without_timings_removes_stale_companions(tmp_path):
    repository = SessionRepository(tmp_path)
    profile = get_language("English")
    repository.ensure_language_directory(profile)
    repository.audio_manifest_path(profile).write_text("stale", encoding="utf-8")
    repository.audio_srt_path(profile).write_text("stale", encoding="utf-8")
    audio = tmp_path / "single-line.mp3"
    audio.write_bytes(b"audio")

    repository.save_session(profile, AppState(original="lesson"), audio)

    assert not repository.audio_manifest_path(profile).exists()
    assert not repository.audio_srt_path(profile).exists()


def test_preferences_round_trip(tmp_path):
    repository = SessionRepository(tmp_path)
    expected = Preferences("French", 16)
    repository.save_preferences(expected)
    assert repository.load_preferences() == expected


def test_legacy_data_is_copied_to_user_directory_without_deletion(tmp_path):
    program = tmp_path / "program"
    storage = tmp_path / "local" / "GPT01"
    language_directory = storage / "language_data" / "Japan"
    language_directory.mkdir(parents=True)
    (storage / "settings.json").write_text('{"editor_font_size": 18}', encoding="utf-8")
    (storage / "language_selection.json").write_text(
        '{"selected_language": "Japan"}',
        encoding="utf-8",
    )
    (language_directory / "voices_cache.json").write_text("[]", encoding="utf-8")
    (language_directory / "lesson_jp.txt").write_text("lesson", encoding="utf-8")

    repository = SessionRepository.for_application(program, storage_root=storage)

    assert repository.preferences_path.read_text(encoding="utf-8") == (
        storage / "settings.json"
    ).read_text(encoding="utf-8")
    assert repository.load_selected_language() == "Japan"
    assert repository.data_root == program / "language_data"
    assert (program / "language_data" / "Japan" / "voices_cache.json").is_file()
    assert (program / "language_data" / "Japan" / "lesson_jp.txt").is_file()
    assert (program / MIGRATION_MARKER_NAME).is_file()
    assert (storage / "settings.json").is_file()
    assert (language_directory / "lesson_jp.txt").is_file()


def test_for_application_creates_language_data_beside_program(tmp_path):
    program = tmp_path / "VoiceGun"
    storage = tmp_path / "local" / "GPT01"
    program.mkdir()

    repository = SessionRepository.for_application(program, storage_root=storage)

    assert repository.data_root == program / "language_data"
    assert repository.data_root.is_dir()
    assert repository.preferences_path == program / "settings.json"


def test_existing_local_language_data_is_copied_to_program_without_deletion(tmp_path):
    program = tmp_path / "VoiceGun"
    storage = tmp_path / "local" / "GPT01"
    previous = storage / "language_data" / "French"
    current = program / "language_data" / "French"
    previous.mkdir(parents=True)
    current.mkdir(parents=True)
    (previous / "lesson_fr.txt").write_text("ancien", encoding="utf-8")
    (previous / "keep_fr.txt").write_text("source", encoding="utf-8")
    (current / "keep_fr.txt").write_text("current", encoding="utf-8")

    SessionRepository.for_application(program, storage_root=storage)

    assert (current / "lesson_fr.txt").read_text(encoding="utf-8") == "ancien"
    assert (current / "keep_fr.txt").read_text(encoding="utf-8") == "current"
    assert (previous / "lesson_fr.txt").is_file()
    assert (program / MIGRATION_MARKER_NAME).is_file()


def test_migration_never_overwrites_existing_user_data(tmp_path):
    program = tmp_path / "program"
    storage = tmp_path / "local" / "GPT01"
    program.mkdir()
    storage.mkdir(parents=True)
    (storage / "settings.json").write_text("legacy", encoding="utf-8")
    (program / "settings.json").write_text("current", encoding="utf-8")

    SessionRepository.for_application(program, storage_root=storage)

    assert (program / "settings.json").read_text(encoding="utf-8") == "current"


def test_migration_marker_makes_copy_one_time_only(tmp_path):
    program = tmp_path / "program"
    storage = tmp_path / "local" / "GPT01"
    program.mkdir()
    storage.mkdir(parents=True)
    (storage / "settings.json").write_text("first", encoding="utf-8")
    SessionRepository.for_application(program, storage_root=storage)
    (program / "settings.json").unlink()
    (storage / "settings.json").write_text("second", encoding="utf-8")

    SessionRepository.for_application(program, storage_root=storage)

    assert not (program / "settings.json").exists()


def test_migrated_legacy_chinese_session_restores_audio(tmp_path):
    program = tmp_path / "program"
    storage = tmp_path / "local" / "GPT01"
    storage.mkdir(parents=True)
    save_app_state(storage / "app_state.json", AppState(original="старый текст"))
    (storage / "last_audio.mp3").write_bytes(b"audio")

    repository = SessionRepository.for_application(program, storage_root=storage)
    restored = repository.load_session(get_language("Chine"))

    assert restored.state.original == "старый текст"
    assert restored.audio_path == program / "last_audio.mp3"
    assert restored.audio_path.read_bytes() == b"audio"
