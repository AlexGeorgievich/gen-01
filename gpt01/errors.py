class AppError(Exception):
    """An expected error that can be presented to the user."""


class NetworkServiceError(AppError):
    """A remote translation or speech service is unavailable."""


class StorageError(AppError):
    """A document or application file could not be read or written."""


class OperationCancelled(AppError):
    """The user cancelled a background operation."""

