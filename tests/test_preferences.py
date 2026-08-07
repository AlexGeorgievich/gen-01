import json

from gpt01.preferences import Preferences, load_preferences, save_preferences


def test_preferences_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    expected = Preferences(
        source_language_key="French",
        editor_font_size=17,
        french_article_mode="definite",
    )
    save_preferences(path, expected)
    assert load_preferences(path) == expected


def test_interface_language_defaults_to_english_and_is_validated():
    assert Preferences.from_dict({}).interface_language == "en"
    assert Preferences.from_dict({"interface_language": "ru"}).interface_language == "ru"
    assert Preferences.from_dict({"interface_language": "invalid"}).interface_language == "en"


def test_recent_directories_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    expected = Preferences(
        last_open_directory="C:/Documents/source",
        last_export_directory="C:/Documents/export",
    )

    save_preferences(path, expected)

    assert load_preferences(path) == expected


def test_preferences_are_readable_json(tmp_path):
    path = tmp_path / "settings.json"
    save_preferences(path, Preferences(source_language_key="Japan"))
    assert json.loads(path.read_text(encoding="utf-8"))["source_language_key"] == "Japan"


def test_invalid_source_language_falls_back_to_auto():
    assert Preferences.from_dict({"source_language_key": "unknown"}).source_language_key == "auto"


def test_font_size_is_clamped():
    assert Preferences.from_dict({"editor_font_size": 2}).editor_font_size == 8
    assert Preferences.from_dict({"editor_font_size": 100}).editor_font_size == 32


def test_invalid_french_article_mode_falls_back_to_auto():
    preferences = Preferences.from_dict({"french_article_mode": "invalid"})

    assert preferences.french_article_mode == "auto"


def test_invalid_recent_directories_fall_back_to_empty_strings():
    preferences = Preferences.from_dict(
        {"last_open_directory": None, "last_export_directory": ["invalid"]}
    )

    assert preferences.last_open_directory == ""
    assert preferences.last_export_directory == ""


def test_corrupt_preferences_return_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("broken", encoding="utf-8")
    assert load_preferences(path) == Preferences()
