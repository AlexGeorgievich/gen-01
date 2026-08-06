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


def test_controller_configures_russian_translation_voice_and_transcription():
    controller = LanguageController("Chine")
    controller.select_target("Russian")
    voices = [
        {"Locale": "ru-RU", "ShortName": "ru-RU-SvetlanaNeural"},
        {"Locale": "en-US", "ShortName": "en-US-AriaNeural"},
    ]

    assert controller.translator.target_language == "ru"
    assert controller.filter_voices(voices) == [voices[0]]
    assert controller.transcribe("Привет") == "/prʲivʲet/"


def test_controller_transcribes_for_current_profile():
    controller = LanguageController("Chine")
    assert controller.transcribe("你好") == "nǐ hǎo"


def test_controller_prepares_french_translation_with_selected_article_mode():
    controller = LanguageController("French", french_article_mode="definite")

    assert controller.prepare_translation("стол", "tableau") == "la table"
    controller.set_french_article_mode("off")
    assert controller.prepare_translation("стол", "tableau") == "tableau"


def test_controller_does_not_apply_french_rules_to_other_languages():
    controller = LanguageController("Spanish", french_article_mode="definite")

    assert controller.prepare_translation("стол", "tableau") == "tableau"
