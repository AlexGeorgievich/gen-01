from gpt01.services import EdgeSpeechProvider
from gpt01.tts import TtsSettings


class FakeCommunicate:
    captured = {}

    def __init__(self, **kwargs):
        type(self).captured = kwargs

    async def save(self, filename):
        with open(filename, "wb") as output:
            output.write(b"mp3")


class FakeStreamingCommunicate:
    captured = {}

    def __init__(self, **kwargs):
        type(self).captured = kwargs

    async def stream(self):
        yield {"type": "audio", "data": b"first"}
        yield {"type": "WordBoundary", "offset": 1_000_000, "duration": 2_000_000}
        yield {"type": "audio", "data": b"second"}


class FlakyCommunicate:
    calls = 0

    def __init__(self, **_kwargs):
        pass

    async def save(self, filename):
        type(self).calls += 1
        with open(filename, "wb") as output:
            output.write(b"incomplete")
        if type(self).calls < 3:
            raise TimeoutError("temporary timeout")
        with open(filename, "wb") as output:
            output.write(b"complete")


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


def test_edge_speech_streams_audio_and_returns_boundary_duration(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "gpt01.services.edge_tts.Communicate",
        FakeStreamingCommunicate,
    )
    output = tmp_path / "timed.mp3"
    provider = EdgeSpeechProvider(timeout=1)

    duration_ms = provider.synthesize_timed(
        "bonjour",
        "fr-FR-DeniseNeural",
        output,
        settings=TtsSettings(rate=5),
    )

    assert output.read_bytes() == b"firstsecond"
    assert duration_ms == 300
    assert FakeStreamingCommunicate.captured["rate"] == "+5%"


def test_edge_speech_retries_timeout_and_removes_incomplete_part(monkeypatch, tmp_path):
    FlakyCommunicate.calls = 0
    monkeypatch.setattr("gpt01.services.edge_tts.Communicate", FlakyCommunicate)
    output = tmp_path / "speech.mp3"
    provider = EdgeSpeechProvider(timeout=1, retry_delays=(0, 0))

    provider.synthesize("hello", "en-US-GuyNeural", output)

    assert FlakyCommunicate.calls == 3
    assert output.read_bytes() == b"complete"
