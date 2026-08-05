from gpt01.models import TranslationRow
from gpt01.playback import PlaybackSequence


def test_sequence_starts_on_first_row():
    sequence = PlaybackSequence()
    generation = sequence.start([TranslationRow(2, "hello")])
    assert sequence.active
    assert sequence.current == TranslationRow(2, "hello")
    assert sequence.matches(generation)


def test_sequence_advances_and_completes():
    rows = [TranslationRow(0, "one"), TranslationRow(1, "two")]
    sequence = PlaybackSequence()
    sequence.start(rows)
    assert sequence.advance() == rows[1]
    assert sequence.advance() is None
    assert not sequence.active


def test_stop_invalidates_generation():
    sequence = PlaybackSequence()
    generation = sequence.start([TranslationRow(0, "one")])
    assert sequence.stop()
    assert not sequence.matches(generation)


def test_empty_sequence_does_not_activate():
    sequence = PlaybackSequence()
    sequence.start([])
    assert not sequence.active
