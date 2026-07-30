# Mock Fan Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone `mock_fan` HTTP service in this repo that speaks the real Modern Forms fan wire protocol, configurable at startup as Gen 1/2 or Gen 3 with optional breeze mode, for pointing a Home Assistant dev instance at during integration development.

**Architecture:** An `aiohttp.web.Application` exposing `POST /mf` (static info queries, state queries, commands) and `POST /config-read` (generation-specific config), backed by a per-generation static profile and a mutable dynamic-shadow state object. One process per simulated fan, driven by a CLI (`python -m mock_fan`). Reboot/factory-reset/decommission commands hold the connection open past the client's timeout rather than responding, then resume after a short delay — reproducing the disconnect behavior `aiomodernforms` already expects.

**Tech Stack:** Python 3.11+, `aiohttp` (already a project dependency), `pytest` + `pytest-asyncio` (already a test dependency), the real `aiomodernforms` client library (this repo) used directly in integration tests.

## Global Constraints

- Python >=3.11, matching `setup.py`'s `python_requires`.
- No new dependencies — `aiohttp` is already in `requirements.txt`; `aiohttp.test_utils.TestServer`/`TestClient` (used for integration tests) ships inside the `aiohttp` package itself, no `pytest-aiohttp` needed.
- `mock_fan/` is a dev tool, not part of the published package — `setup.py`'s `packages=find_packages(include=["aiomodernforms"])` already excludes it; no `setup.py` change needed.
- All tests live under `tests/` (`pytest.ini`'s `testpaths = tests`), so `mock_fan` tests go in `tests/mock_fan/`.
- Use `from __future__ import annotations` and full type hints on every function/class (matches existing `aiomodernforms` code style and this repo's `disallow_untyped_defs` mypy setting).
- Every module/function/class needs a one-line docstring (`flake8-docstrings` lints for this repo-wide via pre-commit).
- Reuse field-name constants from `aiomodernforms.const` everywhere instead of hardcoding wire field names — keeps the mock mechanically in sync with the client library it mirrors.
- Async tests use explicit `@pytest.mark.asyncio` (this repo's pytest-asyncio is in strict mode, no `asyncio_mode = auto`).

---

### Task 1: Generation profiles

**Files:**
- Create: `mock_fan/__init__.py`
- Create: `mock_fan/generations.py`
- Create: `tests/mock_fan/__init__.py`
- Test: `tests/mock_fan/test_generations.py`

**Interfaces:**
- Produces: `mock_fan.generations.GenerationProfile` (frozen dataclass) with fields `name: str`, `client_id: str`, `mac: str`, `fan_type: str`, `light_type: str`, `fan_motor_type: str`, `firmware_version: str`, `main_mcu_firmware_version: str`, `brand: int | None`, `date_code: str`, `uses_relative_timers: bool`, `config_read_response: dict[str, str | int]`.
- Produces: `mock_fan.generations.GEN1_2`, `mock_fan.generations.GEN3` (module-level `GenerationProfile` instances).
- Produces: `mock_fan.generations.PROFILES: dict[str, GenerationProfile]` mapping `"gen1_2"`/`"gen3"` to the instances above.

- [ ] **Step 1: Create empty package files**

`mock_fan/__init__.py`:
```python
"""Mock Modern Forms fan HTTP server, for testing clients without real hardware."""
```

`tests/mock_fan/__init__.py`:
```python
"""This is empty to fix package for VSCode."""
```

- [ ] **Step 2: Write the failing test**

`tests/mock_fan/test_generations.py`:
```python
"""Unit tests for mock_fan.generations profile data."""

from aiomodernforms.const import CONFIG_HARDWARE_REVISION, CONFIG_WIFI_STRENGTH

from mock_fan.generations import GEN1_2, GEN3, PROFILES


def test_gen1_2_uses_epoch_timers():
    """Gen 1/2 profile is marked as using epoch (not relative) timers."""
    assert GEN1_2.uses_relative_timers is False


def test_gen3_uses_relative_timers():
    """Gen 3 profile is marked as using relative timers."""
    assert GEN3.uses_relative_timers is True


def test_gen1_2_has_no_brand_or_date_code():
    """Gen 1/2 profile has no brand/dateCode (Gen 3-only static fields)."""
    assert GEN1_2.brand is None
    assert GEN1_2.date_code == ""


def test_gen3_has_brand_and_date_code():
    """Gen 3 profile includes brand/dateCode."""
    assert GEN3.brand == 0
    assert GEN3.date_code == "20220101"


def test_gen1_2_config_read_has_hardware_revision():
    """Gen 1/2 config-read data includes a hardware revision."""
    assert (
        GEN1_2.config_read_response[CONFIG_HARDWARE_REVISION] == "WAC_WINDERMIER_REV_5"
    )


def test_gen3_config_read_has_no_hardware_revision_key():
    """Gen 3 config-read data has no hardware revision key at all."""
    assert CONFIG_HARDWARE_REVISION not in GEN3.config_read_response


def test_gen1_2_wifi_strength_is_percentage_int():
    """Gen 1/2 Wi-Fi strength is reported as a percentage integer."""
    assert GEN1_2.config_read_response[CONFIG_WIFI_STRENGTH] == 100


def test_gen3_wifi_strength_is_dbm_string():
    """Gen 3 Wi-Fi strength is reported as a dBm string."""
    assert GEN3.config_read_response[CONFIG_WIFI_STRENGTH] == "-48"


def test_profiles_registry_maps_cli_names():
    """PROFILES exposes both generations under their CLI --generation names."""
    assert PROFILES["gen1_2"] is GEN1_2
    assert PROFILES["gen3"] is GEN3
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/pytest tests/mock_fan/test_generations.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mock_fan.generations'`

- [ ] **Step 4: Write the implementation**

`mock_fan/generations.py`:
```python
"""Static per-generation profile data for the mock fan."""

from __future__ import annotations

from dataclasses import dataclass

from aiomodernforms.const import (
    CONFIG_CERTIFICATE_ID,
    CONFIG_FIRMWARE_VERSION,
    CONFIG_FIRMWARE_VERSION_LEGACY,
    CONFIG_HARDWARE_REVISION,
    CONFIG_NAME,
    CONFIG_NAME_LEGACY,
    CONFIG_PROTOCOL,
    CONFIG_PROTOCOL_LEGACY,
    CONFIG_RF_VERSION,
    CONFIG_RF_VERSION_LEGACY,
    CONFIG_WIFI_STRENGTH,
)


@dataclass(frozen=True)
class GenerationProfile:
    """Static, generation-specific data the mock fan serves."""

    name: str
    client_id: str
    mac: str
    fan_type: str
    light_type: str
    fan_motor_type: str
    firmware_version: str
    main_mcu_firmware_version: str
    brand: int | None
    date_code: str
    uses_relative_timers: bool
    config_read_response: dict[str, str | int]


GEN1_2 = GenerationProfile(
    name="gen1_2",
    client_id="MF_000000000000",
    mac="CC:CC:CC:CC:CC:CC",
    fan_type="1818-56",
    light_type="F6IN-120V-R1-30",
    fan_motor_type="DC125X25",
    firmware_version="01.03.0025",
    main_mcu_firmware_version="01.03.3008",
    brand=None,
    date_code="",
    uses_relative_timers=False,
    config_read_response={
        CONFIG_NAME_LEGACY: "Mock Fan",
        CONFIG_PROTOCOL_LEGACY: "com.modernforms.fan",
        CONFIG_HARDWARE_REVISION: "WAC_WINDERMIER_REV_5",
        CONFIG_FIRMWARE_VERSION_LEGACY: "01.03.0025",
        CONFIG_RF_VERSION_LEGACY: "wl0: Oct  6 2016 01:32:44 version 5.90.230.15 ",
        CONFIG_CERTIFICATE_ID: "mockcertificateid0000000000000000000000000000000000000000",
        CONFIG_WIFI_STRENGTH: 100,
    },
)

GEN3 = GenerationProfile(
    name="gen3",
    client_id="MF_C82B9698E5AC",
    mac="C8:2B:96:98:E5:AC",
    fan_type="2003-52",
    light_type="",
    fan_motor_type="DC125X12",
    firmware_version="02.00.0003",
    main_mcu_firmware_version="02.01.0000",
    brand=0,
    date_code="20220101",
    uses_relative_timers=True,
    config_read_response={
        CONFIG_NAME: "Mock Fan",
        CONFIG_PROTOCOL: "com.modernforms.fan",
        CONFIG_FIRMWARE_VERSION: "02.00.0003",
        CONFIG_RF_VERSION: "v3.2.2",
        CONFIG_CERTIFICATE_ID: "mockcertificateid0000000000000000000000000000000000000000",
        CONFIG_WIFI_STRENGTH: "-48",
    },
)

PROFILES: dict[str, GenerationProfile] = {"gen1_2": GEN1_2, "gen3": GEN3}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/mock_fan/test_generations.py -v`
Expected: PASS (10 tests)

- [ ] **Step 6: Commit**

```bash
git add mock_fan/__init__.py mock_fan/generations.py tests/mock_fan/__init__.py tests/mock_fan/test_generations.py
git commit -m "Add mock fan generation profiles"
```

---

### Task 2: Fan state and command validation

**Files:**
- Create: `mock_fan/state.py`
- Test: `tests/mock_fan/test_state.py`

**Interfaces:**
- Consumes: `mock_fan.generations.GenerationProfile`, `GEN1_2`, `GEN3` (Task 1).
- Produces: `mock_fan.state.FanState` with:
  - `__init__(self, profile: GenerationProfile, breeze: bool) -> None`
  - `snapshot(self) -> dict[str, object]`
  - `reset(self) -> None`
  - `apply_commands(self, commands: dict[str, object]) -> dict[str, object]`

- [ ] **Step 1: Write the failing test**

`tests/mock_fan/test_state.py`:
```python
"""Unit tests for mock_fan.state.FanState."""

from aiomodernforms.const import (
    COMMAND_FAN_DIRECTION,
    COMMAND_FAN_POWER,
    COMMAND_FAN_SLEEP_TIMER,
    COMMAND_FAN_SPEED,
    COMMAND_FAN_TIMER,
    COMMAND_LIGHT_BRIGHTNESS,
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/mock_fan/test_state.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mock_fan.state'`

- [ ] **Step 3: Write the implementation**

`mock_fan/state.py`:
```python
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


def _initial_shadow(profile: GenerationProfile, breeze: bool) -> dict[str, object]:
    """Build the startup dynamic shadow dict for a profile."""
    shadow: dict[str, object] = {
        COMMAND_FAN_POWER: False,
        COMMAND_FAN_SPEED: 3,
        COMMAND_FAN_DIRECTION: FAN_DIRECTION_FORWARD,
        COMMAND_LIGHT_POWER: False,
        COMMAND_LIGHT_BRIGHTNESS: 50,
        COMMAND_AWAY_MODE: False,
        COMMAND_ADAPTIVE_LEARNING: False,
        COMMAND_RF_PAIR_MODE: False,
        COMMAND_RESET_RF_PAIR_LIST: False,
        COMMAND_FACTORY_RESET: False,
        COMMAND_DECOMMISSION: False,
        COMMAND_SCHEDULE: "",
    }
    if profile.uses_relative_timers:
        shadow[COMMAND_FAN_TIMER] = 0
        shadow[COMMAND_LIGHT_TIMER] = 0
    else:
        shadow[COMMAND_FAN_SLEEP_TIMER] = 0
        shadow[COMMAND_LIGHT_SLEEP_TIMER] = 0
    if breeze:
        shadow[COMMAND_WIND] = False
        shadow[COMMAND_WIND_SPEED] = 2
    return shadow


def _build_validators(
    profile: GenerationProfile, breeze: bool
) -> dict[str, Callable[[object], bool]]:
    """Build the per-field validator map for a profile/breeze combination."""
    validators: dict[str, Callable[[object], bool]] = {
        COMMAND_FAN_POWER: _is_bool,
        COMMAND_LIGHT_POWER: _is_bool,
        COMMAND_AWAY_MODE: _is_bool,
        COMMAND_ADAPTIVE_LEARNING: _is_bool,
        COMMAND_RF_PAIR_MODE: _is_bool,
        COMMAND_RESET_RF_PAIR_LIST: _is_bool,
        COMMAND_FAN_SPEED: _is_int_in_range(FAN_SPEED_LOW_VALUE, FAN_SPEED_HIGH_VALUE),
        COMMAND_LIGHT_BRIGHTNESS: _is_int_in_range(
            LIGHT_BRIGHTNESS_LOW_VALUE, LIGHT_BRIGHTNESS_HIGH_VALUE
        ),
        COMMAND_FAN_DIRECTION: _is_one_of(FAN_DIRECTION_FORWARD, FAN_DIRECTION_REVERSE),
        COMMAND_SCHEDULE: _is_str,
    }
    if profile.uses_relative_timers:
        validators[COMMAND_FAN_TIMER] = _is_non_negative_int
        validators[COMMAND_LIGHT_TIMER] = _is_non_negative_int
    else:
        validators[COMMAND_FAN_SLEEP_TIMER] = _is_non_negative_int
        validators[COMMAND_LIGHT_SLEEP_TIMER] = _is_non_negative_int
    if breeze:
        validators[COMMAND_WIND] = _is_bool
        validators[COMMAND_WIND_SPEED] = _is_int_in_range(
            WIND_SPEED_LOW_VALUE, WIND_SPEED_HIGH_VALUE
        )
    return validators


class FanState:
    """Holds and mutates a mock fan's dynamic shadow state."""

    def __init__(self, profile: GenerationProfile, breeze: bool) -> None:
        """Initialize state with startup defaults for the given profile."""
        self._profile = profile
        self._breeze = breeze
        self._validators = _build_validators(profile, breeze)
        self._shadow = _initial_shadow(profile, breeze)

    def snapshot(self) -> dict[str, object]:
        """Return a copy of the current dynamic shadow dict."""
        return dict(self._shadow)

    def reset(self) -> None:
        """Reset the dynamic shadow to startup defaults."""
        self._shadow = _initial_shadow(self._profile, self._breeze)

    def apply_commands(self, commands: dict[str, object]) -> dict[str, object]:
        """Validate and apply command fields, returning the full updated shadow.

        Invalid values (out of range, wrong type, or breeze-only fields on a
        non-breeze fan) are silently ignored rather than erroring, mirroring
        how embedded firmware is expected to no-op bad input rather than
        return an HTTP error the API reference doesn't document.
        """
        for key, value in commands.items():
            validator = self._validators.get(key)
            if validator is not None and validator(value):
                self._shadow[key] = value
        return self.snapshot()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/mock_fan/test_state.py -v`
Expected: PASS (17 tests)

- [ ] **Step 5: Commit**

```bash
git add mock_fan/state.py tests/mock_fan/test_state.py
git commit -m "Add mock fan dynamic state and command validation"
```

---

### Task 3: HTTP server

**Files:**
- Create: `mock_fan/server.py`
- Test: `tests/mock_fan/test_server.py`

**Interfaces:**
- Consumes: `mock_fan.generations.GenerationProfile`, `GEN1_2`, `GEN3` (Task 1); `mock_fan.state.FanState` (Task 2).
- Produces: `mock_fan.server.create_app(profile: GenerationProfile, breeze: bool, resume_delay_secs: float = 5.0) -> aiohttp.web.Application`.

- [ ] **Step 1: Write the failing test**

`tests/mock_fan/test_server.py`:
```python
"""Integration tests: drive the mock fan server with the real aiomodernforms client."""

import asyncio

import pytest
from aiohttp.test_utils import TestClient, TestServer

import aiomodernforms
from aiomodernforms.const import FAN_DIRECTION_REVERSE

from mock_fan.generations import GEN1_2, GEN3
from mock_fan.server import create_app


@pytest.mark.asyncio
async def test_update_populates_info_and_state_gen1_2():
    """update() against a Gen 1/2 mock fan populates Info and State correctly."""
    app = create_app(GEN1_2, breeze=False)
    async with TestClient(TestServer(app)) as client:
        async with aiomodernforms.ModernFormsDevice(
            client.host, port=client.port, session=client.session
        ) as device:
            await device.update()
            assert device.info.fan_type == GEN1_2.fan_type
            assert device.status.fan_on is False
            assert device.status.fan_speed == 3
            assert device.has_breeze_mode() is False
            assert device.has_relative_timers() is False


@pytest.mark.asyncio
async def test_update_populates_info_and_state_gen3():
    """update() against a Gen 3 mock fan reports gen3 info/capabilities."""
    app = create_app(GEN3, breeze=True)
    async with TestClient(TestServer(app)) as client:
        async with aiomodernforms.ModernFormsDevice(
            client.host, port=client.port, session=client.session
        ) as device:
            await device.update()
            assert device.info.fan_type == GEN3.fan_type
            assert device.info.brand == GEN3.brand
            assert device.has_breeze_mode() is True
            assert device.has_relative_timers() is True


@pytest.mark.asyncio
async def test_light_and_fan_round_trip():
    """light()/fan() commands round-trip through the mock fan."""
    app = create_app(GEN1_2, breeze=False)
    async with TestClient(TestServer(app)) as client:
        async with aiomodernforms.ModernFormsDevice(
            client.host, port=client.port, session=client.session
        ) as device:
            await device.update()
            await device.light(on=True, brightness=75)
            assert device.status.light_on is True
            assert device.status.light_brightness == 75

            await device.fan(on=True, speed=5, direction=FAN_DIRECTION_REVERSE)
            assert device.status.fan_on is True
            assert device.status.fan_speed == 5
            assert device.status.fan_direction == FAN_DIRECTION_REVERSE


@pytest.mark.asyncio
async def test_away_and_adaptive_learning_round_trip():
    """away()/adaptive_learning() commands round-trip through the mock fan."""
    app = create_app(GEN1_2, breeze=False)
    async with TestClient(TestServer(app)) as client:
        async with aiomodernforms.ModernFormsDevice(
            client.host, port=client.port, session=client.session
        ) as device:
            await device.update()
            await device.away(True)
            assert device.status.away_mode_enabled is True

            await device.adaptive_learning(True)
            assert device.status.adaptive_learning_enabled is True


@pytest.mark.asyncio
async def test_config_read_gen1_2():
    """config() against a Gen 1/2 mock fan returns gen1/2-shaped fields."""
    app = create_app(GEN1_2, breeze=False)
    async with TestClient(TestServer(app)) as client:
        async with aiomodernforms.ModernFormsDevice(
            client.host, port=client.port, session=client.session
        ) as device:
            config = await device.config()
            assert config.protocol == "com.modernforms.fan"
            assert config.hardware_revision == "WAC_WINDERMIER_REV_5"
            assert config.wifi_strength == "100"


@pytest.mark.asyncio
async def test_config_read_gen3():
    """config() against a Gen 3 mock fan returns gen3-shaped fields."""
    app = create_app(GEN3, breeze=False)
    async with TestClient(TestServer(app)) as client:
        async with aiomodernforms.ModernFormsDevice(
            client.host, port=client.port, session=client.session
        ) as device:
            config = await device.config()
            assert config.protocol == "com.modernforms.fan"
            assert config.hardware_revision == ""
            assert config.wifi_strength == "-48"


@pytest.mark.asyncio
async def test_reboot_disconnects_then_resumes():
    """reboot() times out (swallowed) then the fan resumes responding."""
    app = create_app(GEN1_2, breeze=False, resume_delay_secs=0.05)
    async with TestClient(TestServer(app)) as client:
        async with aiomodernforms.ModernFormsDevice(
            client.host,
            port=client.port,
            session=client.session,
            request_timeout=0.2,
        ) as device:
            await device.update()
            await device.reboot()  # must not raise; timeout is swallowed

            await asyncio.sleep(0.1)
            await device.update()  # must succeed again after resume delay
            assert device.status.fan_on is False


@pytest.mark.asyncio
async def test_factory_reset_resets_state():
    """factory_reset() resets dynamic shadow state to startup defaults."""
    app = create_app(GEN1_2, breeze=False, resume_delay_secs=0.05)
    async with TestClient(TestServer(app)) as client:
        async with aiomodernforms.ModernFormsDevice(
            client.host,
            port=client.port,
            session=client.session,
            request_timeout=0.2,
        ) as device:
            await device.update()
            await device.fan(on=True, speed=6)
            assert device.status.fan_on is True

            await device.factory_reset()  # must not raise

            await asyncio.sleep(0.1)
            await device.update()
            assert device.status.fan_on is False
            assert device.status.fan_speed == 3
```

Note: `test_reboot_disconnects_then_resumes` and `test_factory_reset_resets_state` take a few real seconds each — `aiomodernforms`'s `_request` retries up to 3 times with backoff on `ModernFormsConnectionTimeoutError` before `reboot()`/`factory_reset()` catch and swallow it. That's inherent to the client library being tested against, not a mock defect.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/mock_fan/test_server.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mock_fan.server'`

- [ ] **Step 3: Write the implementation**

`mock_fan/server.py`:
```python
"""aiohttp server emulating the Modern Forms fan wire protocol."""

from __future__ import annotations

import asyncio

from aiohttp import web

from aiomodernforms.const import (
    COMMAND_DECOMMISSION,
    COMMAND_FACTORY_RESET,
    COMMAND_QUERY_STATIC_DATA,
    COMMAND_REBOOT,
    INFO_BRAND,
    INFO_CLIENT_ID,
    INFO_DATE_CODE,
    INFO_DEVICE_NAME,
    INFO_FAN_MOTOR_TYPE,
    INFO_FAN_TYPE,
    INFO_FEDERATED_IDENTITY,
    INFO_FIRMWARE_URL,
    INFO_FIRMWARE_VERSION,
    INFO_LIGHT_TYPE,
    INFO_MAC,
    INFO_MAIN_MCU_FIRMWARE_VERSION,
    INFO_OWNER,
    INFO_PRODUCT_SKU,
    INFO_PRODUCTION_LOT_NUMBER,
)

from .generations import GenerationProfile
from .state import FanState

# Far longer than any sane client timeout, so a held connection is
# effectively dead from the client's point of view; short enough that an
# abandoned handler task doesn't linger indefinitely if never cancelled.
DISCONNECT_HOLD_SECS = 300

DEVICE_NAME = "Mock Fan"


def _static_info(profile: GenerationProfile) -> dict[str, object]:
    """Build the static shadow (queryStaticShadowData) response for a profile."""
    info: dict[str, object] = {
        INFO_CLIENT_ID: profile.client_id,
        INFO_MAC: profile.mac,
        INFO_LIGHT_TYPE: profile.light_type,
        INFO_FAN_TYPE: profile.fan_type,
        INFO_FAN_MOTOR_TYPE: profile.fan_motor_type,
        INFO_PRODUCTION_LOT_NUMBER: "",
        INFO_PRODUCT_SKU: "",
        INFO_OWNER: "mock@example.com",
        INFO_FEDERATED_IDENTITY: "us-east-1:00000000-0000-0000-0000-000000000000",
        INFO_DEVICE_NAME: DEVICE_NAME,
        INFO_FIRMWARE_VERSION: profile.firmware_version,
        INFO_MAIN_MCU_FIRMWARE_VERSION: profile.main_mcu_firmware_version,
        INFO_FIRMWARE_URL: "",
    }
    if profile.brand is not None:
        info[INFO_BRAND] = profile.brand
        info[INFO_DATE_CODE] = profile.date_code
    return info


class MockFan:
    """Holds a mock fan's state and its simulated-disconnect window."""

    def __init__(
        self, profile: GenerationProfile, breeze: bool, resume_delay_secs: float
    ) -> None:
        """Initialize the mock fan's state for the given profile/breeze."""
        self.profile = profile
        self.state = FanState(profile, breeze)
        self.resume_delay_secs = resume_delay_secs
        self.unresponsive_until: float = 0.0


async def _handle_mf(request: web.Request) -> web.Response:
    """Handle POST /mf: static info queries, state queries, and commands."""
    fan: MockFan = request.app["fan"]
    loop = asyncio.get_running_loop()

    if loop.time() < fan.unresponsive_until:
        await asyncio.sleep(DISCONNECT_HOLD_SECS)

    commands = await request.json()

    if commands.get(COMMAND_QUERY_STATIC_DATA):
        return web.json_response(_static_info(fan.profile))

    disruptive = (
        commands.get(COMMAND_FACTORY_RESET)
        or commands.get(COMMAND_DECOMMISSION)
        or commands.get(COMMAND_REBOOT)
    )
    if disruptive:
        if commands.get(COMMAND_FACTORY_RESET) or commands.get(COMMAND_DECOMMISSION):
            fan.state.reset()
        fan.unresponsive_until = loop.time() + fan.resume_delay_secs
        await asyncio.sleep(DISCONNECT_HOLD_SECS)

    shadow = fan.state.apply_commands(commands)
    return web.json_response(shadow)


async def _handle_config_read(request: web.Request) -> web.Response:
    """Handle POST /config-read: generation-specific config info."""
    fan: MockFan = request.app["fan"]
    return web.json_response(fan.profile.config_read_response)


def create_app(
    profile: GenerationProfile, breeze: bool, resume_delay_secs: float = 5.0
) -> web.Application:
    """Build the aiohttp application for a mock fan of the given profile."""
    app = web.Application()
    app["fan"] = MockFan(profile, breeze, resume_delay_secs)
    app.router.add_post("/mf", _handle_mf)
    app.router.add_post("/config-read", _handle_config_read)
    return app
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/mock_fan/test_server.py -v`
Expected: PASS (8 tests; the reboot/factory-reset tests take a few seconds each)

- [ ] **Step 5: Commit**

```bash
git add mock_fan/server.py tests/mock_fan/test_server.py
git commit -m "Add mock fan aiohttp server"
```

---

### Task 4: CLI entry point

**Files:**
- Create: `mock_fan/__main__.py`
- Test: `tests/mock_fan/test_cli.py`

**Interfaces:**
- Consumes: `mock_fan.generations.PROFILES` (Task 1), `mock_fan.server.create_app` (Task 3).
- Produces: `mock_fan.__main__._parse_args(argv: list[str] | None = None) -> argparse.Namespace`, `mock_fan.__main__.main(argv: list[str] | None = None) -> None`.

- [ ] **Step 1: Write the failing test**

`tests/mock_fan/test_cli.py`:
```python
"""Unit tests for mock_fan.__main__ argument parsing."""

import pytest

from mock_fan.__main__ import _parse_args


def test_generation_is_required():
    """--generation is required; omitting it is a usage error."""
    with pytest.raises(SystemExit):
        _parse_args([])


def test_defaults():
    """host/port/breeze default sensibly when only --generation is given."""
    args = _parse_args(["--generation", "gen1_2"])
    assert args.generation == "gen1_2"
    assert args.breeze is False
    assert args.host == "0.0.0.0"
    assert args.port == 8080


def test_breeze_flag_and_overrides():
    """--breeze, --host, and --port are parsed correctly when given."""
    args = _parse_args(
        ["--generation", "gen3", "--breeze", "--host", "127.0.0.1", "--port", "9090"]
    )
    assert args.generation == "gen3"
    assert args.breeze is True
    assert args.host == "127.0.0.1"
    assert args.port == 9090


def test_invalid_generation_rejected():
    """An unrecognized --generation value is a usage error."""
    with pytest.raises(SystemExit):
        _parse_args(["--generation", "gen99"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/mock_fan/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mock_fan.__main__'`

- [ ] **Step 3: Write the implementation**

`mock_fan/__main__.py`:
```python
"""CLI entry point for running a mock Modern Forms fan."""

from __future__ import annotations

import argparse

from aiohttp import web

from .generations import PROFILES
from .server import create_app


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the mock fan server."""
    parser = argparse.ArgumentParser(
        description="Run a mock Modern Forms fan HTTP server."
    )
    parser.add_argument(
        "--generation",
        required=True,
        choices=sorted(PROFILES),
        help="Fan hardware generation to emulate.",
    )
    parser.add_argument(
        "--breeze",
        action="store_true",
        help="Enable breeze (wind) mode support.",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host/interface to listen on (default: 0.0.0.0).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to listen on (default: 8080).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Run the mock fan server until interrupted."""
    args = _parse_args(argv)
    profile = PROFILES[args.generation]
    app = create_app(profile, breeze=args.breeze)
    print(
        f"Mock fan listening on {args.host}:{args.port}"
        f" (generation={profile.name}, breeze={'on' if args.breeze else 'off'})"
    )
    web.run_app(app, host=args.host, port=args.port, print=None)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/mock_fan/test_cli.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Manually smoke-test the CLI**

Run: `.venv/bin/python -m mock_fan --generation gen3 --breeze --port 8090` in one terminal, then in another:
```bash
curl -s -X POST http://127.0.0.1:8090/mf -d '{"queryDynamicShadowData": true}' | python3 -m json.tool
curl -s -X POST http://127.0.0.1:8090/config-read -d '{}' | python3 -m json.tool
```
Expected: both return JSON matching the Gen 3 profile (`wind`/`windSpeed` present in the first; `Name`/`Protocol`/`Firmware Rev` in the second). Stop the server with Ctrl-C.

- [ ] **Step 6: Commit**

```bash
git add mock_fan/__main__.py tests/mock_fan/test_cli.py
git commit -m "Add mock fan CLI entry point"
```

---

### Task 5: Documentation and Makefile convenience target

**Files:**
- Modify: `README.md`
- Modify: `Makefile`

**Interfaces:**
- Consumes: the `python -m mock_fan --generation ... [--breeze] [--host ...] [--port ...]` CLI from Task 4. No new code interfaces produced.

- [ ] **Step 1: Add a Makefile target**

In `Makefile`, add after the existing `.PHONY: diagnose` / `diagnose:` block:

```makefile
.PHONY: mock-fan
mock-fan: ## Run a mock fan server (usage: make mock-fan GENERATION=gen3 [BREEZE=1] [PORT=8080]).
	@if [ -z "$(GENERATION)" ]; then \
		echo "Usage: make mock-fan GENERATION=<gen1_2|gen3> [BREEZE=1] [PORT=8080]"; \
		exit 1; \
	fi
	python -m mock_fan --generation $(GENERATION) --port $${PORT:-8080} $(if $(BREEZE),--breeze,)
```

- [ ] **Step 2: Add a README section**

In `README.md`, add a new section after "## Reporting compatibility issues":

```markdown
## Mock fan for development

To develop or test a client (such as a Home Assistant integration) against
this API without real hardware, run a mock fan that speaks the same wire
protocol:

```bash
python -m mock_fan --generation gen3 --breeze --port 8080
# or
make mock-fan GENERATION=gen1_2 PORT=8081
```

`--generation` is `gen1_2` or `gen3` and is required; `--breeze` optionally
enables breeze/wind mode support. Point your client at the printed
host/port exactly as you would a real fan.
```

- [ ] **Step 3: Verify the full test suite still passes**

Run: `.venv/bin/pytest tests/ -v`
Expected: PASS — all existing `tests/test_aiomodernforms.py` tests plus all new `tests/mock_fan/` tests.

- [ ] **Step 4: Commit**

```bash
git add README.md Makefile
git commit -m "Document the mock fan dev tool"
```
