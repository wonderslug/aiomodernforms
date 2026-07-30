"""Unit tests for mock_fan.state.FanState."""

from aiomodernforms.const import (
    COMMAND_FAN_DIRECTION,
    COMMAND_FAN_POWER,
    COMMAND_FAN_SLEEP_TIMER,
    COMMAND_FAN_SPEED,
    COMMAND_FAN_TIMER,
    COMMAND_LIGHT_BRIGHTNESS,
    COMMAND_LIGHT_POWER,
    COMMAND_LIGHT_SLEEP_TIMER,
    COMMAND_LIGHT_TIMER,
    COMMAND_WIND,
    COMMAND_WIND_SPEED,
    FAN_DIRECTION_REVERSE,
)
from mock_fan.generations import GEN1_2, GEN3
from mock_fan.state import FanState


def test_initial_state_gen1_2_uses_epoch_timer_fields():
    """Gen 1/2 fans start with epoch sleep-timer fields, not relative ones."""
    state = FanState(GEN1_2, breeze=False)
    shadow = state.snapshot()
    assert shadow[COMMAND_FAN_SLEEP_TIMER] == 0
    assert COMMAND_FAN_TIMER not in shadow
    assert COMMAND_WIND not in shadow


def test_initial_state_gen3_uses_relative_timer_fields():
    """Gen 3 fans start with relative fanTimer/lightTimer fields."""
    state = FanState(GEN3, breeze=False)
    shadow = state.snapshot()
    assert shadow[COMMAND_FAN_TIMER] == 0
    assert COMMAND_FAN_SLEEP_TIMER not in shadow


def test_breeze_enabled_adds_wind_fields():
    """Enabling breeze mode adds wind/windSpeed fields with defaults."""
    state = FanState(GEN1_2, breeze=True)
    shadow = state.snapshot()
    assert shadow[COMMAND_WIND] is False
    assert shadow[COMMAND_WIND_SPEED] == 2


def test_apply_valid_fan_speed():
    """A valid fanSpeed command is applied."""
    state = FanState(GEN1_2, breeze=False)
    shadow = state.apply_commands({COMMAND_FAN_SPEED: 6})
    assert shadow[COMMAND_FAN_SPEED] == 6


def test_apply_out_of_range_fan_speed_is_ignored():
    """An out-of-range fanSpeed command is silently ignored, not applied."""
    state = FanState(GEN1_2, breeze=False)
    shadow = state.apply_commands({COMMAND_FAN_SPEED: 7})
    assert shadow[COMMAND_FAN_SPEED] == 3


def test_apply_non_integer_fan_speed_is_ignored():
    """A non-integer fanSpeed command is silently ignored."""
    state = FanState(GEN1_2, breeze=False)
    shadow = state.apply_commands({COMMAND_FAN_SPEED: "six"})
    assert shadow[COMMAND_FAN_SPEED] == 3


def test_apply_out_of_range_light_brightness_is_ignored():
    """An out-of-range lightBrightness command is silently ignored."""
    state = FanState(GEN1_2, breeze=False)
    shadow = state.apply_commands({COMMAND_LIGHT_BRIGHTNESS: 101})
    assert shadow[COMMAND_LIGHT_BRIGHTNESS] == 50


def test_apply_invalid_fan_direction_is_ignored():
    """An unrecognized fanDirection value is silently ignored."""
    state = FanState(GEN1_2, breeze=False)
    shadow = state.apply_commands({COMMAND_FAN_DIRECTION: "sideways"})
    assert shadow[COMMAND_FAN_DIRECTION] != "sideways"


def test_apply_valid_fan_direction():
    """A valid fanDirection command is applied."""
    state = FanState(GEN1_2, breeze=False)
    shadow = state.apply_commands({COMMAND_FAN_DIRECTION: FAN_DIRECTION_REVERSE})
    assert shadow[COMMAND_FAN_DIRECTION] == FAN_DIRECTION_REVERSE


def test_wind_command_ignored_when_breeze_disabled():
    """A wind command against a non-breeze fan is silently ignored."""
    state = FanState(GEN1_2, breeze=False)
    shadow = state.apply_commands({COMMAND_WIND: True})
    assert COMMAND_WIND not in shadow


def test_wind_command_applied_when_breeze_enabled():
    """A valid wind command against a breeze-enabled fan is applied."""
    state = FanState(GEN1_2, breeze=True)
    shadow = state.apply_commands({COMMAND_WIND: True, COMMAND_WIND_SPEED: 3})
    assert shadow[COMMAND_WIND] is True
    assert shadow[COMMAND_WIND_SPEED] == 3


