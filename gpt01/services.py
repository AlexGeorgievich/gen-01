from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import edge_tts
from deep_translator import GoogleTranslator

from .errors import NetworkServiceError, OperationCancelled
from .text import split_text


class TranslationProvider(Protocol):
    def translate(self, text: str, cancelled: Callable[[], bool] | None = None) -> str: ...


class SpeechProvider(Protocol):
    def synthesize(
        self,
        text: str,
        voice: str,
        output: Path,
        cancelled: Callable[[], bool] | None = None,
    ) -> None: ...


class GoogleTranslationProvider:
    def translate(self, text: str, cancelled: Callable[[], bool] | None = None) -> str:
        try:
            translator = GoogleTranslator(source="auto", target="zh-CN")
            translated: list[str] = []
            for chunk in split_text(text):
                if cancelled and cancelled():
                    raise OperationCancelled("Перевод отменён.")
                translated.append(translator.translate(chunk))
            return "".join(translated)
        except OperationCancelled:
            raise
        except Exception as exc:
            raise NetworkServiceError(f"Сервис перевода недоступен: {exc}") from exc


class EdgeSpeechProvider:
    def __init__(self, timeout: int = 90) -> None:
        self.timeout = timeout

    def synthesize(
        self,
        text: str,
        voice: str,
        output: Path,
        cancelled: Callable[[], bool] | None = None,
    ) -> None:
        async def run() -> None:
            await asyncio.wait_for(
                edge_tts.Communicate(text=text, voice=voice).save(str(output)),
                timeout=self.timeout,
            )

        try:
            if cancelled and cancelled():
                raise OperationCancelled("Синтез речи отменён.")
            asyncio.run(run())
            if cancelled and cancelled():
                output.unlink(missing_ok=True)
                raise OperationCancelled("Синтез речи отменён.")
        except OperationCancelled:
            output.unlink(missing_ok=True)
            raise
        except Exception as exc:
            output.unlink(missing_ok=True)
            raise NetworkServiceError(f"Сервис синтеза речи недоступен: {exc}") from exc
