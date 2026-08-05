from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

TranscriptionMode = Literal["latin", "romaji", "pinyin"]


@dataclass(frozen=True, slots=True)
class LanguageProfile:
    key: str
    label: str
    translation_code: str
    file_suffix: str
    voice_prefix: str
    transcription_mode: TranscriptionMode
    default_voice: str
    fallback_voices: tuple[dict[str, str], ...]


LANGUAGES: tuple[LanguageProfile, ...] = (
    LanguageProfile(
        key="French",
        label="French",
        translation_code="fr",
        file_suffix="fr",
        voice_prefix="fr-",
        transcription_mode="latin",
        default_voice="fr-FR-DeniseNeural",
        fallback_voices=(
            {"ShortName": "fr-FR-DeniseNeural", "Locale": "fr-FR", "Gender": "Female"},
            {"ShortName": "fr-FR-HenriNeural", "Locale": "fr-FR", "Gender": "Male"},
        ),
    ),
    LanguageProfile(
        key="Spanish",
        label="Spanish",
        translation_code="es",
        file_suffix="es",
        voice_prefix="es-",
        transcription_mode="latin",
        default_voice="es-ES-ElviraNeural",
        fallback_voices=(
            {"ShortName": "es-ES-ElviraNeural", "Locale": "es-ES", "Gender": "Female"},
            {"ShortName": "es-ES-AlvaroNeural", "Locale": "es-ES", "Gender": "Male"},
        ),
    ),
    LanguageProfile(
        key="Japan",
        label="Japan",
        translation_code="ja",
        file_suffix="jp",
        voice_prefix="ja-",
        transcription_mode="romaji",
        default_voice="ja-JP-NanamiNeural",
        fallback_voices=(
            {"ShortName": "ja-JP-NanamiNeural", "Locale": "ja-JP", "Gender": "Female"},
            {"ShortName": "ja-JP-KeitaNeural", "Locale": "ja-JP", "Gender": "Male"},
        ),
    ),
    LanguageProfile(
        key="Chine",
        label="Chine",
        translation_code="zh-CN",
        file_suffix="zh",
        voice_prefix="zh-",
        transcription_mode="pinyin",
        default_voice="zh-CN-XiaoxiaoNeural",
        fallback_voices=(
            {"ShortName": "zh-CN-XiaoxiaoNeural", "Locale": "zh-CN", "Gender": "Female"},
            {"ShortName": "zh-CN-YunxiNeural", "Locale": "zh-CN", "Gender": "Male"},
            {"ShortName": "zh-CN-YunjianNeural", "Locale": "zh-CN", "Gender": "Male"},
            {"ShortName": "zh-CN-XiaoyiNeural", "Locale": "zh-CN", "Gender": "Female"},
            {"ShortName": "zh-HK-HiuGaaiNeural", "Locale": "zh-HK", "Gender": "Female"},
            {"ShortName": "zh-TW-HsiaoChenNeural", "Locale": "zh-TW", "Gender": "Female"},
        ),
    ),
)

LANGUAGE_BY_KEY = {profile.key: profile for profile in LANGUAGES}
DEFAULT_LANGUAGE_KEY = "Chine"


def get_language(key: str) -> LanguageProfile:
    return LANGUAGE_BY_KEY.get(key, LANGUAGE_BY_KEY[DEFAULT_LANGUAGE_KEY])


def load_selected_language(path: Path) -> str:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        key = str(data.get("selected_language", ""))
        return key if key in LANGUAGE_BY_KEY else DEFAULT_LANGUAGE_KEY
    except (OSError, ValueError, TypeError):
        return DEFAULT_LANGUAGE_KEY


def save_selected_language(path: Path, key: str) -> None:
    selected = key if key in LANGUAGE_BY_KEY else DEFAULT_LANGUAGE_KEY
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps({"selected_language": selected}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)
