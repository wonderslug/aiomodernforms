"""Mutable dynamic-shadow state for the mock fan, and command validation."""

from __future__ import annotations

from collections.abc import Callable

from aiomodernforms.const import (
    COMMAND_ADAPTIVE_LEARNING,
    COMMAND_AWAY_MODE,
    COMMAND_DECOMMISSION,
    COMMAND_FACTORY_RESET,
    COMMAND_FAN_DIRECTION,
    COMMAND_FAN_POWER,
    COMMAND_FAN_SLEEP_TIMER,
    COMMAND_FAN_SPEED,
    COMMAND_FAN_TIMER,
    COMMAND_LIGHT_BRIGHTNESS,
    COMMAND_LIGHT_POWER,
    COMMAND_LIGHT_SLEEP_TIMER,
    COMMAND_LIGHT_TIMER,
    COMMAND_RESET_RF_PAIR_LIST,
    COMMAND_RF_PAIR_MODE,
    COMMAND_SCHEDULE,
    COMMAND_WIND,
    COMMAND_WIND_SPEED,
    FAN_DIRECTION_FORWARD,
    FAN_DIRECTION_REVERSE,
    FAN_SPEED_HIGH_VALUE,
    FAN_SPEED_LOW_VALUE,
    LIGHT_BRIGHTNESS_HIGH_VALUE,
    LIGHT_BRIGHTNESS_LOW_VALUE,
    WIND_SPEED_HIGH_VALUE,
    WIND_SPEED_LOW_VALUE,
)

from .generations import GenerationProfile


def _is_bool(value: object) -> bool:
    """Return whether value is strictly a bool."""
    return isinstance(value, bool)


def _is_non_negative_int(value: object) -> bool:
    """Return whether value is a non-negative int (bools excluded)."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_int_in_range(low: int, high: int) -> Callable[[object], bool]:
    """Build a validator for an int within [low, high], excluding bools."""

    def _validate(value: object) -> bool:
        return (
            isinstance(value, int)
            and not isinstance(value, bool)
            and low <= value <= high
        )

    return _validate


def _is_one_of(*choices: str) -> Callable[[object], bool]:
    """Build a validator that accepts only the given string choices."""
    return lambda value: value in choices


def _is_str(value: object) -> bool:
    """Return whether value is a string."""
    return isinstance(value, str)


def _initial_shadow(
    profile: GenerationProfile, breeze: bool, light: bool
) -> dict[str, object]:
    """Build the startup dynamic shadow dict for a profile."""
    shadow: dict[str, object] = {
        COMMAND_FAN_POWER: False,
        COMMAND_FAN_SPEED: 3,
        COMMAND_FAN_DIRECTION: FAN_DIRECTION_FORWARD,
        COMMAND_AWAY_MODE: False,
        COMMAND_ADAPTIVE_LEARNING: False,
        COMMAND_RF_PAIR_MODE: False,
        COMMAND_RESET_RF_PAIR_LIST: False,
        COMMAND_FACTORY_RESET: False,
        COMMAND_DECOMMISSION: False,
        COMMAND_SCHEDULE: "",
    }
    if light:
        shadow[COMMAND_LIGHT_POWER] = False
        shadow[COMMAND_LIGHT_BRIGHTNESS] = 50
    if profile.uses_relative_timers:
        shadow[COMMAND_FAN_TIMER] = 0
        if light:
            shadow[COMMAND_LIGHT_TIMER] = 0
    else:
        shadow[COMMAND_FAN_SLEEP_TIMER] = 0
        if light:
            shadow[COMMAND_LIGHT_SLEEP_TIMER] = 0
    if breeze:
        shadow[COMMAND_WIND] = False
        shadow[COMMAND_WIND_SPEED] = 2
    return shadow


def _build_validators(
    profile: GenerationProfile, breeze: bool, light: bool
) -> dict[str, Callable[[object], bool]]:
    """Build the per-field validator map for a profile/breeze/light combination."""
    validators: dict[str, Callable[[object], bool]] = {
        COMMAND_FAN_POWER: _is_bool,
        COMMAND_AWAY_MODE: _is_bool,
        COMMAND_ADAPTIVE_LEARNING: _is_bool,
        COMMAND_RF_PAIR_MODE: _is_bool,
        COMMAND_RESET_RF_PAIR_LIST: _is_bool,
        COMMAND_FAN_SPEED: _is_int_in_range(FAN_SPEED_LOW_VALUE, FAN_SPEED_HIGH_VALUE),
        COMMAND_FAN_DIRECTION: _is_one_of(FAN_DIRECTION_FORWARD, FAN_DIRECTION_REVERSE),
        COMMAND_SCHEDULE: _is_str,
    }
    if light:
        validators[COMMAND_LIGHT_POWER] = _is_bool
        validators[COMMAND_LIGHT_BRIGHTNESS] = _is_int_in_range(
            LIGHT_BRIGHTNESS_LOW_VALUE, LIGHT_BRIGHTNESS_HIGH_VALUE
        )
    if profile.uses_relative_timers:
        validators[COMMAND_FAN_TIMER] = _is_non_negative_int
        if light:
            validators[COMMAND_LIGHT_TIMER] = _is_non_negative_int
    else:
        validators[COMMAND_FAN_SLEEP_TIMER] = _is_non_negative_int
        if light:
            validators[COMMAND_LIGHT_SLEEP_TIMER] = _is_non_negative_int
    if breeze:
        validators[COMMAND_WIND] = _is_bool
        validators[COMMAND_WIND_SPEED] = _is_int_in_range(
            WIND_SPEED_LOW_VALUE, WIND_SPEED_HIGH_VALUE
        )
    return validators


class FanState:
    """Holds and mutates a mock fan's dynamic shadow state."""

    def __init__(
        self, profile: GenerationProfile, breeze: bool, light: bool = True
    ) -> None:
        """Initialize state with startup defaults for the given profile."""
        self._profile = profile
        self._breeze = breeze
        self._light = light
        self._validators = _build_validators(profile, breeze, light)
        self._shadow = _initial_shadow(profile, breeze, light)

    def snapshot(self) -> dict[str, object]:
        """Return a copy of the current dynamic shadow dict."""
        return dict(self._shadow)

    def reset(self) -> None:
        """Reset the dynamic shadow to startup defaults."""
        self._shadow = _initial_shadow(self._profile, self._breeze, self._light)

    def apply_commands(self, commands: dict[str, object]) -> dict[str, object]:
        """Validate and apply command fields, returning the full updated shadow.

        Invalid values (out of range, wrong type, or breeze-only/light-only
        fields on a fan without that capability) are silently ignored rather
        than erroring, mirroring how embedded firmware is expected to no-op
        bad input rather than return an HTTP error the API reference doesn't
        document.
        """
        for key, value in commands.items():
            validator = self._validators.get(key)
            if validator is not None and validator(value):
                self._shadow[key] = value
        return self.snapshot()
