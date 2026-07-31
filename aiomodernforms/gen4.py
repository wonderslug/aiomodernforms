"""Translate between the Gen4 WAC IoT wire protocol and canonical dicts.

Gen4 fans speak the WAC IoT `/device` + `/fixture` REST model instead of
Gen 1/2/3's flat `/mf` shadow. Every function here is a pure translation
step — no HTTP happens in this module; `ModernFormsDevice` is the only
thing that makes requests.
"""

from __future__ import annotations

from typing import Any

from .const import (
    COMMAND_FAN_DIRECTION,
    COMMAND_FAN_POWER,
    COMMAND_FAN_SPEED,
    COMMAND_IDENTIFY,
    COMMAND_LIGHT_BRIGHTNESS,
    COMMAND_LIGHT_COLOR_TEMP,
    COMMAND_LIGHT_POWER,
    COMMAND_WIND,
    COMMAND_WIND_SPEED,
    DEFAULT_WIND_SPEED,
    FAN_DIRECTION_FORWARD,
    FAN_DIRECTION_REVERSE,
    FAN_SPEED_LOW_VALUE,
    GEN4_BRIGHTNESS_SCALE,
    GEN4_DEVICE_IOTM_VER,
    GEN4_DEVICE_NAME,
    GEN4_DEVICE_OWNER,
    GEN4_DEVICE_SCM_VER,
    GEN4_DEVICE_STA_MAC,
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
    GEN4_LIGHT_FIXTURE_TYPES,
    GEN4_SYSTEM_TYPE_MARKERS,
    INFO_DEVICE_NAME,
    INFO_FAN_TYPE,
    INFO_FIRMWARE_VERSION,
    INFO_LIGHT_TYPE,
    INFO_MAC,
    INFO_MAIN_MCU_FIRMWARE_VERSION,
    INFO_OWNER,
    LIGHT_BRIGHTNESS_HIGH_VALUE,
    STATE_AWAY_MODE,
    STATE_FAN_DIRECTION,
    STATE_FAN_POWER,
    STATE_FAN_SPEED,
    STATE_LIGHT_BRIGHTNESS,
    STATE_LIGHT_COLOR_TEMP,
    STATE_LIGHT_FIXTURES,
    STATE_LIGHT_POWER,
    STATE_WIND_POWER,
    STATE_WIND_SPEED,
)
from .models import Light


def is_gen4_system_type(system_type: str) -> bool:
    """Return True if a /device systemType value identifies a Gen4 fan."""
    lowered = system_type.lower()
    return any(marker in lowered for marker in GEN4_SYSTEM_TYPE_MARKERS)


