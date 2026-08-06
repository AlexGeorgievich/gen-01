import json
from pathlib import Path

import pytest

from gpt01.french_grammar import (
    FrenchArticleMode,
    FrenchGrammarProcessor,
    FrenchTranslationProvider,
)

RUSSIAN_ARTICLE_CASES = (
    ("дерево", "arbre", "l’arbre", "un arbre"),
    ("офис", "bureau", "le bureau", "un bureau"),
    ("стул", "chaise", "la chaise", "une chaise"),
    ("кот", "chat", "le chat", "un chat"),
    ("школа", "école", "l’école", "une école"),
    ("женщина", "femme", "la femme", "une femme"),
    ("герой", "héros", "le héros", "un héros"),
    ("мужчина", "homme", "l’homme", "un homme"),
    ("книга", "livre", "le livre", "un livre"),
    ("дом", "maison", "la maison", "une maison"),
    ("компьютер", "ordinateur", "l’ordinateur", "un ordinateur"),
    ("стол", "table", "la table", "une table"),
    ("картина", "tableau", "le tableau", "un tableau"),
    ("автомобиль", "voiture", "la voiture", "une voiture"),
    ("деревья", "arbres", "les arbres", "des arbres"),
    ("офисы", "bureaux", "les bureaux", "des bureaux"),
    ("стулья", "chaises", "les chaises", "des chaises"),
    ("коты", "chats", "les chats", "des chats"),
    ("школы", "écoles", "les écoles", "des écoles"),
    ("женщины", "femmes", "les femmes", "des femmes"),
)


@pytest.mark.parametrize(
    ("translated", "expected"),
    [
        ("tableau", "le tableau"),
        ("table", "la table"),
        ("tables", "les tables"),
        ("tableaux", "les tableaux"),
        ("école", "l’école"),
        ("homme", "l’homme"),
        ("héros", "le héros"),
    ],
)
def test_definite_articles_cover_gender_number_and_elision(translated, expected):
    processor = FrenchGrammarProcessor(FrenchArticleMode.DEFINITE)

    assert processor.process("term", translated) == expected


@pytest.mark.parametrize(
    ("translated", "expected"),
    [
        ("tableau", "un tableau"),
        ("table", "une table"),
        ("tables", "des tables"),
        ("école", "une école"),
    ],
)
def test_automatic_mode_uses_unambiguous_learning_articles(translated, expected):
    processor = FrenchGrammarProcessor(FrenchArticleMode.AUTO)

    assert processor.process("term", translated) == expected


@pytest.mark.parametrize(
    "translated",
    [
        "la table",
        "une table",
        "cette table",
        "du tableau",
        "C’est une table.",
        "Paris",
        "mot-inconnu",
    ],
)
def test_existing_determiners_sentences_and_unknown_terms_are_unchanged(translated):
    processor = FrenchGrammarProcessor(FrenchArticleMode.DEFINITE)

    assert processor.process("source", translated) == translated


def test_off_mode_does_not_change_known_noun():
    processor = FrenchGrammarProcessor(FrenchArticleMode.OFF)

    assert processor.process("стол", "tableau") == "tableau"


def test_source_override_corrects_the_table_example_before_adding_article():
    processor = FrenchGrammarProcessor(FrenchArticleMode.DEFINITE)

    assert processor.process("стол", "tableau") == "la table"
    assert processor.process("столы", "tableaux") == "les tables"


def test_multiline_translation_is_processed_line_by_line():
    processor = FrenchGrammarProcessor(FrenchArticleMode.INDEFINITE)

    assert processor.process("стол\nкартина", "tableau\ntableau") == (
        "une table\nun tableau"
    )


def test_multiline_processing_preserves_trailing_empty_line():
    processor = FrenchGrammarProcessor(FrenchArticleMode.DEFINITE)

    assert processor.process("стол\n", "tableau\n") == "la table\n"


def test_custom_lexicon_extends_entries_and_source_overrides(tmp_path):
    path = tmp_path / "lexicon.json"
    path.write_text(
        json.dumps(
            {
                "entries": {
                    "lampe": {"gender": "feminine", "elision": False},
                },
                "source_overrides": {"светильник": "lampe"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    processor = FrenchGrammarProcessor(FrenchArticleMode.DEFINITE, path)

    assert processor.process("светильник", "luminaire") == "la lampe"


def test_missing_external_lexicon_is_created(tmp_path):
    path = tmp_path / "French" / "lexicon.json"

    FrenchGrammarProcessor(FrenchArticleMode.AUTO, path)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["entries"]["table"]["gender"] == "feminine"


class StubTranslator:
    target_language = "fr"
    source_language = "ru"

    def translate(self, text, cancelled=None):
        return "tableau"


def test_translation_provider_applies_grammar_after_translation():
    provider = FrenchTranslationProvider(
        StubTranslator(),
        FrenchGrammarProcessor(FrenchArticleMode.DEFINITE),
    )

    assert provider.translate("стол") == "la table"
    assert provider.target_language == "fr"
    assert provider.source_language == "ru"


@pytest.mark.parametrize(
    ("source", "target", "definite", "indefinite"),
    RUSSIAN_ARTICLE_CASES,
)
def test_complete_russian_set_has_deterministic_article_forms(
    source,
    target,
    definite,
    indefinite,
):
    definite_processor = FrenchGrammarProcessor(FrenchArticleMode.DEFINITE)
    indefinite_processor = FrenchGrammarProcessor(FrenchArticleMode.INDEFINITE)
    automatic_processor = FrenchGrammarProcessor(FrenchArticleMode.AUTO)

    assert definite_processor.process(source, "вариант Google") == definite
    assert indefinite_processor.process(source, "вариант Google") == indefinite
    assert automatic_processor.process(source, "вариант Google") == indefinite
    assert target in definite or target in indefinite


def test_russian_test_file_matches_automated_article_cases():
    path = Path(__file__).parents[1] / "набор-франс.txt"
    expected_sources = [source for source, *_expected in RUSSIAN_ARTICLE_CASES]

    assert path.read_text(encoding="utf-8").splitlines() == expected_sources
