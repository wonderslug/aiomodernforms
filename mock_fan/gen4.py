"""Gen4 (WAC IoT /device + /fixture protocol) fixture data and mutable state."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from aiomodernforms.const import (
    COMMAND_FAN_DIRECTION,
    COMMAND_FAN_SPEED,
    COMMAND_WIND,
    COMMAND_WIND_SPEED,
    FAN_SPEED_HIGH_VALUE,
    FAN_SPEED_LOW_VALUE,
    GEN4_DEVICE_IOTM_VER,
    GEN4_DEVICE_NAME,
    GEN4_DEVICE_NWK_STATE,
    GEN4_DEVICE_OWNER,
    GEN4_DEVICE_SCM_VER,
    GEN4_DEVICE_STA_MAC,
    GEN4_DEVICE_SYSTEM_TYPE,
    GEN4_FIELD_ADDR,
    GEN4_FIELD_DETAIL,
    GEN4_FIELD_FINDME,
    GEN4_FIELD_LEVEL,
    GEN4_FIELD_MAX_COLOR_TEMP,
    GEN4_FIELD_MIN_COLOR_TEMP,
    GEN4_FIELD_MIX_COLOR_TEMP,
    GEN4_FIELD_MODEL,
    GEN4_FIELD_NAME,
    GEN4_FIELD_STATE,
    GEN4_FIELD_STATUS,
    GEN4_FIELD_TYPE,
    GEN4_FIXTURE_TYPE_FAN,
    GEN4_NWK_CERTIFICATE_ID,
    GEN4_NWK_RSSI,
    STATE_AWAY_MODE,
    WIND_SPEED_HIGH_VALUE,
    WIND_SPEED_LOW_VALUE,
)

# Fixed test addresses this mock assigns itself. Never computed from a MAC
# or anything else — the device (real or mock) is always the sole source of
# truth for its own fixture addresses.
FAN_ADDR = 100
_FIRST_LIGHT_ADDR = 200

# Tunable white (CCT) — the only light-fixture type the real Modern Forms
# Gen4 reference hardware has been observed reporting.
LIGHT_FIXTURE_TYPE = 1

DEVICE_NAME = "Mock Gen4 Fan"
_MOCK_CERTIFICATE_ID = "mockgen4certificateid00000000000000000000000000000000000000"
_MOCK_STA_MAC = "AA:BB:CC:00:11:22"
_MOCK_FAN_MODEL = "2603-56"


def _is_bool(value: object) -> bool:
    """Return whether value is strictly a bool."""
    return isinstance(value, bool)


def _is_int_in_range(low: int, high: int) -> Callable[[object], bool]:
    """Build a validator for an int within [low, high], excluding bools."""

    def _validate(value: object) -> bool:
        return (
            isinstance(value, int)
            and not isinstance(value, bool)
            and low <= value <= high
        )

    return _validate


_FAN_VALIDATORS: dict[str, Callable[[object], bool]] = {
    GEN4_FIELD_STATUS: _is_bool,
    COMMAND_FAN_SPEED: _is_int_in_range(FAN_SPEED_LOW_VALUE, FAN_SPEED_HIGH_VALUE),
    COMMAND_FAN_DIRECTION: _is_bool,
    COMMAND_WIND: _is_bool,
    COMMAND_WIND_SPEED: _is_int_in_range(WIND_SPEED_LOW_VALUE, WIND_SPEED_HIGH_VALUE),
    GEN4_FIELD_FINDME: _is_bool,
}

_LIGHT_VALIDATORS: dict[str, Callable[[object], bool]] = {
    GEN4_FIELD_STATUS: _is_bool,
    GEN4_FIELD_LEVEL: _is_int_in_range(1, 10000),
    GEN4_FIELD_MIX_COLOR_TEMP: _is_int_in_range(2700, 6500),
    GEN4_FIELD_FINDME: _is_bool,
}


@dataclass
class Fixture:
    """One addressable Gen4 fixture (the fan, or a light)."""

    address: int
    fixture_type: int
    name: str
    state: dict[str, object]
    detail: dict[str, object] = field(default_factory=dict)
    validators: dict[str, Callable[[object], bool]] = field(default_factory=dict)

    def apply_commands(self, commands: dict[str, object]) -> dict[str, object]:
        """Validate and apply command fields, returning only the changed keys.

        Invalid values are silently ignored rather than erroring, mirroring
        how embedded firmware is expected to no-op bad input (matching the
        existing legacy FanState.apply_commands() convention).
        """
        changed: dict[str, object] = {}
        for key, value in commands.items():
            validator = self.validators.get(key)
            if validator is not None and validator(value):
                self.state[key] = value
                changed[key] = value
        return changed

    def as_wire_dict(self) -> dict[str, object]:
        """Return this fixture's full /fixture read-all element."""
        result: dict[str, object] = {
            GEN4_FIELD_ADDR: self.address,
            GEN4_FIELD_NAME: self.name,
            GEN4_FIELD_TYPE: self.fixture_type,
            GEN4_FIELD_STATE: dict(self.state),
        }
        if self.detail:
            result[GEN4_FIELD_DETAIL] = dict(self.detail)
        return result


