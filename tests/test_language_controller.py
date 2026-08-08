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


def test_controller_configures_new_translation_targets_and_voice_filters():
    cases = (
        ("German", "de", "de-DE"),
        ("Italian", "it", "it-IT"),
        ("Turkish", "tr", "tr-TR"),
    )
    voices = [
        {"Locale": locale, "ShortName": f"{locale}-Voice"}
        for _language, _target, locale in cases
    ]

    for language, target, locale in cases:
        controller = LanguageController(language)
        assert controller.translator.target_language == target
        assert controller.filter_voices(voices) == [
            {"Locale": locale, "ShortName": f"{locale}-Voice"}
        ]


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


def test_controller_normalizes_standalone_asian_numerals():
    controller = LanguageController("Japan", "Russian")

    assert controller.prepare_translation("один\nдвадцать", "1つ\n20") == "一\n二十"
    assert controller.prepare_speech("四\n七") == "よん\nなな"
    controller.select_target("Chine")
    assert controller.prepare_translation("сто один", "101") == "一百零一"


def test_controller_keeps_contextual_asian_numbers_unchanged():
    controller = LanguageController("Chine", "Russian")

    assert controller.prepare_translation("у меня две книги", "我有两本书") == "我有两本书"
