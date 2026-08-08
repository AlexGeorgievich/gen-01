from gpt01.languages import (
    DEFAULT_LANGUAGE_KEY,
    LANGUAGES,
    get_language,
    load_selected_language,
    save_selected_language,
)


def test_required_language_profiles_exist():
    assert {profile.key for profile in LANGUAGES} == {
        "English",
        "French",
        "Spanish",
        "German",
        "Italian",
        "Turkish",
        "Russian",
        "Japan",
        "Chine",
    }


def test_language_profiles_have_distinct_translation_targets():
    assert {profile.translation_code for profile in LANGUAGES} == {
        "en",
        "fr",
        "es",
        "de",
        "it",
        "tr",
        "ru",
        "ja",
        "zh-CN",
    }


def test_language_profiles_have_expected_file_suffixes():
    assert {profile.key: profile.file_suffix for profile in LANGUAGES} == {
        "English": "en",
        "French": "fr",
        "Spanish": "es",
        "German": "de",
        "Italian": "it",
        "Turkish": "tr",
        "Russian": "ru",
        "Japan": "jp",
        "Chine": "zh",
    }


def test_european_languages_use_ipa_profiles():
    european = {
        "English",
        "French",
        "Spanish",
        "German",
        "Italian",
        "Turkish",
        "Russian",
    }
    assert {
        profile.key: profile.transcription_mode
        for profile in LANGUAGES
        if profile.key in european
    } == {
        "English": "ipa_en",
        "French": "ipa_fr",
        "Spanish": "ipa_es",
        "German": "ipa_de",
        "Italian": "ipa_it",
        "Turkish": "ipa_tr",
        "Russian": "ipa_ru",
    }


def test_new_language_profiles_use_expected_edge_voices():
    expected = {
        "German": ("de-DE-KatjaNeural", "de-"),
        "Italian": ("it-IT-ElsaNeural", "it-"),
        "Turkish": ("tr-TR-EmelNeural", "tr-"),
    }

    for key, (voice, prefix) in expected.items():
        profile = get_language(key)
        assert profile.default_voice == voice
        assert profile.voice_prefix == prefix
        assert all(item["Locale"].startswith(prefix) for item in profile.fallback_voices)


def test_russian_profile_uses_russian_edge_voices():
    profile = get_language("Russian")

    assert profile.default_voice == "ru-RU-SvetlanaNeural"
    assert {voice["ShortName"] for voice in profile.fallback_voices} == {
        "ru-RU-SvetlanaNeural",
        "ru-RU-DmitryNeural",
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
