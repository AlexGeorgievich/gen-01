from gpt01.languages import (
    DEFAULT_LANGUAGE_KEY,
    LANGUAGES,
    get_language,
    load_selected_language,
    save_selected_language,
)


def test_required_language_profiles_exist():
    assert {profile.key for profile in LANGUAGES} == {
        "French",
        "Spanish",
        "Japan",
        "Chine",
    }


def test_language_profiles_have_distinct_translation_targets():
    assert {profile.translation_code for profile in LANGUAGES} == {"fr", "es", "ja", "zh-CN"}


def test_language_profiles_have_expected_file_suffixes():
    assert {profile.key: profile.file_suffix for profile in LANGUAGES} == {
        "French": "fr",
        "Spanish": "es",
        "Japan": "jp",
        "Chine": "zh",
    }


def test_unknown_language_falls_back_to_chine():
    assert get_language("unknown").key == DEFAULT_LANGUAGE_KEY


def test_language_selection_round_trip(tmp_path):
    path = tmp_path / "selection.json"
    save_selected_language(path, "Japan")
    assert load_selected_language(path) == "Japan"


def test_invalid_language_selection_uses_default(tmp_path):
    path = tmp_path / "selection.json"
    path.write_text('{"selected_language": "invalid"}', encoding="utf-8")
    assert load_selected_language(path) == DEFAULT_LANGUAGE_KEY