def classify_fixtures(
    fixtures: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Split a /fixture read-all response into (fan fixture, light fixtures).

    Fixture types this library doesn't model (e.g. a Wall Station) are
    ignored. If more than one fan-typed fixture is present, the first wins.
    """
    fan_fixture: dict[str, Any] | None = None
    light_fixtures: list[dict[str, Any]] = []
    for fixture in fixtures:
        fixture_type = fixture.get(GEN4_FIELD_TYPE)
        if fixture_type == GEN4_FIXTURE_TYPE_FAN and fan_fixture is None:
            fan_fixture = fixture
        elif fixture_type in GEN4_LIGHT_FIXTURE_TYPES:
            light_fixtures.append(fixture)
    return fan_fixture, light_fixtures


def _light_from_fixture(fixture: dict[str, Any]) -> Light:
    """Build a canonical Light from one raw /fixture read-all element."""
    state = fixture.get(GEN4_FIELD_STATE) or {}
    detail = fixture.get(GEN4_FIELD_DETAIL) or {}
    default_level = LIGHT_BRIGHTNESS_HIGH_VALUE * GEN4_BRIGHTNESS_SCALE
    raw_level = state.get(GEN4_FIELD_LEVEL, default_level)
    if not isinstance(raw_level, (int, float)) or isinstance(raw_level, bool):
        # A misbehaving device sending a non-numeric level (string, null)
        # shouldn't crash translation for the whole device — fall back to
        # the same default as a missing key.
        raw_level = default_level
    brightness = max(1, min(100, round(raw_level / GEN4_BRIGHTNESS_SCALE)))
    return Light(
        address=fixture.get(GEN4_FIELD_ADDR),
        fixture_type=fixture.get(GEN4_FIELD_TYPE),
        name=fixture.get(GEN4_FIELD_NAME, ""),
        on=state.get(GEN4_FIELD_STATUS, False),
        brightness=brightness,
        color_temp_kelvin=state.get(GEN4_FIELD_MIX_COLOR_TEMP),
        min_color_temp_kelvin=detail.get(GEN4_FIELD_MIN_COLOR_TEMP),
        max_color_temp_kelvin=detail.get(GEN4_FIELD_MAX_COLOR_TEMP),
    )


def build_state_data(
    device_data: dict[str, Any],
    fan_fixture: dict[str, Any] | None,
    light_fixtures: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a canonical state dict from Gen4's /device + /fixture responses.

    This is the same shape State.from_dict() already expects from a legacy
    /mf response — models.py doesn't need to know Gen4's wire format exists.
    """
    fan_state = (fan_fixture or {}).get(GEN4_FIELD_STATE) or {}
    lights = [_light_from_fixture(fixture) for fixture in light_fixtures]
    primary = (
        lights[0]
        if lights
        else Light(
            address=None,
            fixture_type=None,
            name="",
            on=False,
            brightness=LIGHT_BRIGHTNESS_HIGH_VALUE,
            color_temp_kelvin=None,
            min_color_temp_kelvin=None,
            max_color_temp_kelvin=None,
        )
    )

    # fanDirection's key name is identical on both wire formats; only its
    # value differs (gen4: bool, True=reverse; legacy: "forward"/"reverse").
    raw_direction = fan_state.get(COMMAND_FAN_DIRECTION, False)
    direction = FAN_DIRECTION_REVERSE if raw_direction else FAN_DIRECTION_FORWARD

    return {
        STATE_FAN_POWER: fan_state.get(GEN4_FIELD_STATUS, False),
        STATE_FAN_SPEED: fan_state.get(COMMAND_FAN_SPEED, FAN_SPEED_LOW_VALUE),
        STATE_FAN_DIRECTION: direction,
        STATE_WIND_POWER: fan_state.get(COMMAND_WIND),
        STATE_WIND_SPEED: fan_state.get(COMMAND_WIND_SPEED, DEFAULT_WIND_SPEED),
        STATE_AWAY_MODE: device_data.get(STATE_AWAY_MODE, False),
        STATE_LIGHT_POWER: primary.on,
        STATE_LIGHT_BRIGHTNESS: primary.brightness,
        STATE_LIGHT_COLOR_TEMP: primary.color_temp_kelvin,
        STATE_LIGHT_FIXTURES: lights,
    }


def build_info_data(
    device_data: dict[str, Any],
    fan_fixture: dict[str, Any] | None = None,
    light_fixtures: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a canonical info dict from a Gen4 /device response.

    `fan_fixture`/`light_fixtures` (the same `classify_fixtures()` output
    `build_state_data()` takes) fill in the fields a consumer needs for
    stable device/entity identity — a Home Assistant integration keys its
    config entry's unique_id and device registry identifiers off `INFO_MAC`,
    and gates whether it creates a light entity at all off `INFO_LIGHT_TYPE`
    being non-empty, matching the legacy /mf behavior those checks were
    written against.
    """
    fan_detail = (fan_fixture or {}).get(GEN4_FIELD_DETAIL) or {}
    return {
        INFO_DEVICE_NAME: device_data.get(GEN4_DEVICE_NAME, ""),
        INFO_FIRMWARE_VERSION: device_data.get(GEN4_DEVICE_IOTM_VER, ""),
        INFO_MAIN_MCU_FIRMWARE_VERSION: device_data.get(GEN4_DEVICE_SCM_VER, ""),
        INFO_OWNER: device_data.get(GEN4_DEVICE_OWNER, ""),
        INFO_MAC: device_data.get(GEN4_DEVICE_STA_MAC, ""),
        INFO_LIGHT_TYPE: "gen4" if light_fixtures else "",
        INFO_FAN_TYPE: fan_detail.get(GEN4_FIELD_MODEL, ""),
    }


def build_fan_control_state(commands: dict[str, Any]) -> dict[str, Any]:
    """Translate a canonical fan() command dict into a Gen4 fixture state."""
    state: dict[str, Any] = {}
    if COMMAND_FAN_POWER in commands:
        state[GEN4_FIELD_STATUS] = commands[COMMAND_FAN_POWER]
    if COMMAND_FAN_SPEED in commands:
        state[COMMAND_FAN_SPEED] = commands[COMMAND_FAN_SPEED]
    if COMMAND_FAN_DIRECTION in commands:
        state[COMMAND_FAN_DIRECTION] = (
            commands[COMMAND_FAN_DIRECTION] == FAN_DIRECTION_REVERSE
        )
    if COMMAND_WIND in commands:
        state[COMMAND_WIND] = commands[COMMAND_WIND]
    if COMMAND_WIND_SPEED in commands:
        state[COMMAND_WIND_SPEED] = commands[COMMAND_WIND_SPEED]
    if COMMAND_IDENTIFY in commands:
        state[GEN4_FIELD_FINDME] = commands[COMMAND_IDENTIFY]
    return state


def build_light_control_state(commands: dict[str, Any]) -> dict[str, Any]:
    """Translate canonical light()/light_fixture() commands to Gen4 fixture."""
    state: dict[str, Any] = {}
    if COMMAND_LIGHT_POWER in commands:
        state[GEN4_FIELD_STATUS] = commands[COMMAND_LIGHT_POWER]
    if COMMAND_LIGHT_BRIGHTNESS in commands:
        state[GEN4_FIELD_LEVEL] = max(
            1, min(10000, commands[COMMAND_LIGHT_BRIGHTNESS] * GEN4_BRIGHTNESS_SCALE)
        )
    if COMMAND_LIGHT_COLOR_TEMP in commands:
        state[GEN4_FIELD_MIX_COLOR_TEMP] = commands[COMMAND_LIGHT_COLOR_TEMP]
    if COMMAND_IDENTIFY in commands:
        state[GEN4_FIELD_FINDME] = commands[COMMAND_IDENTIFY]
    return state


def parse_fan_control_response(state: dict[str, Any]) -> dict[str, Any]:
    """Translate Gen4 fan control response to canonical STATE_* keys."""
    result: dict[str, Any] = {}
    if GEN4_FIELD_STATUS in state:
        result[STATE_FAN_POWER] = state[GEN4_FIELD_STATUS]
    if COMMAND_FAN_SPEED in state:
        result[STATE_FAN_SPEED] = state[COMMAND_FAN_SPEED]
    if COMMAND_FAN_DIRECTION in state:
        result[STATE_FAN_DIRECTION] = (
            FAN_DIRECTION_REVERSE
            if state[COMMAND_FAN_DIRECTION]
            else FAN_DIRECTION_FORWARD
        )
    if COMMAND_WIND in state:
        result[STATE_WIND_POWER] = state[COMMAND_WIND]
    if COMMAND_WIND_SPEED in state:
        result[STATE_WIND_SPEED] = state[COMMAND_WIND_SPEED]
    return result


def parse_light_control_response(state: dict[str, Any]) -> dict[str, Any]:
    """Translate Gen4 light control response to canonical STATE_* keys."""
    result: dict[str, Any] = {}
    if GEN4_FIELD_STATUS in state:
        result[STATE_LIGHT_POWER] = state[GEN4_FIELD_STATUS]
    if GEN4_FIELD_LEVEL in state:
        result[STATE_LIGHT_BRIGHTNESS] = max(
            1, min(100, round(state[GEN4_FIELD_LEVEL] / GEN4_BRIGHTNESS_SCALE))
        )
    if GEN4_FIELD_MIX_COLOR_TEMP in state:
        result[STATE_LIGHT_COLOR_TEMP] = state[GEN4_FIELD_MIX_COLOR_TEMP]
    return result
