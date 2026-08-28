"""Exceptions for Modern Forms."""


class ModernFormsError(Exception):
    """Generic Modern Forms exception."""


class ModernFormsInvalidSettingsError(ModernFormsError):
    """Raised when invalid settings are provided."""


class ModernFormsNotSupportedError(ModernFormsError):
    """Raised when a feature isn't supported on a device's generation."""


class ModernFormsNotInitializedError(ModernFormsError):
    """Raised when the device hasn't been initialized via update()."""


class ModernFormsEmptyResponseError(ModernFormsError):
    """Raised when the device returns an empty API response."""


class ModernFormsConnectionError(ModernFormsError):
    """Raised when communication with the device fails."""


class ModernFormsConnectionTimeoutError(ModernFormsConnectionError):
    """Raised when connecting to the device times out."""
