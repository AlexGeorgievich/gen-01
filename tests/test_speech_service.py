from gpt01.services import EdgeSpeechProvider
from gpt01.tts import TtsSettings


class FakeCommunicate:
    captured = {}

    def __init__(self, **kwargs):
        type(self).captured = kwargs

    async def save(self, filename):
        with open(filename, "wb") as output:
            output.write(b"mp3")


def test_edge_speech_receives_tts_settings(monkeypatch, tmp_path):
    monkeypatch.setattr("gpt01.services.edge_tts.Communicate", FakeCommunicate)
    output = tmp_path / "speech.mp3"
    provider = EdgeSpeechProvider(timeout=1)

    provider.synthesize(
        "bonjour",
        "fr-FR-DeniseNeural",
        output,
        settings=TtsSettings(rate=20, pitch=-5, volume=15),
    )

    assert output.read_bytes() == b"mp3"
    assert FakeCommunicate.captured == {
        "text": "bonjour",
        "voice": "fr-FR-DeniseNeural",
        "rate": "+20%",
        "pitch": "-5Hz",
        "volume": "+15%",
    }
