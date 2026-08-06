from pathlib import Path

from gpt01.languages import get_language
from gpt01.preferences import Preferences
from gpt01.session import MIGRATION_MARKER_NAME, SessionRepository, user_data_root
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


def test_saving_session_does_not_mutate_caller_state(tmp_path):
    repository = SessionRepository(tmp_path)
    profile = get_language("French")
    audio = tmp_path / "source.mp3"
    audio.write_bytes(b"audio")
    state = AppState(original="table")

    repository.save_session(profile, state, audio)

    assert state.audio_file == ""
    assert repository.load_session(profile).state.audio_file == "last_audio.mp3"


def test_preferences_round_trip(tmp_path):
    repository = SessionRepository(tmp_path)
    expected = Preferences("French", 16)
    repository.save_preferences(expected)
    assert repository.load_preferences() == expected


def test_legacy_data_is_copied_to_user_directory_without_deletion(tmp_path):
    legacy = tmp_path / "program"
    storage = tmp_path / "local" / "GPT01"
    language_directory = legacy / "language_data" / "Japan"
    language_directory.mkdir(parents=True)
    (legacy / "settings.json").write_text('{"editor_font_size": 18}', encoding="utf-8")
    (legacy / "language_selection.json").write_text(
        '{"selected_language": "Japan"}',
        encoding="utf-8",
    )
    (language_directory / "voices_cache.json").write_text("[]", encoding="utf-8")
    (language_directory / "lesson_jp.txt").write_text("lesson", encoding="utf-8")

    repository = SessionRepository.for_application(legacy, storage_root=storage)

    assert repository.preferences_path.read_text(encoding="utf-8") == (
        legacy / "settings.json"
    ).read_text(encoding="utf-8")
    assert repository.load_selected_language() == "Japan"
    assert (storage / "language_data" / "Japan" / "voices_cache.json").is_file()
    assert (storage / "language_data" / "Japan" / "lesson_jp.txt").is_file()
    assert (storage / MIGRATION_MARKER_NAME).is_file()
    assert (legacy / "settings.json").is_file()
    assert (language_directory / "lesson_jp.txt").is_file()


def test_migration_never_overwrites_existing_user_data(tmp_path):
    legacy = tmp_path / "program"
    storage = tmp_path / "local" / "GPT01"
    legacy.mkdir()
    storage.mkdir(parents=True)
    (legacy / "settings.json").write_text("legacy", encoding="utf-8")
    (storage / "settings.json").write_text("current", encoding="utf-8")

    SessionRepository.for_application(legacy, storage_root=storage)

    assert (storage / "settings.json").read_text(encoding="utf-8") == "current"


def test_migration_marker_makes_copy_one_time_only(tmp_path):
    legacy = tmp_path / "program"
    storage = tmp_path / "local" / "GPT01"
    legacy.mkdir()
    (legacy / "settings.json").write_text("first", encoding="utf-8")
    SessionRepository.for_application(legacy, storage_root=storage)
    (storage / "settings.json").unlink()
    (legacy / "settings.json").write_text("second", encoding="utf-8")

    SessionRepository.for_application(legacy, storage_root=storage)

    assert not (storage / "settings.json").exists()


def test_migrated_legacy_chinese_session_restores_audio(tmp_path):
    legacy = tmp_path / "program"
    storage = tmp_path / "local" / "GPT01"
    legacy.mkdir()
    save_app_state(legacy / "app_state.json", AppState(original="старый текст"))
    (legacy / "last_audio.mp3").write_bytes(b"audio")

    repository = SessionRepository.for_application(legacy, storage_root=storage)
    restored = repository.load_session(get_language("Chine"))

    assert restored.state.original == "старый текст"
    assert restored.audio_path == storage / "last_audio.mp3"
    assert restored.audio_path.read_bytes() == b"audio"
