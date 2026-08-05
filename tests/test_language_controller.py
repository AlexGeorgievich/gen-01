from gpt01.language_controller import LanguageController


def test_controller_switches_translation_target():
    controller = LanguageController("Chine")
    controller.select_target("Spanish")
    assert controller.profile.key == "Spanish"
    assert controller.translator.target_language == "es"


def test_controller_uses_selected_source_language():
    controller = LanguageController("Spanish", "English")
    assert controller.translator.source_language == "en"


def test_controller_updates_source_language():
    controller = LanguageController("French")
    controller.select_source("Japan")
    assert controller.translator.source_language == "ja"


def test_controller_filters_target_voices():
    controller = LanguageController("English")
    voices = [
        {"Locale": "en-US", "ShortName": "English"},
        {"Locale": "fr-FR", "ShortName": "French"},
    ]
    assert controller.filter_voices(voices) == [voices[0]]


def test_controller_transcribes_for_current_profile():
    controller = LanguageController("Chine")
    assert controller.transcribe("你好") == "nǐ hǎo"
