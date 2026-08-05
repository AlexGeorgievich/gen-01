import json

from gpt01.state import AppState, load_app_state, save_app_state


def test_state_round_trip(tmp_path):
    path = tmp_path / "state.json"
    expected = AppState(
        original="source",
        translation="你好",
        transcription="nǐ hǎo",
        selected_voice="zh-CN-XiaoxiaoNeural",
        transcription_visible=False,
        splitter_sizes=[600, 0, 600],
        window_geometry="Z2VvbWV0cnk=",
        volume=0.5,
        current_source_path="example.txt",
        audio_file="last_audio.mp3",
        tts_rate=20,
        tts_pitch=-10,
        tts_volume=15,
    )
    save_app_state(path, expected)
    assert load_app_state(path) == expected


def test_state_is_saved_as_readable_utf8_json(tmp_path):
    path = tmp_path / "state.json"
    save_app_state(path, AppState(translation="你好"))
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["translation"] == "你好"


def test_missing_state_returns_defaults(tmp_path):
    assert load_app_state(tmp_path / "missing.json") == AppState()


def test_corrupt_state_returns_defaults(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("not json", encoding="utf-8")
    assert load_app_state(path) == AppState()


def test_volume_is_clamped_when_loading(tmp_path):
    path = tmp_path / "state.json"
    path.write_text('{"volume": 12}', encoding="utf-8")
    assert load_app_state(path).volume == 1.0


def test_legacy_visibility_field_is_supported(tmp_path):
    path = tmp_path / "state.json"
    path.write_text('{"translation_visible": false}', encoding="utf-8")
    assert load_app_state(path).transcription_visible is False


def test_tts_settings_are_clamped_when_loading(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(
        '{"tts_rate": 900, "tts_pitch": -900, "tts_volume": "invalid"}',
        encoding="utf-8",
    )

    assert load_app_state(path).tts_settings.edge_options() == {
        "rate": "+100%",
        "pitch": "-100Hz",
        "volume": "+0%",
    }