def _initial_fan_state() -> dict[str, object]:
    """Build the startup state dict for the fan fixture."""
    return {
        GEN4_FIELD_STATUS: False,
        COMMAND_FAN_SPEED: 3,
        COMMAND_FAN_DIRECTION: False,
        COMMAND_WIND: False,
        COMMAND_WIND_SPEED: 2,
    }


def _initial_light_state() -> dict[str, object]:
    """Build the startup state dict for one light fixture."""
    return {
        GEN4_FIELD_STATUS: False,
        GEN4_FIELD_LEVEL: 5000,
        GEN4_FIELD_MIX_COLOR_TEMP: 3000,
    }


class Gen4FanState:
    """Holds and mutates a mock Gen4 fan's fixtures (the fan + N lights)."""

    def __init__(self, lights: int = 1) -> None:
        """Initialize the fan and `lights` light fixtures at startup defaults."""
        self.away_mode_enabled = False
        self.fan = Fixture(
            address=FAN_ADDR,
            fixture_type=GEN4_FIXTURE_TYPE_FAN,
            name="Fan",
            state=_initial_fan_state(),
            detail={GEN4_FIELD_MODEL: _MOCK_FAN_MODEL},
            validators=_FAN_VALIDATORS,
        )
        self.lights: list[Fixture] = [
            Fixture(
                address=_FIRST_LIGHT_ADDR + i,
                fixture_type=LIGHT_FIXTURE_TYPE,
                name=f"Light {i + 1}",
                state=_initial_light_state(),
                detail={
                    GEN4_FIELD_MIN_COLOR_TEMP: 2700,
                    GEN4_FIELD_MAX_COLOR_TEMP: 6500,
                },
                validators=_LIGHT_VALIDATORS,
            )
            for i in range(lights)
        ]

    def all_fixtures(self) -> list[Fixture]:
        """Return the fan and every light, in address order."""
        return [self.fan, *self.lights]

    def find(self, address: int) -> Fixture | None:
        """Return the fixture at the given address, or None if unknown."""
        for fixture in self.all_fixtures():
            if fixture.address == address:
                return fixture
        return None

    def reset(self) -> None:
        """Reset all fixtures and away mode to startup defaults."""
        self.away_mode_enabled = False
        self.fan.state = _initial_fan_state()
        for light in self.lights:
            light.state = _initial_light_state()


def device_data(away_mode_enabled: bool) -> dict[str, object]:
    """Build the /device response dict for the given away-mode value."""
    return {
        GEN4_DEVICE_SYSTEM_TYPE: "fan_g4",
        GEN4_DEVICE_NAME: DEVICE_NAME,
        GEN4_DEVICE_OWNER: "mock@example.com",
        GEN4_DEVICE_IOTM_VER: "01.00.0082",
        GEN4_DEVICE_SCM_VER: "01.00.0012",
        GEN4_DEVICE_STA_MAC: _MOCK_STA_MAC,
        STATE_AWAY_MODE: away_mode_enabled,
        GEN4_DEVICE_NWK_STATE: {
            GEN4_NWK_CERTIFICATE_ID: _MOCK_CERTIFICATE_ID,
            GEN4_NWK_RSSI: "-42",
        },
    }
