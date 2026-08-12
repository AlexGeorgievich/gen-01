from __future__ import annotations

from pathlib import Path

_BITRATES = {
    (1, 3): (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320),
    (2, 3): (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160),
}
_SAMPLE_RATES = {
    1: (44100, 48000, 32000),
    2: (22050, 24000, 16000),
    25: (11025, 12000, 8000),
}


def mp3_duration_ms(path: Path) -> int | None:
    """Return duration from MPEG audio frames, without external decoders."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    offset = _skip_id3v2(data)
    total_samples_over_rate = 0.0
    frames = 0
    while offset + 4 <= len(data):
        header = int.from_bytes(data[offset : offset + 4], "big")
        parsed = _parse_frame_header(header)
        if parsed is None:
            offset += 1
            continue
        frame_length, samples, sample_rate = parsed
        if offset + frame_length > len(data):
            break
        total_samples_over_rate += samples / sample_rate
        frames += 1
        offset += frame_length
    if not frames:
        return None
    return max(1, round(total_samples_over_rate * 1000))


def _skip_id3v2(data: bytes) -> int:
    if len(data) < 10 or data[:3] != b"ID3":
        return 0
    size = 0
    for byte in data[6:10]:
        if byte & 0x80:
            return 0
        size = (size << 7) | byte
    return min(len(data), 10 + size)


def _parse_frame_header(header: int) -> tuple[int, int, int] | None:
    if header >> 21 != 0x7FF:
        return None
    version_bits = (header >> 19) & 0b11
    layer_bits = (header >> 17) & 0b11
    bitrate_index = (header >> 12) & 0b1111
    sample_rate_index = (header >> 10) & 0b11
    padding = (header >> 9) & 1
    if layer_bits != 0b01 or bitrate_index in {0, 15} or sample_rate_index == 3:
        return None
    version = {0b11: 1, 0b10: 2, 0b00: 25}.get(version_bits)
    if version is None:
        return None
    bitrate_group = 1 if version == 1 else 2
    bitrate = _BITRATES[(bitrate_group, 3)][bitrate_index] * 1000
    sample_rate = _SAMPLE_RATES[version][sample_rate_index]
    samples = 1152 if version == 1 else 576
    coefficient = 144 if version == 1 else 72
    frame_length = coefficient * bitrate // sample_rate + padding
    if frame_length < 4:
        return None
    return frame_length, samples, sample_rate
