from gpt01.i18n import normalize_interface_language, ui_text


def test_ui_catalog_switches_language_and_formats_values() -> None:
    assert ui_text("en", "clear") == "Clear"
    assert ui_text("ru", "clear") == "Очистить"
    assert ui_text("en", "cached_voices", count=3) == "Voices loaded from cache: 3"


def test_unknown_interface_language_falls_back_to_english() -> None:
    assert normalize_interface_language("de") == "en"