def test_apply_out_of_range_wind_speed_is_ignored():
    """An out-of-range windSpeed command is silently ignored."""
    state = FanState(GEN1_2, breeze=True)
    shadow = state.apply_commands({COMMAND_WIND_SPEED: 4})
    assert shadow[COMMAND_WIND_SPEED] == 2


def test_apply_fan_power_boolean():
    """A valid fanOn boolean command is applied."""
    state = FanState(GEN1_2, breeze=False)
    shadow = state.apply_commands({COMMAND_FAN_POWER: True})
    assert shadow[COMMAND_FAN_POWER] is True


def test_apply_non_boolean_fan_power_is_ignored():
    """A non-boolean fanOn command is silently ignored."""
    state = FanState(GEN1_2, breeze=False)
    shadow = state.apply_commands({COMMAND_FAN_POWER: "yes"})
    assert shadow[COMMAND_FAN_POWER] is False


def test_reset_restores_startup_defaults():
    """reset() restores the dynamic shadow to its startup defaults."""
    state = FanState(GEN1_2, breeze=False)
    state.apply_commands({COMMAND_FAN_POWER: True, COMMAND_FAN_SPEED: 6})
    state.reset()
    shadow = state.snapshot()
    assert shadow[COMMAND_FAN_POWER] is False
    assert shadow[COMMAND_FAN_SPEED] == 3


def test_relative_timer_rejects_negative_value():
    """A negative relative timer value is silently ignored."""
    state = FanState(GEN3, breeze=False)
    shadow = state.apply_commands({COMMAND_FAN_TIMER: -1})
    assert shadow[COMMAND_FAN_TIMER] == 0


def test_relative_timer_accepts_zero_and_positive_values():
    """Zero (cancel) and positive relative timer values are applied."""
    state = FanState(GEN3, breeze=False)
    shadow = state.apply_commands({COMMAND_FAN_TIMER: 120})
    assert shadow[COMMAND_FAN_TIMER] == 120
    shadow = state.apply_commands({COMMAND_FAN_TIMER: 0})
    assert shadow[COMMAND_FAN_TIMER] == 0


def test_light_disabled_omits_light_fields_gen1_2():
    """A light=False Gen 1/2 fan has no light-related fields in its shadow."""
    state = FanState(GEN1_2, breeze=False, light=False)
    shadow = state.snapshot()
    assert COMMAND_LIGHT_POWER not in shadow
    assert COMMAND_LIGHT_BRIGHTNESS not in shadow
    assert COMMAND_LIGHT_SLEEP_TIMER not in shadow


def test_light_disabled_omits_light_timer_field_gen3():
    """A light=False Gen 3 fan omits lightTimer but keeps fanTimer."""
    state = FanState(GEN3, breeze=False, light=False)
    shadow = state.snapshot()
    assert COMMAND_LIGHT_TIMER not in shadow
    assert COMMAND_LIGHT_POWER not in shadow
    assert shadow[COMMAND_FAN_TIMER] == 0


def test_light_enabled_by_default():
    """Omitting the light argument defaults to light enabled."""
    state = FanState(GEN1_2, breeze=False)
    shadow = state.snapshot()
    assert shadow[COMMAND_LIGHT_POWER] is False
    assert shadow[COMMAND_LIGHT_BRIGHTNESS] == 50


def test_light_power_command_ignored_when_light_disabled():
    """A lightOn command against a light=False fan is silently ignored."""
    state = FanState(GEN1_2, breeze=False, light=False)
    shadow = state.apply_commands({COMMAND_LIGHT_POWER: True})
    assert COMMAND_LIGHT_POWER not in shadow


def test_light_brightness_command_ignored_when_light_disabled():
    """A lightBrightness command against a light=False fan is silently ignored."""
    state = FanState(GEN1_2, breeze=False, light=False)
    shadow = state.apply_commands({COMMAND_LIGHT_BRIGHTNESS: 75})
    assert COMMAND_LIGHT_BRIGHTNESS not in shadow


def test_reset_preserves_light_disabled():
    """reset() keeps light disabled if the fan was constructed that way."""
    state = FanState(GEN1_2, breeze=False, light=False)
    state.apply_commands({COMMAND_FAN_POWER: True})
    state.reset()
    shadow = state.snapshot()
    assert COMMAND_LIGHT_POWER not in shadow
