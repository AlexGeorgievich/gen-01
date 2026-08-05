from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .errors import AppError, OperationCancelled, StorageError
from .languages import LanguageProfile
from .models import Document
from .services import TranslationProvider
from .session import SessionRepository
from .storage import load_document, save_document
from .structured_translation import translate_preserving_layout
from .transcription import transcribe

BatchProgress = Callable[[int, int, str], None]


@dataclass(frozen=True, slots=True)
class BatchItemResult:
    source: Path
    output: Path | None = None
    error: str = ""

    @property
    def succeeded(self) -> bool:
        return self.output is not None and not self.error


@dataclass(frozen=True, slots=True)
class BatchResult:
    items: tuple[BatchItemResult, ...]

    @property
    def succeeded(self) -> tuple[BatchItemResult, ...]:
        return tuple(item for item in self.items if item.succeeded)

    @property
    def failed(self) -> tuple[BatchItemResult, ...]:
        return tuple(item for item in self.items if not item.succeeded)


class BatchProcessor:
    """Translate multiple source documents into unique language-specific TXT files."""

    def __init__(
        self,
        repository: SessionRepository,
        profile: LanguageProfile,
        translator: TranslationProvider,
    ) -> None:
        self.repository = repository
        self.profile = profile
        self.translator = translator

    def process(
        self,
        paths: Sequence[Path],
        cancelled: Callable[[], bool] | None = None,
        progress: BatchProgress | None = None,
    ) -> BatchResult:
        total = len(paths)
        results: list[BatchItemResult] = []
        reserved_outputs: set[str] = set()
        if progress:
            progress(0, total, f"Подготовлено файлов: {total}")

        for index, source in enumerate(paths, start=1):
            if cancelled and cancelled():
                raise OperationCancelled("Пакетная обработка остановлена.")
            if progress:
                progress(index - 1, total, f"Файл {index} из {total}: {source.name}")
            try:
                document = load_document(source)
                if not document.original.strip():
                    raise StorageError("исходный текст пуст")
                translated = translate_preserving_layout(
                    document.original,
                    self.translator,
                    cancelled,
                ).text
                transcription = transcribe(translated, self.profile.transcription_mode)
                output = self._unique_output(source.stem, reserved_outputs)
                save_document(output, Document(document.original, translated, transcription))
                reserved_outputs.add(str(output.resolve()).casefold())
                results.append(BatchItemResult(source=source, output=output))
            except OperationCancelled:
                raise
            except (AppError, OSError) as exc:
                results.append(BatchItemResult(source=source, error=str(exc)))
            if progress:
                progress(index, total, f"Обработано файлов: {index} из {total}")

        return BatchResult(tuple(results))

    def _unique_output(self, stem: str, reserved: set[str]) -> Path:
        candidate = self.repository.export_path(self.profile, stem, ".txt")
        counter = 2
        while candidate.exists() or str(candidate.resolve()).casefold() in reserved:
            candidate = candidate.with_name(f"{candidate.stem}_{counter}{candidate.suffix}")
            counter += 1
        return candidate
