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
    ("сад", "jardin", "le jardin", "un jardin"),
    ("телефон", "téléphone", "le téléphone", "un téléphone"),
    ("сыр", "fromage", "le fromage", "un fromage"),
    ("хлеб", "pain", "le pain", "un pain"),
    ("собака", "chien", "le chien", "un chien"),
    ("мальчик", "garçon", "le garçon", "un garçon"),
    ("отец", "père", "le père", "un père"),
    ("брат", "frère", "le frère", "un frère"),
    ("солнце", "soleil", "le soleil", "un soleil"),
    ("поезд", "train", "le train", "un train"),
    ("велосипед", "vélo", "le vélo", "un vélo"),
    ("работа", "travail", "le travail", "un travail"),
    ("путешествие", "voyage", "le voyage", "un voyage"),
    ("фильм", "film", "le film", "un film"),
    ("газета", "journal", "le journal", "un journal"),
    ("рынок", "marché", "le marché", "un marché"),
    ("ресторан", "restaurant", "le restaurant", "un restaurant"),
    ("музей", "musée", "le musée", "un musée"),
    ("больница", "hôpital", "l’hôpital", "un hôpital"),
    ("отель", "hôtel", "l’hôtel", "un hôtel"),
    ("фасоль", "haricot", "le haricot", "un haricot"),
    ("случай", "hasard", "le hasard", "un hasard"),
    ("лампа", "lampe", "la lampe", "une lampe"),
    ("окно", "fenêtre", "la fenêtre", "une fenêtre"),
    ("город", "ville", "la ville", "une ville"),
    ("комната", "chambre", "la chambre", "une chambre"),
    ("дверь", "porte", "la porte", "une porte"),
    ("дорога", "route", "la route", "une route"),
    ("улица", "rue", "la rue", "une rue"),
    ("цветок", "fleur", "la fleur", "une fleur"),
    ("море", "mer", "la mer", "une mer"),
    ("гора", "montagne", "la montagne", "une montagne"),
    ("река", "rivière", "la rivière", "une rivière"),
    ("музыка", "musique", "la musique", "une musique"),
    ("вопрос", "question", "la question", "une question"),
    ("ответ", "réponse", "la réponse", "une réponse"),
    ("семья", "famille", "la famille", "une famille"),
    ("мать", "mère", "la mère", "une mère"),
    ("сестра", "sœur", "la sœur", "une sœur"),
    ("девочка", "fille", "la fille", "une fille"),
    ("ночь", "nuit", "la nuit", "une nuit"),
    ("прогулка", "promenade", "la promenade", "une promenade"),
    ("история", "histoire", "l’histoire", "une histoire"),
    ("час", "heure", "l’heure", "une heure"),
    ("масло", "huile", "l’huile", "une huile"),
    ("топор", "hache", "la hache", "une hache"),
    ("ненависть", "haine", "la haine", "une haine"),
    ("друг", "ami", "l’ami", "un ami"),
    ("животное", "animal", "l’animal", "un animal"),
    ("самолёт", "avion", "l’avion", "un avion"),
    ("ребёнок", "enfant", "l’enfant", "un enfant"),
    ("лето", "été", "l’été", "un été"),
    ("яйцо", "œuf", "l’œuf", "un œuf"),
    ("птица", "oiseau", "l’oiseau", "un oiseau"),
    ("апельсин", "orange", "l’orange", "une orange"),
    ("церковь", "église", "l’église", "une église"),
    ("идея", "idée", "l’idée", "une idée"),
    ("изображение", "image", "l’image", "une image"),
    ("завод", "usine", "l’usine", "une usine"),
    ("остров", "île", "l’île", "une île"),
    ("дома", "maisons", "les maisons", "des maisons"),
    ("книги", "livres", "les livres", "des livres"),
    ("автомобили", "voitures", "les voitures", "des voitures"),
    ("компьютеры", "ordinateurs", "les ordinateurs", "des ordinateurs"),
    ("окна", "fenêtres", "les fenêtres", "des fenêtres"),
    ("города", "villes", "les villes", "des villes"),
    ("сады", "jardins", "les jardins", "des jardins"),
    ("дети", "enfants", "les enfants", "des enfants"),
    ("моря", "mers", "les mers", "des mers"),
    ("телефоны", "téléphones", "les téléphones", "des téléphones"),
    ("собаки", "chiens", "les chiens", "des chiens"),
    ("мальчики", "garçons", "les garçons", "des garçons"),
    ("поезда", "trains", "les trains", "des trains"),
    ("велосипеды", "vélos", "les vélos", "des vélos"),
    ("фильмы", "films", "les films", "des films"),
    ("рынки", "marchés", "les marchés", "des marchés"),
    ("рестораны", "restaurants", "les restaurants", "des restaurants"),
    ("музеи", "musées", "les musées", "des musées"),
    ("семьи", "familles", "les familles", "des familles"),
    ("цветы", "fleurs", "les fleurs", "des fleurs"),
)

RUSSIAN_PHRASE_CASES = (
    ("Это стол.", "C’est une table."),
    ("Я вижу дом.", "Je vois une maison."),
    ("Это новая школа.", "C’est une nouvelle école."),
    ("Женщина читает книгу.", "La femme lit un livre."),
    ("Мужчина открывает окно.", "L’homme ouvre une fenêtre."),
    ("Ребёнок играет в саду.", "L’enfant joue dans le jardin."),
    ("Автомобиль стоит на улице.", "La voiture est dans la rue."),
    ("Поезд прибывает утром.", "Le train arrive le matin."),
    ("Мы слушаем музыку.", "Nous écoutons de la musique."),
    ("Они посещают музей.", "Ils visitent un musée."),
    ("этот стол", "cette table"),
    ("эта книга", "ce livre"),
    ("эти дома", "ces maisons"),
    ("мой компьютер", "mon ordinateur"),
    ("моя машина", "ma voiture"),
    ("наши друзья", "nos amis"),
    ("один мужчина", "un homme"),
    ("одна женщина", "une femme"),
    ("несколько книг", "plusieurs livres"),
    ("много деревьев", "beaucoup d’arbres"),
    ("рядом с домом", "près de la maison"),
    ("возле школы", "près de l’école"),
    ("из офиса", "du bureau"),
    ("в саду", "dans le jardin"),
    ("к музею", "au musée"),
    ("Париж", "Paris"),
    ("Мария", "Marie"),
    ("бежать", "courir"),
    ("красивый", "beau"),
    ("очень быстро", "très vite"),
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
    assert definite.endswith(target)
    assert indefinite.endswith(target)


def test_russian_test_file_matches_automated_article_cases():
    path = Path(__file__).parents[1] / "набор-франс.txt"
    expected_sources = [source for source, *_expected in RUSSIAN_ARTICLE_CASES]

    assert len(expected_sources) == 100
    assert path.read_text(encoding="utf-8").splitlines() == expected_sources


@pytest.mark.parametrize(("source", "translated"), RUSSIAN_PHRASE_CASES)
def test_complete_phrase_set_is_not_modified_by_article_processor(source, translated):
    for mode in (
        FrenchArticleMode.AUTO,
        FrenchArticleMode.DEFINITE,
        FrenchArticleMode.INDEFINITE,
    ):
        assert FrenchGrammarProcessor(mode).process(source, translated) == translated


def test_russian_phrase_file_matches_automated_negative_cases():
    path = Path(__file__).parents[1] / "набор-франс-фразы.txt"
    expected_sources = [source for source, _translated in RUSSIAN_PHRASE_CASES]

    assert len(expected_sources) == 30
    assert path.read_text(encoding="utf-8").splitlines() == expected_sources
