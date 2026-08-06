from gpt01.languages import get_language
from gpt01.preferences import Preferences
from gpt01.session import SessionRepository
from gpt01.state import AppState


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
