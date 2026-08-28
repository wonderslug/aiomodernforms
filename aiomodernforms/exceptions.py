"""Exceptions for Modern Forms."""


class ModernFormsError(Exception):
    """Generic Modern Forms exception."""


class ModernFormsInvalidSettingsError(ModernFormsError):
    """Modern Forms invalid settings exception."""


class ModernFormsNotSupportedError(ModernFormsError):
    """Raised when a feature isn't supported on a device's generation."""


class ModernFormsNotInitializedError(ModernFormsError):
    """Modern Forms not initialized exception."""


class ModernFormsEmptyResponseError(ModernFormsError):
    """Modern Forms empty API response exception."""


class ModernFormsConnectionError(ModernFormsError):
    """Modern Forms connection exception."""


class ModernFormsConnectionTimeoutError(ModernFormsConnectionError):
    """Modern Forms connection Timeout exception."""
