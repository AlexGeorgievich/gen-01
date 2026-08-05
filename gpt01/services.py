from __future__ import annotations

import asyncio
import re
import time
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
    _ERROR_RESPONSE = re.compile(
        r"(?:\berror\s*[45]\d\d\b|server error|that.?s an error|service unavailable)",
        re.IGNORECASE,
    )

    def __init__(
        self,
        target_language: str = "zh-CN",
        source_language: str = "auto",
        retry_delays: tuple[float, ...] = (0.5, 1.5),
    ) -> None:
        self.target_language = target_language
        self.source_language = source_language
        self.retry_delays = retry_delays

    def translate(self, text: str, cancelled: Callable[[], bool] | None = None) -> str:
        try:
            translator = GoogleTranslator(
                source=self.source_language, target=self.target_language
            )
            translated: list[str] = []
            for chunk in split_text(text):
                if cancelled and cancelled():
                    raise OperationCancelled("Перевод отменён.")
                translated.append(self._translate_with_retry(translator, chunk, cancelled))
            return "".join(translated)
        except OperationCancelled:
            raise
        except Exception as exc:
            raise NetworkServiceError(f"Сервис перевода недоступен: {exc}") from exc

    def _translate_with_retry(
        self,
        translator: GoogleTranslator,
        chunk: str,
        cancelled: Callable[[], bool] | None,
    ) -> str:
        attempts = len(self.retry_delays) + 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            if cancelled and cancelled():
                raise OperationCancelled("Перевод отменён.")
            try:
                response = str(translator.translate(chunk) or "").strip()
                if not response or self._ERROR_RESPONSE.search(response):
                    raise RuntimeError("сервер вернул ошибочный ответ вместо перевода")
                return response
            except Exception as exc:
                last_error = exc
                if attempt >= len(self.retry_delays):
                    break
                self._cooperative_wait(self.retry_delays[attempt], cancelled)
        raise NetworkServiceError(
            f"Сервис перевода не ответил после {attempts} попыток: {last_error}"
        ) from last_error

    @staticmethod
    def _cooperative_wait(
        delay: float, cancelled: Callable[[], bool] | None = None
    ) -> None:
        deadline = time.monotonic() + max(0.0, delay)
        while time.monotonic() < deadline:
            if cancelled and cancelled():
                raise OperationCancelled("Перевод отменён.")
            time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))


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
