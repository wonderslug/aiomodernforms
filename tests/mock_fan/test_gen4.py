"""Unit tests for mock_fan.gen4 fixture data and state."""

from aiomodernforms.const import (
    COMMAND_FAN_DIRECTION,
    COMMAND_FAN_SPEED,
    COMMAND_WIND,
    COMMAND_WIND_SPEED,
    GEN4_FIELD_ADDR,
    GEN4_FIELD_FINDME,
    GEN4_FIELD_LEVEL,
    GEN4_FIELD_MAX_COLOR_TEMP,
    GEN4_FIELD_MIN_COLOR_TEMP,
    GEN4_FIELD_MIX_COLOR_TEMP,
    GEN4_FIELD_NAME,
    GEN4_FIELD_STATE,
    GEN4_FIELD_STATUS,
    GEN4_FIELD_TYPE,
    GEN4_FIXTURE_TYPE_FAN,
    GEN4_NWK_CERTIFICATE_ID,
    GEN4_NWK_RSSI,
    STATE_AWAY_MODE,
)
from mock_fan.gen4 import LIGHT_FIXTURE_TYPE, Gen4FanState, device_data


def test_gen4_fan_state_startup_defaults():
    """A fresh Gen4FanState has the fan off, speed 3, one light off at 50%."""
    state = Gen4FanState(lights=1)
    assert state.fan.state[GEN4_FIELD_STATUS] is False
    assert state.fan.state[COMMAND_FAN_SPEED] == 3
    assert state.fan.state[COMMAND_FAN_DIRECTION] is False
    assert state.fan.state[COMMAND_WIND] is False
    assert state.fan.state[COMMAND_WIND_SPEED] == 2
    assert len(state.lights) == 1
    assert state.lights[0].state[GEN4_FIELD_STATUS] is False
    assert state.away_mode_enabled is False


def test_gen4_fan_state_lights_count_zero():
    """lights=0 produces a fan with no light fixtures at all."""
    state = Gen4FanState(lights=0)
    assert state.lights == []
    assert state.all_fixtures() == [state.fan]


def test_gen4_fan_state_multiple_lights_have_distinct_addresses():
    """lights=3 produces three lights, each with a unique address and name."""
    state = Gen4FanState(lights=3)
    assert len(state.lights) == 3
    addresses = [light.address for light in state.lights]
    assert len(set(addresses)) == 3
    names = [light.name for light in state.lights]
    assert len(set(names)) == 3


def test_gen4_fan_state_find_by_address():
    """find() locates the fan or a light by its address; None for unknown."""
    state = Gen4FanState(lights=2)
    assert state.find(state.fan.address) is state.fan
    assert state.find(state.lights[1].address) is state.lights[1]
    assert state.find(999999) is None


def test_gen4_fixture_apply_commands_validates_fan_speed():
    """A valid fanSpeed command is applied; an out-of-range one is ignored."""
    state = Gen4FanState(lights=0)
    changed = state.fan.apply_commands({COMMAND_FAN_SPEED: 6})
    assert changed == {COMMAND_FAN_SPEED: 6}
    assert state.fan.state[COMMAND_FAN_SPEED] == 6

    changed = state.fan.apply_commands({COMMAND_FAN_SPEED: 7})
    assert not changed
    assert state.fan.state[COMMAND_FAN_SPEED] == 6


def test_gen4_fixture_apply_commands_only_returns_changed_keys():
    """apply_commands() returns only the applied keys, not the full state."""
    state = Gen4FanState(lights=0)
    changed = state.fan.apply_commands(
        {GEN4_FIELD_STATUS: True, GEN4_FIELD_FINDME: True}
    )
    expected = {GEN4_FIELD_STATUS: True, GEN4_FIELD_FINDME: True}
    assert changed == expected
    assert COMMAND_FAN_SPEED not in changed


def test_gen4_fixture_light_validates_level_and_color_temp():
    """A light fixture validates level (1-10000) and mixColorTemp."""
    state = Gen4FanState(lights=1)
    light = state.lights[0]
    changed = light.apply_commands(
        {GEN4_FIELD_LEVEL: 7500, GEN4_FIELD_MIX_COLOR_TEMP: 4000}
    )
    expected = {GEN4_FIELD_LEVEL: 7500, GEN4_FIELD_MIX_COLOR_TEMP: 4000}
    assert changed == expected

    changed = light.apply_commands({GEN4_FIELD_LEVEL: 10001})
    assert changed == {}
    assert light.state[GEN4_FIELD_LEVEL] == 7500


def test_gen4_fixture_as_wire_dict_shape():
    """as_wire_dict() matches the /fixture read-all element shape."""
    state = Gen4FanState(lights=1)
    wire = state.fan.as_wire_dict()
    assert wire[GEN4_FIELD_ADDR] == state.fan.address
    assert wire[GEN4_FIELD_TYPE] == GEN4_FIXTURE_TYPE_FAN
    assert GEN4_FIELD_NAME in wire
    assert wire[GEN4_FIELD_STATE] == state.fan.state

    light_wire = state.lights[0].as_wire_dict()
    assert light_wire[GEN4_FIELD_TYPE] == LIGHT_FIXTURE_TYPE
    assert GEN4_FIELD_MIN_COLOR_TEMP in light_wire["detail"]
    assert GEN4_FIELD_MAX_COLOR_TEMP in light_wire["detail"]


def test_gen4_fan_state_reset_restores_defaults():
    """reset() restores the fan, all lights, and away mode to startup defaults."""
    state = Gen4FanState(lights=2)
    state.fan.apply_commands({GEN4_FIELD_STATUS: True, COMMAND_FAN_SPEED: 6})
    state.lights[0].apply_commands({GEN4_FIELD_STATUS: True})
    state.away_mode_enabled = True

    state.reset()

    assert state.fan.state[GEN4_FIELD_STATUS] is False
    assert state.fan.state[COMMAND_FAN_SPEED] == 3
    assert state.lights[0].state[GEN4_FIELD_STATUS] is False
    assert state.away_mode_enabled is False


def test_device_data_reflects_away_mode():
    """device_data() embeds the given away-mode value and static device fields."""
    data = device_data(away_mode_enabled=True)
    assert data["systemType"] == "fan_g4"
    assert data[STATE_AWAY_MODE] is True
    assert "nwkState" in data
    assert GEN4_NWK_CERTIFICATE_ID in data["nwkState"]
    assert GEN4_NWK_RSSI in data["nwkState"]

    data = device_data(away_mode_enabled=False)
    assert data[STATE_AWAY_MODE] is False
