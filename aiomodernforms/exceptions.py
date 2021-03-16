"""Exceptions for Modern Forms."""


class ModernFormsError(Exception):
    """Generic Modern Forms exception."""


class ModernFormsInvalidSettingsError(Exception):
    """Modern Forms Not InvalidSettings exception."""


class ModernFormsNotInitializedError(Exception):
    """Modern Forms Not InvalidSettings exception."""


class ModernFormsEmptyResponseError(Exception):
    """Modern Forms empty API response exception."""


class ModernFormsConnectionError(ModernFormsError):
    """Modern Forms connection exception."""


class ModernFormsConnectionTimeoutError(ModernFormsConnectionError):
    """Modern Forms connection Timeout exception."""
