from gpt01.tts import TtsSettings


def test_tts_settings_format_edge_options():
    settings = TtsSettings(rate=15, pitch=-8, volume=20)

    assert settings.edge_options() == {
        "rate": "+15%",
        "pitch": "-8Hz",
        "volume": "+20%",
    }


def test_tts_settings_are_clamped():
    assert TtsSettings.normalized(500, -500, "bad") == TtsSettings(100, -100, 0)
