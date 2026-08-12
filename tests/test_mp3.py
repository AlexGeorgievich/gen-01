from gpt01.mp3 import mp3_duration_ms


def _mpeg2_layer3_frame(*, bitrate_index=8, sample_rate_index=1, padding=0):
    header = (
        (0x7FF << 21)
        | (0b10 << 19)
        | (0b01 << 17)
        | (1 << 16)
        | (bitrate_index << 12)
        | (sample_rate_index << 10)
        | (padding << 9)
    )
    bitrate = 64_000
    sample_rate = 24_000
    length = 72 * bitrate // sample_rate + padding
    return header.to_bytes(4, "big") + bytes(length - 4)


def test_mp3_duration_uses_complete_mpeg_frames_and_skips_id3(tmp_path):
    audio = tmp_path / "part.mp3"
    id3 = b"ID3\x04\x00\x00\x00\x00\x00\x00"
    audio.write_bytes(id3 + _mpeg2_layer3_frame() * 10)

    assert mp3_duration_ms(audio) == 240


def test_mp3_duration_returns_none_for_unrecognized_audio(tmp_path):
    audio = tmp_path / "invalid.mp3"
    audio.write_bytes(b"not an mp3")

    assert mp3_duration_ms(audio) is None
