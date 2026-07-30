# Gen4 Fan Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Gen4 fan support to `aiomodernforms` — detecting Gen4 devices, translating their `/device` + `/fixture` wire protocol into the library's existing canonical state/info shape, and controlling an arbitrary number of light fixtures — without changing any existing method's signature or behavior for Gen 1/2/3 callers.

**Architecture:** A new pure-translation module (`aiomodernforms/gen4.py`) converts between Gen4's wire shapes and the same canonical `STATE_*`/`INFO_*`-keyed dicts `State.from_dict`/`Info.from_dict` already consume — so `models.py` stays almost entirely generation-agnostic, and `ModernFormsDevice` only needs to know generation-specific *transport* details (which endpoint, how to merge a partial fixture response), not wire-format details. Generation is tracked explicitly as a three-value `Generation` enum (`gen1_2`/`gen3`/`gen4`) on `Device`, detected once per `ModernFormsDevice` instance and reused on every later call.

**Tech Stack:** Python 3.11, aiohttp, pytest + pytest-asyncio + aresponses (HTTP mocking).

## Global Constraints

- Python `>=3.11` (`setup.py`). Use `from __future__ import annotations` and modern union syntax (`int | None`, not `Optional[int]`) to match every existing file in `aiomodernforms/`.
- Line length 88 chars (black default; `flake8` `max-line-length=88`).
- mypy runs with `disallow_untyped_calls=True`, `disallow_untyped_defs=True`, `no_implicit_optional=True`, `strict_optional=True` — give every new function full parameter and return type hints.
- `flake8-docstrings` is enabled (`D202`, `W503` ignored) — every new public function/class/method needs a one-line docstring.
- Pre-commit hooks (black, isort, autopep8, pylint, mypy, flake8, pyupgrade `--py36-plus`) run automatically on `git commit`. If a hook reformats files, the commit aborts on the first attempt — run `git add -u` and re-run the same `git commit` command.
- Tests use `@pytest.mark.asyncio` and the `aresponses` fixture (auto-provided, already used throughout `tests/test_aiomodernforms.py` — no fixture setup needed). Mirror existing fixture/test naming conventions (`gen3_info`, `gen1_2_config_response`, etc.) with a `gen4_` prefix for new ones.
- Run the full suite with `pytest tests/ -v` before every commit that touches source files.
- Per the design spec (`docs/superpowers/specs/2026-07-29-gen4-fan-support-design.md`): **no fixture address is ever computed** (e.g. from a MAC address) — every address used for control comes from what the device reports in a `/fixture` read. Do not reintroduce address arithmetic anywhere in this plan.
- Out of scope for this plan (per the design spec): `decommission()`/RF pairing/schedules on Gen4 (raise `ModernFormsNotSupportedError` instead), the Gen4 `Configure`-action tuning fields, RGBW lights, any non-fan WAC IoT device/fixture type, mDNS discovery, and the `mock_fan` Gen4 profile (documented at the end of this plan as a deferred follow-on — the base `mock_fan` service this would extend doesn't exist in the repo yet).

---

### Task 1: Add `ModernFormsNotSupportedError` exception

**Files:**
- Modify: `aiomodernforms/exceptions.py`
- Test: `tests/test_aiomodernforms.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `aiomodernforms.exceptions.ModernFormsNotSupportedError` (and re-exported as `aiomodernforms.ModernFormsNotSupportedError`). Used by Task 10 for `decommission()`/`enable_pairing_mode()`/`clear_paired_devices()`/`set_schedule()` on Gen4.

**Context:** `aiomodernforms/exceptions.py` currently defines six exceptions, all simple `Exception` subclasses with a one-line docstring:

```python
class ModernFormsError(Exception):
    """Generic ModernForms exception."""
```

- [ ] **Step 1: Write the failing test**

Add to `tests/test_aiomodernforms.py`, near the top with the other exception-adjacent imports left alone (this test only needs the new exception itself — add the import inline in the test file's import block from `aiomodernforms.exceptions`):

```python
from aiomodernforms.exceptions import (
    ModernFormsConnectionTimeoutError,
    ModernFormsEmptyResponseError,
    ModernFormsNotInitializedError,
    ModernFormsNotSupportedError,
)
```

Then add this test anywhere after the imports (e.g. right before `basic_response`):

```python
def test_not_supported_error_is_an_exception():
    """Test that ModernFormsNotSupportedError exists and is a real exception."""
    with pytest.raises(ModernFormsNotSupportedError):
        raise ModernFormsNotSupportedError("not supported on this generation")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_aiomodernforms.py::test_not_supported_error_is_an_exception -v`
Expected: FAIL with `ImportError: cannot import name 'ModernFormsNotSupportedError'`.

- [ ] **Step 3: Add the exception**

In `aiomodernforms/exceptions.py`, add after `ModernFormsInvalidSettingsError`:

```python
class ModernFormsNotSupportedError(Exception):
    """Raised when a feature isn't supported on a device's generation."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_aiomodernforms.py::test_not_supported_error_is_an_exception -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aiomodernforms/exceptions.py tests/test_aiomodernforms.py
git commit -m "feat: add ModernFormsNotSupportedError exception"
```

---

### Task 2: `Generation` enum on `Device`, with `has_adaptive_learning()`/`has_sleep_timer()`/`has_identify()`

**Files:**
- Modify: `aiomodernforms/models.py`
- Test: `tests/test_aiomodernforms.py`

**Interfaces:**
- Consumes: `STATE_FAN_TIMER`, `STATE_LIGHT_TIMER` (existing constants).
- Produces: `aiomodernforms.models.Generation` enum (`GEN1_2 = "gen1_2"`, `GEN3 = "gen3"`, `GEN4 = "gen4"`); `Device.generation: Generation`; `Device.__init__`/`Device.update_from_dict` gain an optional `generation: Generation | None = None` keyword parameter; `Device.has_adaptive_learning() -> bool`, `Device.has_sleep_timer() -> bool`, `Device.has_identify() -> bool`. Task 6 (Gen4 `update()` wiring) passes `generation=Generation.GEN4` explicitly; Task 9/10 consume `has_adaptive_learning()`/`has_sleep_timer()`; Task 8 consumes `has_identify()`.

**Context:** `Device.update_from_dict` currently is:

```python
def update_from_dict(
    self, state_data: dict | None = None, info_data: dict | None = None
) -> Device:
    """Update the device status with the passed dict."""
    if state_data is not None:
        self.state = State.from_dict(state_data)
    if info_data is not None:
        self.info = Info.from_dict(info_data)
    return self
```

`has_relative_timers()` already infers Gen 3 vs Gen 1/2 from whether `fan_timer`/`light_timer` are non-`None` — the same signal now also sets the new `generation` field, so `has_relative_timers()`'s existing behavior doesn't change. For Gen4, `ModernFormsDevice` (Task 6) always passes `generation=Generation.GEN4` explicitly, since Gen4 detection happens before any state dict exists.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_aiomodernforms.py`, after `test_has_relative_timers_false_for_gen1_2` (or anywhere near the other `has_*` tests):

```python
@pytest.mark.asyncio
async def test_generation_defaults_gen1_2(aresponses):
    """Test that a device with no relative timers is classified gen1_2."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        assert device._device.generation == Generation.GEN1_2
        assert device._device.has_adaptive_learning() is True
        assert device._device.has_sleep_timer() is True
        assert device._device.has_identify() is False


@pytest.mark.asyncio
async def test_generation_gen3_from_relative_timers(aresponses):
    """Test that a device with relative timers is classified gen3."""
    aresponses.add("fan.local", "/mf", "POST", response=gen3_info)
    aresponses.add("fan.local", "/mf", "POST", response=gen3_relative_timer_response)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        assert device._device.generation == Generation.GEN3


def test_device_accepts_explicit_generation():
    """Test that Device.__init__ honors an explicitly passed generation."""
    device = Device(state_data=basic_response, info_data=basic_info, generation=Generation.GEN4)
    assert device.generation == Generation.GEN4
    assert device.has_adaptive_learning() is False
    assert device.has_sleep_timer() is False
    assert device.has_identify() is True
```

Add the new imports these tests need to the top of `tests/test_aiomodernforms.py`:

```python
from aiomodernforms.models import Device, Generation
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_aiomodernforms.py::test_generation_defaults_gen1_2 tests/test_aiomodernforms.py::test_generation_gen3_from_relative_timers tests/test_aiomodernforms.py::test_device_accepts_explicit_generation -v`
Expected: FAIL with `ImportError: cannot import name 'Generation'`.

- [ ] **Step 3: Add the `Generation` enum and wire it into `Device`**

In `aiomodernforms/models.py`, add near the top (after the existing imports, before the `Info` dataclass):

```python
from enum import Enum


class Generation(str, Enum):
    """Which wire protocol a Modern Forms fan speaks."""

    GEN1_2 = "gen1_2"
    GEN3 = "gen3"
    GEN4 = "gen4"
```

Replace the `Device` class's `__init__` and `update_from_dict` with:

```python
class Device:
    """Object holding all information of Modern Forms Device."""

    info: Info
    state: State
    generation: Generation

    def __init__(
        self,
        state_data: dict,
        info_data: dict,
        generation: Generation | None = None,
    ):
        """Initialize an empty Modern Forms device class."""
        self.update_from_dict(
            state_data=state_data, info_data=info_data, generation=generation
        )

    def update_from_dict(
        self,
        state_data: dict | None = None,
        info_data: dict | None = None,
        generation: Generation | None = None,
    ) -> Device:
        """Update the device status with the passed dict."""
        if state_data is not None:
            self.state = State.from_dict(state_data)
            self.generation = generation or _infer_generation(state_data)
        if info_data is not None:
            self.info = Info.from_dict(info_data)
        return self

    def has_wind(self) -> bool:
        """See if the Fan has Breeze Mode."""
        return self.state.wind is not None

    def has_relative_timers(self) -> bool:
        """See if the Fan uses relative (seconds-until-off) sleep timers."""
        return self.generation == Generation.GEN3

    def has_adaptive_learning(self) -> bool:
        """See if the Fan supports adaptive learning (not available on Gen4)."""
        return self.generation != Generation.GEN4

    def has_sleep_timer(self) -> bool:
        """See if the Fan supports sleep timers at all (not available on Gen4)."""
        return self.generation != Generation.GEN4

    def has_identify(self) -> bool:
        """See if the Fan supports the identify/findme function (Gen4 only)."""
        return self.generation == Generation.GEN4
```

Note `has_relative_timers()` now reads `self.generation` instead of inspecting `self.state.fan_timer`/`self.state.light_timer` directly — behaviorally identical (both are driven by the same underlying signal), but now expressed via the single `generation` source of truth per the design spec.

Add the inference helper as a module-level function, right after the `State` class's `from_dict` (before the `Device` class):

```python
def _infer_generation(state_data: dict[str, Any]) -> Generation:
    """Infer gen1_2 vs gen3 from whether relative timer keys are present.

    Only called when no explicit generation is passed to update_from_dict()
    — Gen4 always passes one explicitly, since Gen4 detection happens via
    the /device endpoint before any state dict exists to infer from.
    """
    if STATE_FAN_TIMER in state_data or STATE_LIGHT_TIMER in state_data:
        return Generation.GEN3
    return Generation.GEN1_2
```

`STATE_FAN_TIMER`/`STATE_LIGHT_TIMER` are already imported in `models.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_aiomodernforms.py -v`
Expected: PASS — all tests, including the three new ones and every pre-existing test (this change is additive; `has_relative_timers()`'s return value is unchanged for both fixtures already in the test file).

- [ ] **Step 5: Commit**

```bash
git add aiomodernforms/models.py tests/test_aiomodernforms.py
git commit -m "feat: track an explicit Generation on Device"
```

---

### Task 3: `Light` dataclass, `State.light_fixtures`, `State.to_dict()`

**Files:**
- Modify: `aiomodernforms/const.py`
- Modify: `aiomodernforms/models.py`
- Test: `tests/test_aiomodernforms.py`

**Interfaces:**
- Consumes: nothing new from other tasks.
- Produces: `aiomodernforms.models.Light` dataclass (`address: int | None`, `fixture_type: int | None`, `name: str`, `on: bool`, `brightness: int`, `color_temp_kelvin: int | None`, `min_color_temp_kelvin: int | None`, `max_color_temp_kelvin: int | None`); `State.light_fixtures: list[Light]`; `State.light_color_temp_kelvin: int | None`; `State.to_dict() -> dict[str, Any]`. Task 4 constructs `Light` objects; Tasks 7/8 consume `State.to_dict()` and `State.light_fixtures` for the Gen4 partial-merge pattern.

**Context:** `State.from_dict` builds every field from a flat canonical dict. For Gen 1/2/3, there's only ever one light, so `light_fixtures` gets a single synthetic entry (`address=None`) mirroring the existing flat fields — this keeps `status.light_fixtures[0]` meaningful for every generation, per the design spec. `STATE_LIGHT_FIXTURES` is an internal-only canonical key (never a real wire field on any generation) that Gen4's translation layer (Task 4) sets to a pre-built `list[Light]`; when absent, `State.from_dict` synthesizes the single-entry list itself.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_aiomodernforms.py`, near the other model-level tests (e.g. after `test_generation_gen3_from_relative_timers` from Task 2):

```python
def test_light_fixtures_synthetic_entry_for_legacy():
    """Test that gen1_2/gen3 responses get a single synthetic Light entry."""
    device = Device(state_data=basic_response, info_data=basic_info)
    assert len(device.state.light_fixtures) == 1
    light = device.state.light_fixtures[0]
    assert light.address is None
    assert light.fixture_type is None
    assert light.on == basic_response["lightOn"]
    assert light.brightness == basic_response["lightBrightness"]
    assert light.color_temp_kelvin is None
    assert light.min_color_temp_kelvin is None
    assert light.max_color_temp_kelvin is None
    assert device.state.light_color_temp_kelvin is None


def test_state_to_dict_round_trips_through_from_dict():
    """Test that State.to_dict() is the inverse of State.from_dict()."""
    device = Device(state_data=gen3_relative_timer_response, info_data=gen3_info)
    round_tripped = State.from_dict(device.state.to_dict())
    assert round_tripped == device.state
```

Add `State` to the existing `from aiomodernforms.models import Device, Generation` import (from Task 2), making it:

```python
from aiomodernforms.models import Device, Generation, State
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_aiomodernforms.py::test_light_fixtures_synthetic_entry_for_legacy tests/test_aiomodernforms.py::test_state_to_dict_round_trips_through_from_dict -v`
Expected: FAIL — `AttributeError: 'State' object has no attribute 'light_fixtures'`.

- [ ] **Step 3: Add the new constants**

In `aiomodernforms/const.py`, add after the existing `STATE_LIGHT_TIMER = "lightTimer"` line:

```python
STATE_LIGHT_COLOR_TEMP = "lightColorTemp"
COMMAND_LIGHT_COLOR_TEMP = "lightColorTemp"

# Internal-only canonical key: never a real wire field on any generation.
# Gen4's translation layer sets this to a pre-built list[Light]; absent for
# gen1_2/gen3, where State.from_dict synthesizes a single-entry list itself.
STATE_LIGHT_FIXTURES = "__lightFixtures__"

COMMAND_IDENTIFY = "identify"
```

- [ ] **Step 4: Add the `Light` dataclass and wire it into `State`**

In `aiomodernforms/models.py`, add the `Light` dataclass right before the `State` dataclass:

```python
@dataclass
class Light:
    """One light fixture's state.

    For gen1_2/gen3 (which have exactly one, non-addressable light), this
    is a synthetic entry with address=None and fixture_type=None, mirroring
    State's flat light_on/light_brightness/light_color_temp_kelvin fields.
    For gen4, one real Light exists per light-shaped fixture the device
    reports, with a real address usable for per-fixture control.
    """

    address: int | None
    fixture_type: int | None
    name: str
    on: bool
    brightness: int
    color_temp_kelvin: int | None
    min_color_temp_kelvin: int | None
    max_color_temp_kelvin: int | None
```

Add the new imports to the top of `models.py`'s `from .const import (...)` block: `STATE_LIGHT_COLOR_TEMP` and `STATE_LIGHT_FIXTURES` (keep the existing import list alphabetized alongside them).

In `State`, add two new fields (after the existing `light_timer: int | None = None` line):

```python
    light_color_temp_kelvin: int | None = None
    light_fixtures: list[Light] = field(default_factory=list)
```

This requires changing the `from dataclasses import dataclass` import at the top of `models.py` to `from dataclasses import dataclass, field`.

In `State.from_dict`, add before the final `)` that closes the `return State(...)` call:

```python
            light_color_temp_kelvin=data.get(STATE_LIGHT_COLOR_TEMP),
            light_fixtures=data.get(STATE_LIGHT_FIXTURES) or [
                Light(
                    address=None,
                    fixture_type=None,
                    name="",
                    on=data.get(STATE_LIGHT_POWER, False),
                    brightness=data.get(STATE_LIGHT_BRIGHTNESS, 100),
                    color_temp_kelvin=data.get(STATE_LIGHT_COLOR_TEMP),
                    min_color_temp_kelvin=None,
                    max_color_temp_kelvin=None,
                )
            ],
```

- [ ] **Step 5: Add `State.to_dict()`**

In `aiomodernforms/models.py`, add as a new method on `State` (after `from_dict`):

```python
    def to_dict(self) -> dict[str, Any]:
        """Return this State as a canonical dict — the inverse of from_dict().

        Used by generation-specific control paths (currently only Gen4) that
        receive a partial state change from the device and need to merge it
        onto the full cached state before rebuilding a State.
        """
        return {
            STATE_FAN_POWER: self.fan_on,
            STATE_FAN_SPEED: self.fan_speed,
            STATE_FAN_DIRECTION: self.fan_direction,
            STATE_FAN_SLEEP_TIMER: self.fan_sleep_timer,
            STATE_LIGHT_POWER: self.light_on,
            STATE_LIGHT_BRIGHTNESS: self.light_brightness,
            STATE_LIGHT_COLOR_TEMP: self.light_color_temp_kelvin,
            STATE_LIGHT_SLEEP_TIMER: self.light_sleep_timer,
            STATE_AWAY_MODE: self.away_mode_enabled,
            STATE_ADAPTIVE_LEARNING: self.adaptive_learning_enabled,
            STATE_WIND_POWER: self.wind,
            STATE_WIND_SPEED: self.wind_speed,
            STATE_RF_PAIR_MODE_ACTIVE: self.rf_pair_mode_active,
            STATE_RESET_RF_PAIR_LIST: self.reset_rf_pair_list,
            STATE_FACTORY_RESET: self.factory_reset,
            STATE_DECOMMISSION: self.decommission,
            STATE_SCHEDULE: self.schedule,
            STATE_USER_DATA: self.user_data,
            STATE_FAN_TIMER: self.fan_timer,
            STATE_LIGHT_TIMER: self.light_timer,
            STATE_LIGHT_FIXTURES: self.light_fixtures,
        }
```

`Any` needs to be available — `models.py` already imports `from typing import Any`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_aiomodernforms.py -v`
Expected: PASS — all tests, including the two new ones. `test_state_to_dict_round_trips_through_from_dict` passes `light_fixtures` back through `STATE_LIGHT_FIXTURES` so the round-tripped `State` gets the exact same `Light` list object contents back rather than a re-synthesized one — confirm this by checking the assertion passes, not just that it runs.

- [ ] **Step 7: Commit**

```bash
git add aiomodernforms/const.py aiomodernforms/models.py tests/test_aiomodernforms.py
git commit -m "feat: add Light dataclass, State.light_fixtures, State.to_dict()"
```

---

### Task 4: `aiomodernforms/gen4.py` — read-direction translation

**Files:**
- Create: `aiomodernforms/gen4.py`
- Modify: `aiomodernforms/const.py`
- Test: `tests/test_aiomodernforms.py`

**Interfaces:**
- Consumes: `Light` (Task 3), `Generation` (Task 2).
- Produces: `gen4.is_gen4_system_type(system_type: str) -> bool`; `gen4.classify_fixtures(fixtures: list[dict]) -> tuple[dict | None, list[dict]]`; `gen4.build_state_data(device_data: dict, fan_fixture: dict | None, light_fixtures: list[dict]) -> dict`; `gen4.build_info_data(device_data: dict) -> dict`. Task 6 (`update()` wiring) calls all four directly.

**Context:** This task only adds pure functions — no HTTP, no `ModernFormsDevice` changes yet. Every function takes and returns plain dicts (already-parsed JSON) so it's testable with plain Python dicts, no `aresponses` needed.

- [ ] **Step 1: Add the Gen4 wire-protocol constants**

In `aiomodernforms/const.py`, add at the end of the file:

```python
# --- Gen4 (WAC IoT /device + /fixture) ---

GEN4_DEVICE_API_ENDPOINT = "device"
GEN4_FIXTURE_API_ENDPOINT = "fixture"

# Matched as a case-insensitive substring of a /device response's
# "systemType" value.
GEN4_SYSTEM_TYPE_MARKERS = ("fan_g4",)

GEN4_FIXTURE_ACTION_READ = 3
GEN4_FIXTURE_ACTION_CONTROL = 4

GEN4_FIXTURE_TYPE_FAN = 13
GEN4_LIGHT_FIXTURE_TYPES = frozenset({0, 1, 2, 14, 15})

# Gen4 reports light brightness as 1-10000; this library's public API uses
# 1-100 everywhere (matching gen1_2/gen3) — multiply/divide by this scale.
GEN4_BRIGHTNESS_SCALE = 100

GEN4_FIELD_ACTION = "action"
GEN4_FIELD_ADDR = "addr"
GEN4_FIELD_TYPE = "type"
GEN4_FIELD_NAME = "name"
GEN4_FIELD_STATE = "state"
GEN4_FIELD_DETAIL = "detail"
GEN4_FIELD_FIXTURE_LIST = "fixture"
GEN4_FIELD_STATUS = "status"
GEN4_FIELD_LEVEL = "level"
GEN4_FIELD_MIX_COLOR_TEMP = "mixColorTemp"
GEN4_FIELD_MIN_COLOR_TEMP = "minColorTemp"
GEN4_FIELD_MAX_COLOR_TEMP = "maxColorTemp"
GEN4_FIELD_FINDME = "findme"

GEN4_DEVICE_QUERY = "query"
GEN4_DEVICE_SYSTEM_TYPE = "systemType"
GEN4_DEVICE_NAME = "deviceName"
GEN4_DEVICE_IOTM_VER = "iotmVer"
GEN4_DEVICE_SCM_VER = "scmVer"
GEN4_DEVICE_OWNER = "owner"
GEN4_DEVICE_NWK_STATE = "nwkState"
GEN4_DEVICE_HARD_FACTORY_RESET = "hardFactoryReset"

GEN4_NWK_CERTIFICATE_ID = "certificateID"
GEN4_NWK_RSSI = "rssi"
```

Note `fanSpeed`, `wind`, `windSpeed`, `fanDirection`, and `awayModeEnabled` are **not** redefined here — Gen4 uses the exact same wire key names as the existing `COMMAND_FAN_SPEED`/`COMMAND_WIND`/`COMMAND_WIND_SPEED`/`COMMAND_FAN_DIRECTION`/`STATE_AWAY_MODE` constants (only `fanDirection`'s *value* differs — Gen4 sends a boolean, gen1_2/gen3 a string — reuse the same key constant, translate the value).

- [ ] **Step 2: Write the failing tests**

Add to `tests/test_aiomodernforms.py`, as a new fixture block plus tests. First add the fixtures near the top of the file, after `real_gen2_wifi_signal_config_response`:

```python
gen4_device_response = {
    "systemType": "fan_g4",
    "deviceName": "Fan",
    "owner": "someone@somewhere.com",
    "iotmVer": "01.00.0082",
    "scmVer": "01.00.0012",
    "awayModeEnabled": False,
    "nwkState": {
        "certificateID": "abc123certid",
        "rssi": "-42",
    },
}

gen4_fan_fixture = {
    "addr": 218103808,
    "name": "Fan",
    "type": 13,
    "state": {
        "status": False,
        "fanSpeed": 3,
        "fanDirection": False,
        "wind": False,
        "windSpeed": 2,
    },
}

gen4_light_fixture = {
    "addr": 83951616,
    "name": "Light",
    "type": 1,
    "state": {
        "status": False,
        "level": 5000,
        "mixColorTemp": 3000,
    },
    "detail": {
        "minColorTemp": 2700,
        "maxColorTemp": 5000,
    },
}

gen4_wall_station_fixture = {
    "addr": 184549376,
    "name": "Remote",
    "type": 11,
    "state": {},
}
```

Then add the tests (anywhere after the fixtures, e.g. at the end of the file):

```python
def test_is_gen4_system_type_matches():
    """Test that the fan_g4 systemType marker is recognized."""
    assert gen4.is_gen4_system_type("fan_g4") is True
    assert gen4.is_gen4_system_type("FAN_G4") is True
    assert gen4.is_gen4_system_type("gen3fan") is False
    assert gen4.is_gen4_system_type("strut") is False


def test_classify_fixtures_splits_fan_and_lights():
    """Test that classify_fixtures finds the fan, the light, and ignores others."""
    fan, lights = gen4.classify_fixtures(
        [gen4_fan_fixture, gen4_light_fixture, gen4_wall_station_fixture]
    )
    assert fan == gen4_fan_fixture
    assert lights == [gen4_light_fixture]


def test_classify_fixtures_handles_no_lights():
    """Test that classify_fixtures returns an empty light list when none exist."""
    fan, lights = gen4.classify_fixtures([gen4_fan_fixture])
    assert fan == gen4_fan_fixture
    assert lights == []


def test_build_state_data_maps_fan_and_light_fields():
    """Test that build_state_data produces the canonical dict State.from_dict expects."""
    state_data = gen4.build_state_data(
        gen4_device_response, gen4_fan_fixture, [gen4_light_fixture]
    )
    assert state_data[STATE_FAN_POWER] is False
    assert state_data[STATE_FAN_SPEED] == 3
    assert state_data[STATE_FAN_DIRECTION] == "forward"
    assert state_data[STATE_WIND_POWER] is False
    assert state_data[STATE_WIND_SPEED] == 2
    assert state_data[STATE_AWAY_MODE] is False
    assert state_data[STATE_LIGHT_POWER] is False
    assert state_data[STATE_LIGHT_BRIGHTNESS] == 50
    assert state_data[STATE_LIGHT_COLOR_TEMP] == 3000

    light_fixtures = state_data[STATE_LIGHT_FIXTURES]
    assert len(light_fixtures) == 1
    light = light_fixtures[0]
    assert light.address == 83951616
    assert light.fixture_type == 1
    assert light.name == "Light"
    assert light.min_color_temp_kelvin == 2700
    assert light.max_color_temp_kelvin == 5000


def test_build_state_data_reverse_direction():
    """Test that a True fanDirection (gen4 boolean) maps to the reverse string."""
    reversed_fan = {**gen4_fan_fixture, "state": {**gen4_fan_fixture["state"], "fanDirection": True}}
    state_data = gen4.build_state_data(gen4_device_response, reversed_fan, [])
    assert state_data[STATE_FAN_DIRECTION] == "reverse"


def test_build_state_data_no_lights_uses_synthetic_default():
    """Test that a fan with zero light fixtures gets a sensible default light."""
    state_data = gen4.build_state_data(gen4_device_response, gen4_fan_fixture, [])
    assert state_data[STATE_LIGHT_FIXTURES] == []
    assert state_data[STATE_LIGHT_POWER] is False
    assert state_data[STATE_LIGHT_BRIGHTNESS] == 100


def test_build_info_data_maps_device_fields():
    """Test that build_info_data maps /device fields into canonical INFO_* keys."""
    info_data = gen4.build_info_data(gen4_device_response)
    assert info_data[INFO_DEVICE_NAME] == "Fan"
    assert info_data[INFO_FIRMWARE_VERSION] == "01.00.0082"
    assert info_data[INFO_MAIN_MCU_FIRMWARE_VERSION] == "01.00.0012"
    assert info_data[INFO_OWNER] == "someone@somewhere.com"
```

Add the new imports these tests need to the top of `tests/test_aiomodernforms.py`:

```python
from aiomodernforms import gen4
from aiomodernforms.const import (
    INFO_DEVICE_NAME,
    INFO_FIRMWARE_VERSION,
    INFO_MAIN_MCU_FIRMWARE_VERSION,
    INFO_OWNER,
    STATE_LIGHT_COLOR_TEMP,
    STATE_LIGHT_FIXTURES,
)
```

(Add these alongside the existing `from aiomodernforms.const import (...)` block rather than as a second block — keep one alphabetized import per module, matching the file's existing style.)

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_aiomodernforms.py -k "gen4 or is_gen4 or classify_fixtures or build_state_data or build_info_data" -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'aiomodernforms.gen4'`.

- [ ] **Step 4: Create `aiomodernforms/gen4.py`**

```python
"""Translate between the Gen4 WAC IoT wire protocol and this library's
canonical (legacy-shaped) state/info dictionaries.

Gen4 fans speak the WAC IoT `/device` + `/fixture` REST model instead of
Gen 1/2/3's flat `/mf` shadow. Every function here is a pure translation
step — no HTTP happens in this module; `ModernFormsDevice` is the only
thing that makes requests.
"""

from __future__ import annotations

from typing import Any

from .const import (
    COMMAND_FAN_DIRECTION,
    COMMAND_FAN_SPEED,
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
    GEN4_FIELD_ADDR,
    GEN4_FIELD_DETAIL,
    GEN4_FIELD_MAX_COLOR_TEMP,
    GEN4_FIELD_MIN_COLOR_TEMP,
    GEN4_FIELD_MIX_COLOR_TEMP,
    GEN4_FIELD_NAME,
    GEN4_FIELD_STATE,
    GEN4_FIELD_STATUS,
    GEN4_FIELD_TYPE,
    GEN4_FIXTURE_TYPE_FAN,
    GEN4_LIGHT_FIXTURE_TYPES,
    GEN4_SYSTEM_TYPE_MARKERS,
    INFO_DEVICE_NAME,
    INFO_FIRMWARE_VERSION,
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
    raw_level = state.get(
        "level", LIGHT_BRIGHTNESS_HIGH_VALUE * GEN4_BRIGHTNESS_SCALE
    )
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


def build_info_data(device_data: dict[str, Any]) -> dict[str, Any]:
    """Build a canonical info dict from a Gen4 /device response."""
    return {
        INFO_DEVICE_NAME: device_data.get(GEN4_DEVICE_NAME, ""),
        INFO_FIRMWARE_VERSION: device_data.get(GEN4_DEVICE_IOTM_VER, ""),
        INFO_MAIN_MCU_FIRMWARE_VERSION: device_data.get(GEN4_DEVICE_SCM_VER, ""),
        INFO_OWNER: device_data.get(GEN4_DEVICE_OWNER, ""),
    }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_aiomodernforms.py -v`
Expected: PASS — all tests, including every new one from this task.

- [ ] **Step 6: Commit**

```bash
git add aiomodernforms/gen4.py aiomodernforms/const.py tests/test_aiomodernforms.py
git commit -m "feat: add gen4.py read-direction fixture/device translation"
```

---

### Task 5: `aiomodernforms/gen4.py` — control-direction translation

**Files:**
- Modify: `aiomodernforms/gen4.py`
- Modify: `aiomodernforms/const.py`
- Test: `tests/test_aiomodernforms.py`

**Interfaces:**
- Consumes: `COMMAND_LIGHT_COLOR_TEMP`, `COMMAND_IDENTIFY` (added in Task 3).
- Produces: `gen4.build_fan_control_state(commands: dict) -> dict`; `gen4.build_light_control_state(commands: dict) -> dict`; `gen4.parse_fan_control_response(state: dict) -> dict`; `gen4.parse_light_control_response(state: dict) -> dict`. Tasks 7/8 (`fan()`/`light()`/`light_fixture()`) call all four.

**Context:** `fan()`/`light()`/`light_fixture()` already build a canonical `commands` dict using existing `COMMAND_*` keys (e.g. `{COMMAND_FAN_POWER: True, COMMAND_FAN_SPEED: 3}`) before deciding how to send it. These functions translate that same canonical dict into a Gen4 fixture `state` object for the `/fixture` control request, and translate the device's echoed `state` back into canonical `STATE_*` keys for merging onto the cached `State` (via `State.to_dict()` from Task 3).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_aiomodernforms.py`:

```python
def test_build_fan_control_state_translates_all_fields():
    """Test that a canonical fan commands dict becomes a gen4 fixture state."""
    commands = {
        aiomodernforms.COMMAND_FAN_POWER: True,
        aiomodernforms.COMMAND_FAN_SPEED: 4,
        aiomodernforms.COMMAND_FAN_DIRECTION: aiomodernforms.FAN_DIRECTION_REVERSE,
        aiomodernforms.COMMAND_WIND: True,
        aiomodernforms.COMMAND_WIND_SPEED: 2,
        COMMAND_IDENTIFY: True,
    }
    state = gen4.build_fan_control_state(commands)
    assert state == {
        "status": True,
        "fanSpeed": 4,
        "fanDirection": True,
        "wind": True,
        "windSpeed": 2,
        "findme": True,
    }


def test_build_fan_control_state_only_includes_given_fields():
    """Test that fields not present in commands are omitted, not defaulted."""
    state = gen4.build_fan_control_state({aiomodernforms.COMMAND_FAN_POWER: False})
    assert state == {"status": False}


def test_build_light_control_state_scales_brightness():
    """Test that a canonical light commands dict becomes a gen4 fixture state."""
    commands = {
        aiomodernforms.COMMAND_LIGHT_POWER: True,
        aiomodernforms.COMMAND_LIGHT_BRIGHTNESS: 75,
        COMMAND_LIGHT_COLOR_TEMP: 3000,
        COMMAND_IDENTIFY: False,
    }
    state = gen4.build_light_control_state(commands)
    assert state == {
        "status": True,
        "level": 7500,
        "mixColorTemp": 3000,
        "findme": False,
    }


def test_parse_fan_control_response_translates_back():
    """Test that an echoed gen4 fan state maps back to canonical STATE_* keys."""
    result = gen4.parse_fan_control_response(
        {"status": True, "fanSpeed": 4, "fanDirection": True, "wind": False}
    )
    assert result == {
        STATE_FAN_POWER: True,
        STATE_FAN_SPEED: 4,
        STATE_FAN_DIRECTION: "reverse",
        STATE_WIND_POWER: False,
    }


def test_parse_light_control_response_scales_brightness_back():
    """Test that an echoed gen4 light state maps back to canonical STATE_* keys."""
    result = gen4.parse_light_control_response(
        {"status": True, "level": 2500, "mixColorTemp": 4000}
    )
    assert result == {
        STATE_LIGHT_POWER: True,
        STATE_LIGHT_BRIGHTNESS: 25,
        STATE_LIGHT_COLOR_TEMP: 4000,
    }
```

Add the new imports these tests need:

```python
from aiomodernforms.const import (
    COMMAND_IDENTIFY,
    COMMAND_LIGHT_COLOR_TEMP,
    STATE_FAN_DIRECTION,
    STATE_FAN_POWER,
    STATE_FAN_SPEED,
    STATE_WIND_POWER,
)
```

(Merge these alphabetically into the existing `from aiomodernforms.const import (...)` block rather than adding a second one.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_aiomodernforms.py -k "control_state or control_response" -v`
Expected: FAIL with `AttributeError: module 'aiomodernforms.gen4' has no attribute 'build_fan_control_state'`.

- [ ] **Step 3: Add the control-direction functions**

In `aiomodernforms/gen4.py`, add `COMMAND_FAN_POWER`, `COMMAND_IDENTIFY`, `COMMAND_LIGHT_BRIGHTNESS`, `COMMAND_LIGHT_COLOR_TEMP`, `COMMAND_LIGHT_POWER` to the existing `from .const import (...)` block (alphabetized in), then append these four functions at the end of the file:

```python
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
    """Translate a canonical light()/light_fixture() command dict into a
    Gen4 fixture state."""
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
    """Translate an echoed Gen4 fan-fixture state back into canonical
    STATE_* keys, for merging onto the cached State."""
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
    """Translate an echoed Gen4 light-fixture state back into canonical
    STATE_* keys, for merging onto the cached State."""
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_aiomodernforms.py -v`
Expected: PASS — all tests.

- [ ] **Step 5: Commit**

```bash
git add aiomodernforms/gen4.py aiomodernforms/const.py tests/test_aiomodernforms.py
git commit -m "feat: add gen4.py control-direction fixture translation"
```

---

### Task 6: `ModernFormsDevice.update()` — Gen4 detection and wiring

**Files:**
- Modify: `aiomodernforms/modernforms.py`
- Test: `tests/test_aiomodernforms.py`

**Interfaces:**
- Consumes: `gen4.is_gen4_system_type`, `gen4.classify_fixtures`, `gen4.build_state_data`, `gen4.build_info_data` (Task 4); `Generation` (Task 2).
- Produces: `ModernFormsDevice._is_gen4: bool | None` (new private attribute); `ModernFormsDevice._gen4_fan_addr: int | None` (new private attribute, the fan fixture's address once discovered — used by Task 7). `update()`'s public signature/return type is unchanged.

**Context:** `update()` currently is:

```python
@backoff.on_exception(
    backoff.expo, ModernFormsEmptyResponseError, max_tries=3, logger=None
)
async def update(self, full_update: bool = False) -> Device:
    """Get all information about the device in a single call."""
    info_data = await self._request({COMMAND_QUERY_STATIC_DATA: True})
    state_data = await self._request()
    if not state_data:
        raise ModernFormsEmptyResponseError(
            f"Modern Forms device at {self._host}"
            + " returned an empty API response on full update"
        )
    if self._device is None or full_update:
        self._device = Device(state_data=state_data, info_data=info_data)
    self._device.update_from_dict(state_data=state_data)
    return self._device
```

`self._request(commands, path)` already accepts an arbitrary `path` (used today for `/config-read` in `config()`), so no changes to `_request()` itself are needed — Gen4 requests just pass a different `path`.

**Detection order:** `update()` tries the long-supported `/mf` endpoint *first*, exactly as it always has, and only probes `/device` if that fails. This means every existing Gen 1/2/3 test keeps working with **zero changes** (their mocked `/mf` calls succeed immediately, so `/device` is never touched), there's no extra request added for the — overwhelmingly common today — legacy case, and detection still correctly reaches a real Gen4 fan (which is expected not to have `/mf` at all, so the first request fails and triggers the `/device` probe).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_aiomodernforms.py`, right after the `gen4_wall_station_fixture` dict (added in Task 4), a small helper every Gen4 test from here on will reuse:

```python
def _mock_gen4_device(aresponses, fixtures=None):
    """Register the request sequence a Gen4 device's first update() makes.

    update() tries /mf first (so legacy fans need no special mocking) and
    only falls back to probing /device when that fails — so every Gen4 test
    must mock /mf failing first, then /device, then /fixture, in that order.
    """
    aresponses.add(
        "fan.local", "/mf", "POST", response=aresponses.Response(text="not found", status=404)
    )
    aresponses.add("fan.local", "/device", "POST", response=gen4_device_response)
    fixture_list = (
        fixtures if fixtures is not None else [gen4_fan_fixture, gen4_light_fixture]
    )
    aresponses.add(
        "fan.local",
        "/fixture",
        "POST",
        response={
            "action": 3,
            "result": "0",
            "count": len(fixture_list),
            "fixture": fixture_list,
        },
    )
```

Then add the tests:

```python
@pytest.mark.asyncio
async def test_update_detects_gen4(aresponses):
    """Test that update() falls back to /device and detects a Gen4 fan."""
    _mock_gen4_device(aresponses)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        assert device._device.generation == Generation.GEN4
        assert device.status.fan_speed == 3
        assert device.status.light_brightness == 50
        assert len(device.status.light_fixtures) == 1
        assert device.info.device_name == "Fan"
        assert device._gen4_fan_addr == 218103808


@pytest.mark.asyncio
async def test_update_uses_legacy_without_probing_device(aresponses):
    """Test that update() never touches /device when /mf succeeds immediately."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        assert device._device.generation == Generation.GEN1_2
        assert device.status.fan_speed == basic_response["fanSpeed"]
        # No /device mock was registered above — if update() had probed it,
        # aresponses would raise a route-not-found error for that request.


@pytest.mark.asyncio
async def test_update_reraises_legacy_error_when_device_also_not_gen4(aresponses):
    """Test that a device failing both /mf and /device surfaces the /mf error."""
    aresponses.add(
        "fan.local", "/mf", "POST", response=aresponses.Response(text="not found", status=404)
    )
    aresponses.add(
        "fan.local", "/device", "POST", response=aresponses.Response(text="not found", status=404)
    )

    with pytest.raises(aiomodernforms.ModernFormsError):
        async with aiomodernforms.ModernFormsDevice("fan.local") as device:
            await device.update()


@pytest.mark.asyncio
async def test_update_only_probes_gen4_once(aresponses):
    """Test that a second update() call skips straight to /device + /fixture."""
    _mock_gen4_device(aresponses)
    aresponses.add("fan.local", "/device", "POST", response=gen4_device_response)
    aresponses.add(
        "fan.local",
        "/fixture",
        "POST",
        response={
            "action": 3,
            "result": "0",
            "count": 2,
            "fixture": [gen4_fan_fixture, gen4_light_fixture],
        },
    )

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        await device.update()
        # The second update() call has no /mf mock registered and only one
        # more /device + /fixture pair above — if it had re-attempted /mf or
        # re-probed generation an extra time, aresponses would raise.
```

Add `Generation` to the existing `from aiomodernforms.models import Device, Generation, State` import (already present from Task 3).

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_aiomodernforms.py -k "test_update_detects_gen4 or test_update_uses_legacy or test_update_reraises or test_update_only_probes" -v`
Expected: FAIL — `test_update_detects_gen4` fails because `update()` still only ever calls `/mf`, so `aresponses` raises for the unmatched `/device`/`/fixture` routes; `device._gen4_fan_addr` doesn't exist yet either.

- [ ] **Step 3: Implement Gen4 detection and update wiring**

In `aiomodernforms/modernforms.py`, add to the `from .const import (...)` block: `GEN4_DEVICE_API_ENDPOINT`, `GEN4_DEVICE_QUERY`, `GEN4_DEVICE_SYSTEM_TYPE`, `GEN4_FIELD_ACTION`, `GEN4_FIELD_ADDR`, `GEN4_FIELD_FIXTURE_LIST`, `GEN4_FIXTURE_ACTION_READ`, `GEN4_FIXTURE_API_ENDPOINT` (alphabetized in). Add `from . import gen4` and `from .models import ConfigInfo, Device, Generation` (extending the existing `from .models import ConfigInfo, Device` line).

Add two new instance attributes in `__init__`, alongside the existing `self._device: Device | None = None` class attribute — add these as instance attributes at the end of `__init__` (after `self._user_agent = f"AIOModernForms/{__version__}"` handling):

```python
        self._is_gen4: bool | None = None
        self._gen4_fan_addr: int | None = None
```

Replace `update()` with:

```python
    @backoff.on_exception(
        backoff.expo, ModernFormsEmptyResponseError, max_tries=3, logger=None
    )
    async def update(self, full_update: bool = False) -> Device:
        """Get all information about the device in a single call."""
        if self._is_gen4:
            await self._update_gen4(full_update=full_update)
            return self._device  # type: ignore[return-value]
        if self._is_gen4 is False:
            return await self._update_legacy(full_update=full_update)

        # Generation not yet known: try the long-supported /mf endpoint
        # first (so every existing legacy fan keeps working exactly as
        # before, with no extra request), and only probe /device for Gen4
        # if that fails.
        try:
            result = await self._update_legacy(full_update=full_update)
        except ModernFormsError:
            if await self._probe_gen4():
                self._is_gen4 = True
                await self._update_gen4(full_update=full_update)
                return self._device  # type: ignore[return-value]
            raise
        self._is_gen4 = False
        return result

    async def _update_legacy(self, full_update: bool = False) -> Device:
        """Gen 1/2/3 update() body — the flat /mf shadow protocol."""
        info_data = await self._request({COMMAND_QUERY_STATIC_DATA: True})
        state_data = await self._request()
        if not state_data:
            raise ModernFormsEmptyResponseError(
                f"Modern Forms device at {self._host}"
                + " returned an empty API response on full update"
            )
        if self._device is None or full_update:
            self._device = Device(state_data=state_data, info_data=info_data)
        self._device.update_from_dict(state_data=state_data)
        return self._device

    async def _probe_gen4(self) -> bool:
        """Check whether /device identifies this as a Gen4 fan."""
        try:
            device_data = await self._request(
                {GEN4_DEVICE_QUERY: True}, path=GEN4_DEVICE_API_ENDPOINT
            )
        except ModernFormsError:
            return False
        system_type = device_data.get(GEN4_DEVICE_SYSTEM_TYPE, "")
        return gen4.is_gen4_system_type(system_type)

    async def _update_gen4(self, full_update: bool = False) -> None:
        """Gen4 equivalent of _update_legacy() — the /device + /fixture protocol."""
        device_data = await self._request(
            {GEN4_DEVICE_QUERY: True}, path=GEN4_DEVICE_API_ENDPOINT
        )
        fixture_response = await self._request(
            {GEN4_FIELD_ACTION: GEN4_FIXTURE_ACTION_READ},
            path=GEN4_FIXTURE_API_ENDPOINT,
        )
        fixtures = fixture_response.get(GEN4_FIELD_FIXTURE_LIST, [])
        fan_fixture, light_fixtures = gen4.classify_fixtures(fixtures)
        self._gen4_fan_addr = (fan_fixture or {}).get(GEN4_FIELD_ADDR)

        state_data = gen4.build_state_data(device_data, fan_fixture, light_fixtures)
        info_data = gen4.build_info_data(device_data)

        if self._device is None or full_update:
            self._device = Device(
                state_data=state_data, info_data=info_data, generation=Generation.GEN4
            )
        else:
            self._device.update_from_dict(
                state_data=state_data, generation=Generation.GEN4
            )
```

`ModernFormsError` is already imported in `modernforms.py`. Note `_update_legacy()` and `_update_gen4()` are private (leading underscore) — `update()` remains the only public entry point, so this is purely an internal refactor of what was previously `update()`'s inline body.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_aiomodernforms.py -v`
Expected: PASS — all tests. Every pre-existing legacy test needs **no changes** for this task: `update()` still tries `/mf` first exactly as before, so `_probe_gen4()`/`_update_gen4()` are never reached by any test that doesn't explicitly make `/mf` fail first.

- [ ] **Step 5: Commit**

```bash
git add aiomodernforms/modernforms.py tests/test_aiomodernforms.py
git commit -m "feat: detect and wire up Gen4 devices in update()"
```

---

### Task 7: `ModernFormsDevice.fan()` — Gen4 control path

**Files:**
- Modify: `aiomodernforms/modernforms.py`
- Test: `tests/test_aiomodernforms.py`

**Interfaces:**
- Consumes: `gen4.build_fan_control_state`, `gen4.parse_fan_control_response` (Task 5); `self._gen4_fan_addr` (Task 6); `State.to_dict()` (Task 3).
- Produces: `fan()` gains a new optional keyword-only parameter `identify: bool | None = None`. Existing parameters/behavior for gen1_2/gen3 are unchanged. New private helper `ModernFormsDevice._apply_gen4_state_change(changes: dict) -> None`, also used by Task 9 (`away()`).

**Context:** `fan()` currently builds a `commands` dict via existing validation logic, then unconditionally calls `await self.request(commands=commands)` at the end, which POSTs to `/mf` and expects a full-shadow response. For Gen4, the same validated `commands` dict needs to be translated and POSTed to `/fixture` instead, and the response merged onto cached state rather than replacing it wholesale.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_aiomodernforms.py`:

```python
@pytest.mark.asyncio
async def test_fan_gen4_sends_to_fixture_endpoint(aresponses):
    """Test that fan() on a Gen4 device posts to /fixture with the real addr."""
    _mock_gen4_device(aresponses)

    async def evaluate_request(request):
        data = await request.json()
        assert data["action"] == 4
        assert data["addr"] == 218103808
        assert data["state"] == {"status": True, "fanSpeed": 5}
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps({"action": 4, "result": "0", "state": {"status": True, "fanSpeed": 5}}),
        )

    aresponses.add("fan.local", "/fixture", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        await device.fan(on=True, speed=5)
        assert device.status.fan_on is True
        assert device.status.fan_speed == 5
        # Fields not touched by this call stay at their pre-call values.
        assert device.status.light_brightness == 50


@pytest.mark.asyncio
async def test_fan_gen4_identify(aresponses):
    """Test that fan(identify=True) sends findme to the fixture."""
    _mock_gen4_device(aresponses)

    async def evaluate_request(request):
        data = await request.json()
        assert data["state"] == {"findme": True}
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps({"action": 4, "result": "0", "state": {}}),
        )

    aresponses.add("fan.local", "/fixture", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        await device.fan(identify=True)


@pytest.mark.asyncio
async def test_fan_gen4_sleep_is_a_silent_noop(aresponses):
    """Test that fan(sleep=...) on Gen4 sends no timer field at all."""
    _mock_gen4_device(aresponses)

    async def evaluate_request(request):
        data = await request.json()
        assert data["state"] == {"status": True}
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps({"action": 4, "result": "0", "state": {"status": True}}),
        )

    aresponses.add("fan.local", "/fixture", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        await device.fan(on=True, sleep=90)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_aiomodernforms.py -k "test_fan_gen4" -v`
Expected: FAIL — `fan()` doesn't accept `identify=`, and even without it, `aresponses` raises a route-not-found error because `fan()` still posts to `/mf`.

- [ ] **Step 3: Implement the Gen4 branch in `fan()`**

In `aiomodernforms/modernforms.py`, add `GEN4_FIXTURE_ACTION_CONTROL` to the `from .const import (...)` block (already importing `GEN4_FIXTURE_ACTION_READ` from Task 6 — add `GEN4_FIXTURE_ACTION_CONTROL` alongside it) and `COMMAND_IDENTIFY`.

Add the merge helper as a new private method (place it right after `_sleep_command`):

```python
    def _apply_gen4_state_change(self, changes: dict[str, Any]) -> None:
        """Merge a partial canonical state change onto the cached State (Gen4)."""
        full = self._device.state.to_dict()  # type: ignore[union-attr]
        full.update(changes)
        self._device.update_from_dict(  # type: ignore[union-attr]
            state_data=full, generation=Generation.GEN4
        )
```

In `fan()`, add `identify: bool | None = None` to the signature (after `wind_speed: int | None = None,`):

```python
    async def fan(
        self,
        *,
        on: bool | None = None,
        sleep: int | datetime | None = None,
        speed: int | None = None,
        direction: str | None = None,
        wind: bool | None = None,
        wind_speed: int | None = None,
        identify: bool | None = None,
    ) -> None: ...
```

Immediately before the existing `if sleep is not None:` block, change it to skip sending a timer command on Gen4:

```python
        if sleep is not None and self._device.generation != Generation.GEN4:
            commands.update(
                self._sleep_command(COMMAND_FAN_SLEEP_TIMER, COMMAND_FAN_TIMER, sleep)
            )
```

(This replaces the existing unconditional `if sleep is not None:` block — same body, just gated by the added `and self._device.generation != Generation.GEN4` on the `if`.)

After the existing `if direction is not None:` block and the existing `if self._device is not None and self._device.has_wind():` wind block, add the `identify` command:

```python
        if identify is not None:
            commands[COMMAND_IDENTIFY] = identify
```

Finally, replace the function's last line (`await self.request(commands=commands)`) with:

```python
        if self._device.generation == Generation.GEN4:
            wire_state = gen4.build_fan_control_state(commands)
            if wire_state:
                response = await self._request(
                    {
                        "action": GEN4_FIXTURE_ACTION_CONTROL,
                        "addr": self._gen4_fan_addr,
                        "state": wire_state,
                    },
                    path=GEN4_FIXTURE_API_ENDPOINT,
                )
                changes = gen4.parse_fan_control_response(response.get("state", {}))
                self._apply_gen4_state_change(changes)
            return

        await self.request(commands=commands)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_aiomodernforms.py -v`
Expected: PASS — all tests, including the three new Gen4 `fan()` tests and every pre-existing `fan()` test (the new `Generation.GEN4` branch is only reached when `self._device.generation == Generation.GEN4`, which no gen1_2/gen3 test triggers).

- [ ] **Step 5: Commit**

```bash
git add aiomodernforms/modernforms.py tests/test_aiomodernforms.py
git commit -m "feat: add Gen4 control path to fan()"
```

---

### Task 8: `ModernFormsDevice.light()` and new `light_fixture()` — Gen4 control path

**Files:**
- Modify: `aiomodernforms/modernforms.py`
- Test: `tests/test_aiomodernforms.py`

**Interfaces:**
- Consumes: `gen4.build_light_control_state`, `gen4.parse_light_control_response` (Task 5); `_apply_gen4_state_change` (Task 7); `dataclasses.replace`.
- Produces: `light()` gains `color_temp_kelvin: int | None = None` and `identify: bool | None = None` new optional keyword-only parameters. New public method `light_fixture(address: int | None, *, brightness=None, on=None, color_temp_kelvin=None, identify=None) -> None`. New `has_identify()` wrapper on `ModernFormsDevice` (mirroring `has_breeze_mode()`).

**Context:** `light()` has more branching than `fan()` (the brightness-before-on flash-avoidance logic), but the same principle applies: build the canonical `commands` dict as today, then dispatch based on generation. `light_fixture()` is the new generalized method — `light()` becomes a thin wrapper around it that always targets `status.light_fixtures[0].address`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_aiomodernforms.py`:

```python
@pytest.mark.asyncio
async def test_light_gen4_sends_to_primary_fixture(aresponses):
    """Test that light() on Gen4 controls light_fixtures[0]'s real address."""
    _mock_gen4_device(aresponses)

    async def evaluate_request(request):
        data = await request.json()
        assert data["addr"] == 83951616
        assert data["state"] == {"status": True, "level": 8000}
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps({"action": 4, "result": "0", "state": {"status": True, "level": 8000}}),
        )

    aresponses.add("fan.local", "/fixture", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        await device.light(on=True, brightness=80)
        assert device.status.light_on is True
        assert device.status.light_brightness == 80
        assert device.status.light_fixtures[0].on is True
        assert device.status.light_fixtures[0].brightness == 80


@pytest.mark.asyncio
async def test_light_gen4_color_temp(aresponses):
    """Test that light(color_temp_kelvin=...) sends mixColorTemp."""
    _mock_gen4_device(aresponses)

    async def evaluate_request(request):
        data = await request.json()
        assert data["state"] == {"mixColorTemp": 4500}
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps({"action": 4, "result": "0", "state": {"mixColorTemp": 4500}}),
        )

    aresponses.add("fan.local", "/fixture", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        await device.light(color_temp_kelvin=4500)
        assert device.status.light_color_temp_kelvin == 4500


@pytest.mark.asyncio
async def test_light_color_temp_ignored_on_legacy(aresponses):
    """Test that color_temp_kelvin is silently dropped for gen1_2/gen3."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async def evaluate_request(request):
        data = await request.json()
        assert aiomodernforms.COMMAND_LIGHT_POWER in data
        assert COMMAND_LIGHT_COLOR_TEMP not in data
        modified_response = basic_response.copy()
        modified_response[STATE_LIGHT_POWER] = data[aiomodernforms.COMMAND_LIGHT_POWER]
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(modified_response),
        )

    aresponses.add("fan.local", "/mf", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        await device.light(on=True, color_temp_kelvin=4500)


@pytest.mark.asyncio
async def test_light_fixture_controls_a_specific_address(aresponses):
    """Test that light_fixture() addresses a light directly, not via index 0."""
    second_light = {**gen4_light_fixture, "addr": 83951617, "name": "Uplight"}
    _mock_gen4_device(aresponses, fixtures=[gen4_fan_fixture, gen4_light_fixture, second_light])

    async def evaluate_request(request):
        data = await request.json()
        assert data["addr"] == 83951617
        assert data["state"] == {"status": True}
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps({"action": 4, "result": "0", "state": {"status": True}}),
        )

    aresponses.add("fan.local", "/fixture", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        assert len(device.status.light_fixtures) == 2
        await device.light_fixture(83951617, on=True)
        assert device.status.light_fixtures[1].on is True
        # The primary light (index 0) and its flat mirror fields are untouched.
        assert device.status.light_fixtures[0].on is False
        assert device.status.light_on is False


@pytest.mark.asyncio
async def test_light_fixture_none_address_routes_through_legacy(aresponses):
    """Test that light_fixture(None, ...) works on gen1_2/gen3 like light()."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async def evaluate_request(request):
        data = await request.json()
        assert aiomodernforms.COMMAND_LIGHT_POWER in data
        modified_response = basic_response.copy()
        modified_response[STATE_LIGHT_POWER] = data[aiomodernforms.COMMAND_LIGHT_POWER]
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(modified_response),
        )

    aresponses.add("fan.local", "/mf", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        await device.light_fixture(None, on=True)
        assert device.status.light_on is True


def test_has_identify_true_only_for_gen4():
    """Test has_identify() reflects generation."""
    legacy_device = Device(state_data=basic_response, info_data=basic_info)
    gen4_device = Device(state_data=basic_response, info_data=basic_info, generation=Generation.GEN4)
    assert legacy_device.has_identify() is False
    assert gen4_device.has_identify() is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_aiomodernforms.py -k "light_gen4 or light_fixture or light_color_temp_ignored or has_identify" -v`
Expected: FAIL — `light()` doesn't accept `color_temp_kelvin=`/`identify=` yet, `light_fixture()` doesn't exist, `has_identify()` doesn't exist on `ModernFormsDevice`.

- [ ] **Step 3: Implement `light_fixture()`, rewire `light()`, add `has_identify()`**

In `aiomodernforms/modernforms.py`, add `from dataclasses import replace` to the imports, and add `COMMAND_LIGHT_COLOR_TEMP` to the `from .const import (...)` block.

Add `has_identify()` right after `has_relative_timers()`:

```python
    def has_identify(self):
        """See if the Fan supports the identify/findme function (Gen4 only)."""
        if self._device is None:
            raise ModernFormsNotInitializedError(
                "The device has not been initialized.  "
                + "Please run update on the device before getting state"
            )
        return self._device.has_identify()
```

Add a light-specific merge helper right after `_apply_gen4_state_change` (from Task 7):

```python
    def _apply_gen4_light_change(self, address: int | None, changes: dict[str, Any]) -> None:
        """Merge a partial light-fixture state change onto the cached State (Gen4)."""
        lights = list(self._device.state.light_fixtures)  # type: ignore[union-attr]
        for i, light in enumerate(lights):
            if light.address == address:
                lights[i] = replace(
                    light,
                    on=changes.get(STATE_LIGHT_POWER, light.on),
                    brightness=changes.get(STATE_LIGHT_BRIGHTNESS, light.brightness),
                    color_temp_kelvin=changes.get(
                        STATE_LIGHT_COLOR_TEMP, light.color_temp_kelvin
                    ),
                )
                break

        full = self._device.state.to_dict()  # type: ignore[union-attr]
        full[STATE_LIGHT_FIXTURES] = lights
        if lights and lights[0].address == address:
            full[STATE_LIGHT_POWER] = lights[0].on
            full[STATE_LIGHT_BRIGHTNESS] = lights[0].brightness
            full[STATE_LIGHT_COLOR_TEMP] = lights[0].color_temp_kelvin
        self._device.update_from_dict(  # type: ignore[union-attr]
            state_data=full, generation=Generation.GEN4
        )
```

Now replace `light()` entirely with a version that delegates to a new `light_fixture()`:

```python
    async def light(
        self,
        *,
        brightness: int | None = None,
        on: bool | None = None,
        sleep: int | datetime | None = None,
        color_temp_kelvin: int | None = None,
        identify: bool | None = None,
    ):
        """Change Fans Light state — always controls the primary light.

        When both brightness and on=True are given, brightness is sent in
        its own request first to avoid the fan briefly flashing at the
        previous brightness. See issue #99.
        """
        if self._device is None:
            await self.update()

        address = self._device.state.light_fixtures[0].address

        if brightness is not None and (
            not isinstance(brightness, int)
            or int(brightness) < LIGHT_BRIGHTNESS_LOW_VALUE
            or int(brightness) > LIGHT_BRIGHTNESS_HIGH_VALUE
        ):
            raise ModernFormsInvalidSettingsError(
                "brightness value must be between"
                + f" {LIGHT_BRIGHTNESS_LOW_VALUE} and {LIGHT_BRIGHTNESS_HIGH_VALUE}"
            )

        if on is not None and not isinstance(on, bool):
            raise ModernFormsInvalidSettingsError("on must be a boolean")

        if brightness is not None and on is True:
            # Setting brightness and turning on in a single request makes the
            # fan briefly show the previous brightness before jumping to the
            # new one. Sending brightness first avoids the flash.
            await self.light_fixture(address, brightness=brightness)
            await self.light_fixture(address, on=on, sleep=sleep, identify=identify)
            return

        await self.light_fixture(
            address,
            brightness=brightness,
            on=on,
            sleep=sleep,
            color_temp_kelvin=color_temp_kelvin,
            identify=identify,
        )

    async def light_fixture(
        self,
        address: int | None,
        *,
        brightness: int | None = None,
        on: bool | None = None,
        sleep: int | datetime | None = None,
        color_temp_kelvin: int | None = None,
        identify: bool | None = None,
    ):
        """Change one light fixture's state.

        `address` is a value from `status.light_fixtures[*].address` — pass
        `None` to target the gen1_2/gen3 synthetic entry (routes through the
        legacy /mf endpoint); pass a real address to control a specific
        Gen4 light fixture via /fixture.
        """
        if self._device is None:
            await self.update()

        if brightness is not None and (
            not isinstance(brightness, int)
            or int(brightness) < LIGHT_BRIGHTNESS_LOW_VALUE
            or int(brightness) > LIGHT_BRIGHTNESS_HIGH_VALUE
        ):
            raise ModernFormsInvalidSettingsError(
                "brightness value must be between"
                + f" {LIGHT_BRIGHTNESS_LOW_VALUE} and {LIGHT_BRIGHTNESS_HIGH_VALUE}"
            )

        if on is not None and not isinstance(on, bool):
            raise ModernFormsInvalidSettingsError("on must be a boolean")

        sleep_commands: dict[str, int] = {}
        if sleep is not None and self._device.generation != Generation.GEN4:
            sleep_commands = self._sleep_command(
                COMMAND_LIGHT_SLEEP_TIMER, COMMAND_LIGHT_TIMER, sleep
            )

        commands: dict[str, bool | int] = {}
        if brightness is not None:
            commands[COMMAND_LIGHT_BRIGHTNESS] = brightness
        if on is not None:
            commands[COMMAND_LIGHT_POWER] = on
        if color_temp_kelvin is not None:
            commands[COMMAND_LIGHT_COLOR_TEMP] = color_temp_kelvin
        if identify is not None:
            commands[COMMAND_IDENTIFY] = identify
        commands.update(sleep_commands)

        if self._device.generation == Generation.GEN4:
            wire_state = gen4.build_light_control_state(commands)
            if wire_state:
                response = await self._request(
                    {
                        "action": GEN4_FIXTURE_ACTION_CONTROL,
                        "addr": address,
                        "state": wire_state,
                    },
                    path=GEN4_FIXTURE_API_ENDPOINT,
                )
                changes = gen4.parse_light_control_response(response.get("state", {}))
                self._apply_gen4_light_change(address, changes)
            return

        await self.request(commands=commands)
```

Note `light_fixture()`'s legacy path (`address is None`, `generation != GEN4`) reuses `self.request(commands=commands)` exactly like the old `light()` did — a full `/mf` request that replaces the whole cached shadow, which is correct since legacy responses are always full-shadow.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_aiomodernforms.py -v`
Expected: PASS — all tests, including every pre-existing `light()` test (they never pass `color_temp_kelvin`/`identify`, and for gen1_2/gen3 devices `light()` computes `address = light_fixtures[0].address` which is `None`, so `light_fixture()`'s legacy branch behaves identically to the old `light()` body).

- [ ] **Step 5: Commit**

```bash
git add aiomodernforms/modernforms.py tests/test_aiomodernforms.py
git commit -m "feat: add light_fixture() and rewire light() for Gen4 multi-light support"
```

---

### Task 9: `away()`, `adaptive_learning()` no-op, `has_adaptive_learning()`/`has_sleep_timer()` wrappers

**Files:**
- Modify: `aiomodernforms/modernforms.py`
- Test: `tests/test_aiomodernforms.py`

**Interfaces:**
- Consumes: `_apply_gen4_state_change` (Task 7); `Device.has_adaptive_learning()`/`has_sleep_timer()` (Task 2).
- Produces: `ModernFormsDevice.has_adaptive_learning() -> bool`, `ModernFormsDevice.has_sleep_timer() -> bool` (mirroring `has_breeze_mode()`). `away()`/`adaptive_learning()` signatures are unchanged.

**Context:** `away()` currently always POSTs `{COMMAND_AWAY_MODE: away, COMMAND_QUERY_STATUS: True}` to `/mf`. `adaptive_learning()` always POSTs to `/mf` too. For Gen4: `away()` posts `{"awayModeEnabled": away}` to `/device` instead (same key name, reused constant); `adaptive_learning()` sends nothing at all.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_aiomodernforms.py`:

```python
@pytest.mark.asyncio
async def test_away_gen4_sends_to_device_endpoint(aresponses):
    """Test that away() on Gen4 posts to /device, not /fixture or /mf."""
    _mock_gen4_device(aresponses)

    async def evaluate_request(request):
        data = await request.json()
        assert data == {aiomodernforms.COMMAND_AWAY_MODE: True}
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps({"awayModeEnabled": True}),
        )

    aresponses.add("fan.local", "/device", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        await device.away(True)
        assert device.status.away_mode_enabled is True


@pytest.mark.asyncio
async def test_adaptive_learning_gen4_is_a_silent_noop(aresponses):
    """Test that adaptive_learning() on Gen4 sends nothing and doesn't error."""
    _mock_gen4_device(aresponses)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        await device.adaptive_learning(True)
        # No aresponses mock was registered for a follow-up /device or /mf
        # request — if adaptive_learning() sent anything, this test would
        # fail with a route-not-found error.
        assert device.status.adaptive_learning_enabled is False


@pytest.mark.asyncio
async def test_has_adaptive_learning_and_has_sleep_timer(aresponses):
    """Test the two new capability wrapper methods."""
    _mock_gen4_device(aresponses)

    async with aiomodernforms.ModernFormsDevice("fan.local") as gen4_device:
        await gen4_device.update()
        assert gen4_device.has_adaptive_learning() is False
        assert gen4_device.has_sleep_timer() is False

    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async with aiomodernforms.ModernFormsDevice("fan.local") as legacy_device:
        await legacy_device.update()
        assert legacy_device.has_adaptive_learning() is True
        assert legacy_device.has_sleep_timer() is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_aiomodernforms.py -k "away_gen4 or adaptive_learning_gen4 or has_adaptive_learning_and_has_sleep_timer" -v`
Expected: FAIL — `away()` still posts to `/mf` (route-not-found for the `/device` mock in the test), `has_adaptive_learning()`/`has_sleep_timer()` don't exist on `ModernFormsDevice`.

- [ ] **Step 3: Implement**

In `aiomodernforms/modernforms.py`, add `has_adaptive_learning()`/`has_sleep_timer()` right after `has_identify()` (from Task 8):

```python
    def has_adaptive_learning(self):
        """See if the Fan supports adaptive learning (not available on Gen4)."""
        if self._device is None:
            raise ModernFormsNotInitializedError(
                "The device has not been initialized.  "
                + "Please run update on the device before getting state"
            )
        return self._device.has_adaptive_learning()

    def has_sleep_timer(self):
        """See if the Fan supports sleep timers at all (not available on Gen4)."""
        if self._device is None:
            raise ModernFormsNotInitializedError(
                "The device has not been initialized.  "
                + "Please run update on the device before getting state"
            )
        return self._device.has_sleep_timer()
```

Replace `away()`:

```python
    async def away(self, away: bool):
        """Change the away state of the device."""
        if self._device is None:
            await self.update()

        if self._device.generation == Generation.GEN4:
            response = await self._request(
                {COMMAND_AWAY_MODE: away}, path=GEN4_DEVICE_API_ENDPOINT
            )
            self._apply_gen4_state_change({STATE_AWAY_MODE: response.get(STATE_AWAY_MODE, away)})
            return

        await self.request(
            commands={COMMAND_AWAY_MODE: away, COMMAND_QUERY_STATUS: True}
        )
```

Replace `adaptive_learning()`:

```python
    async def adaptive_learning(self, adaptive_learning: bool):
        """Change the adaptive learning state of the device (no-op on Gen4)."""
        if self._device is None:
            await self.update()

        if self._device.generation == Generation.GEN4:
            return

        await self.request(
            commands={
                COMMAND_ADAPTIVE_LEARNING: adaptive_learning,
                COMMAND_QUERY_STATUS: True,
            }
        )
```

`STATE_AWAY_MODE` needs adding to the `from .const import (...)` block if not already present (check first — it likely already is, since `models.py` imports it too; `modernforms.py` currently doesn't need it directly, so add it).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_aiomodernforms.py -v`
Expected: PASS — all tests, including every pre-existing `away()`/`adaptive_learning()` test (both now do an `if self._device is None: await self.update()` check they didn't do before — confirm this doesn't break `test_away`/`test_adaptive_learning`, which already call `device.update()` before `device.away(...)`/`device.adaptive_learning(...)`, so `self._device` is never `None` at that point and the new check is a no-op for them).

- [ ] **Step 5: Commit**

```bash
git add aiomodernforms/modernforms.py tests/test_aiomodernforms.py
git commit -m "feat: add Gen4 away() path, no-op adaptive_learning(), capability wrappers"
```

---

### Task 10: `reboot()`, `factory_reset()` Gen4 paths; unsupported methods raise on Gen4

**Files:**
- Modify: `aiomodernforms/modernforms.py`
- Test: `tests/test_aiomodernforms.py`

**Interfaces:**
- Consumes: `ModernFormsNotSupportedError` (Task 1).
- Produces: no new public methods; `reboot()`/`factory_reset()` behavior branches on generation; `decommission()`/`enable_pairing_mode()`/`clear_paired_devices()`/`set_schedule()` raise `ModernFormsNotSupportedError` when `generation == Generation.GEN4`.

**Context:** `reboot()` and `factory_reset()` already swallow `ModernFormsConnectionTimeoutError` (the device drops the connection on a successful reset/reboot) — this behavior is preserved for Gen4, just targeting `/device` with different command keys (`{"reboot": True}` — same key as legacy's `COMMAND_REBOOT`; `{"hardFactoryReset": True}` for factory reset, the immediate/no-response variant per the PDF).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_aiomodernforms.py`:

```python
@pytest.mark.asyncio
async def test_reboot_gen4(aresponses):
    """Test reboot() on Gen4 posts {"reboot": True} to /device."""
    _mock_gen4_device(aresponses)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        with patch(
            "aiomodernforms.ModernFormsDevice._request",
            side_effect=ModernFormsConnectionTimeoutError,
        ):
            await device.reboot()


@pytest.mark.asyncio
async def test_factory_reset_gen4_sends_hard_factory_reset(aresponses):
    """Test that factory_reset() on Gen4 sends hardFactoryReset, not factoryReset."""
    _mock_gen4_device(aresponses)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        with patch(
            "aiomodernforms.ModernFormsDevice._request",
            side_effect=ModernFormsConnectionTimeoutError,
        ) as mock_request:
            await device.factory_reset()
            mock_request.assert_called_once_with(
                {"hardFactoryReset": True}, path="device"
            )


@pytest.mark.asyncio
async def test_gen4_unsupported_methods_raise(aresponses):
    """Test that decommission/pairing/schedule raise on Gen4."""
    _mock_gen4_device(aresponses)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        with pytest.raises(ModernFormsNotSupportedError):
            await device.decommission()
        with pytest.raises(ModernFormsNotSupportedError):
            await device.enable_pairing_mode()
        with pytest.raises(ModernFormsNotSupportedError):
            await device.clear_paired_devices()
        with pytest.raises(ModernFormsNotSupportedError):
            await device.set_schedule("AAAA")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_aiomodernforms.py -k "reboot_gen4 or factory_reset_gen4 or gen4_unsupported" -v`
Expected: FAIL — `reboot()`/`factory_reset()` still post to `/mf` via `self.request()`, and the four unsupported methods don't raise on Gen4 at all yet.

- [ ] **Step 3: Implement**

In `aiomodernforms/modernforms.py`, add `ModernFormsNotSupportedError` to the `from .exceptions import (...)` block and `GEN4_DEVICE_HARD_FACTORY_RESET` to the `from .const import (...)` block.

Replace `reboot()`:

```python
    async def reboot(self):
        """Send a reboot to the Fan."""
        if self._device is None:
            await self.update()

        try:
            if self._device.generation == Generation.GEN4:
                await self._request({COMMAND_REBOOT: True}, path=GEN4_DEVICE_API_ENDPOINT)
            else:
                await self.request(commands={COMMAND_REBOOT: True})
        except ModernFormsConnectionTimeoutError:
            # a successful reboot drops the connection
            pass
```

Replace `factory_reset()`:

```python
    async def factory_reset(self):
        """Reset the fan to factory defaults.

        Clears Wi-Fi credentials, decommissions the fan from the cloud,
        clears RF pairings, and returns the fan to AP mode. On Gen4, sends
        the immediate/no-response hardFactoryReset variant, matching the
        same connection-drop behavior as Gen 1/2/3.
        """
        if self._device is None:
            await self.update()

        try:
            if self._device.generation == Generation.GEN4:
                await self._request(
                    {GEN4_DEVICE_HARD_FACTORY_RESET: True}, path=GEN4_DEVICE_API_ENDPOINT
                )
            else:
                await self.request(commands={COMMAND_FACTORY_RESET: True})
        except ModernFormsConnectionTimeoutError:
            # a successful factory reset drops the connection
            pass
```

Add a generation guard at the top of `decommission()`, `enable_pairing_mode()`, `clear_paired_devices()`, and `set_schedule()` — for example, `decommission()` becomes:

```python
    async def decommission(self):
        """Decommission the fan from the cloud and return it to AP mode."""
        if self._device is None:
            await self.update()
        if self._device.generation == Generation.GEN4:
            raise ModernFormsNotSupportedError(
                "decommission() is not supported on Gen4 fans"
            )
        try:
            await self.request(commands={COMMAND_DECOMMISSION: True})
        except ModernFormsConnectionTimeoutError:
            # a successful decommission drops the connection
            pass
```

Apply the same pattern (add `if self._device is None: await self.update()` then the `if self._device.generation == Generation.GEN4: raise ModernFormsNotSupportedError(...)` guard, with a message naming the specific method) to `enable_pairing_mode()`, `clear_paired_devices()`, and `set_schedule()`, before each method's existing body.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_aiomodernforms.py -v`
Expected: PASS — all tests, including every pre-existing `reboot()`/`factory_reset()`/`decommission()`/`enable_pairing_mode()`/`clear_paired_devices()`/`set_schedule()` test (all of them already call `device.update()` before the method under test, so the new `if self._device is None:` checks are no-ops, and `self._device.generation` is `Generation.GEN1_2`/`GEN3` for every existing fixture, so the new Gen4 branches are never taken).

- [ ] **Step 5: Commit**

```bash
git add aiomodernforms/modernforms.py tests/test_aiomodernforms.py
git commit -m "feat: add Gen4 reboot()/factory_reset(); raise on unsupported Gen4 methods"
```

---

### Task 11: `config()` — Gen4 path

**Files:**
- Modify: `aiomodernforms/modernforms.py`
- Test: `tests/test_aiomodernforms.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `config()`'s public signature/return type (`ConfigInfo`) unchanged.

**Context:** `config()` currently always fetches `/config-read` and maps it via `ConfigInfo.from_dict`. Gen4 has no `/config-read` endpoint — the same information (mapped to what fields are available) comes from `/device`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_aiomodernforms.py`:

```python
@pytest.mark.asyncio
async def test_config_gen4(aresponses):
    """Test config() against a Gen4 device — maps /device fields into ConfigInfo."""
    _mock_gen4_device(aresponses)
    aresponses.add("fan.local", "/device", "POST", response=gen4_device_response)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        config = await device.config()
        assert config.device_name == "Fan"
        assert config.firmware_version == "01.00.0082"
        assert config.rf_version == "01.00.0012"
        assert config.certificate_id == "abc123certid"
        assert config.wifi_strength == "-42"
        assert config.hardware_revision == ""
        assert config.protocol == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_aiomodernforms.py::test_config_gen4 -v`
Expected: FAIL — `config()` unconditionally requests `/config-read`, which has no mock registered (`aresponses` route-not-found), and even if it did, `ConfigInfo.from_dict` wouldn't recognize any of `gen4_device_response`'s keys.

- [ ] **Step 3: Implement**

In `aiomodernforms/modernforms.py`, replace `config()`:

```python
    async def config(self) -> ConfigInfo:
        """Retrieve config-read data.

        Includes hardware revision, RF library version, certificate ID,
        and current Wi-Fi signal strength.
        """
        if self._device is None:
            await self.update()

        if self._device.generation == Generation.GEN4:
            device_data = await self._request(
                {GEN4_DEVICE_QUERY: True}, path=GEN4_DEVICE_API_ENDPOINT
            )
            nwk_state = device_data.get(GEN4_DEVICE_NWK_STATE) or {}
            return ConfigInfo(
                device_name=device_data.get(GEN4_DEVICE_NAME, ""),
                protocol="",
                hardware_revision="",
                firmware_version=device_data.get(GEN4_DEVICE_IOTM_VER, ""),
                rf_version=device_data.get(GEN4_DEVICE_SCM_VER, ""),
                certificate_id=nwk_state.get(GEN4_NWK_CERTIFICATE_ID, ""),
                wifi_strength=str(nwk_state.get(GEN4_NWK_RSSI, "")),
            )

        config_data = await self._request(commands={}, path=CONFIG_READ_API_ENDPOINT)
        return ConfigInfo.from_dict(config_data)
```

Add `GEN4_DEVICE_NWK_STATE`, `GEN4_NWK_CERTIFICATE_ID`, `GEN4_NWK_RSSI` to the `from .const import (...)` block.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_aiomodernforms.py -v`
Expected: PASS — all tests, including every pre-existing `config()` test (gen1_2/gen3 devices take the unchanged final branch).

- [ ] **Step 5: Commit**

```bash
git add aiomodernforms/modernforms.py tests/test_aiomodernforms.py
git commit -m "feat: add Gen4 path to config()"
```

---

### Task 12: `diagnose.py` — Gen4-aware raw dump and active tests

**Files:**
- Modify: `diagnose.py`

**Interfaces:**
- Consumes: `ModernFormsDevice._is_gen4`/`_probe_gen4()` behavior (Task 6) — `diagnose.py` already reaches into `ModernFormsDevice` internals (`fan._request`, `fan._device`), matching its existing style.
- Produces: no new public interface — this is a standalone script, not library code other tasks depend on.

**Context:** `gather_report()` currently unconditionally calls `/mf` + `/config-read` directly (bypassing `update()`, so it can capture the truly raw, unparsed response for the "unrecognized keys" diagnostic). It needs a Gen4 branch that instead dumps raw `/device` + `/fixture` responses.

- [ ] **Step 1: Add Gen4 known-key sets and redaction handling**

In `diagnose.py`, add after `CONFIG_KNOWN_KEYS`:

```python
GEN4_DEVICE_KNOWN_KEYS = {
    "systemType",
    "deviceName",
    "owner",
    "iotmVer",
    "scmVer",
    "awayModeEnabled",
    "nwkState",
}

GEN4_FIXTURE_KNOWN_KEYS = {
    "addr",
    "name",
    "type",
    "state",
    "detail",
}
```

Add `"deviceName"` and `"owner"` to the existing `SENSITIVE_KEYS` set (Gen4's `/device` response carries the same kind of identifying info the legacy redaction already covers under different key names):

```python
SENSITIVE_KEYS = {
    const.INFO_OWNER,  # account email address
    const.INFO_FEDERATED_IDENTITY,  # AWS Cognito identity
    const.INFO_MAC,
    const.INFO_DEVICE_NAME,  # user-assigned name, e.g. "Living Room"
    const.CONFIG_CERTIFICATE_ID,
    const.CONFIG_NAME_LEGACY,  # config-read device name, Gen 1/2
    const.CONFIG_NAME,  # config-read device name, Gen 3
    "deviceName",  # Gen4 /device device name
    "owner",  # Gen4 /device account email address
}
```

- [ ] **Step 2: Branch `gather_report()` on generation**

Replace the body of `gather_report()`'s `async with` block (currently the block starting at `try: static_raw = await fan._request(...)` through the `if active:` line) with a generation probe up front, then two separate paths. Add this import at the top of `diagnose.py`: `from aiomodernforms.gen4 import is_gen4_system_type`.

```python
    async with aiomodernforms.ModernFormsDevice(
        host, port=port, tls=tls, username=username, password=password
    ) as fan:
        try:
            device_raw = await fan._request(  # pylint: disable=protected-access
                {"query": True}, path="device"
            )
        except aiomodernforms.ModernFormsError:
            device_raw = None

        if device_raw is not None and is_gen4_system_type(device_raw.get("systemType", "")):
            out.extend(await _gather_gen4_report(fan, device_raw))
        else:
            out.extend(await _gather_legacy_report(fan))

        if active:
            out.extend(await run_active_tests(fan))

    return "\n".join(out)
```

Extract the existing legacy body (everything that was between `try: static_raw = ...` and the `if active:` line) into a new function `_gather_legacy_report(fan)` returning `list[str]`, unchanged in content — just moved and made to `return out` instead of appending to the outer `out`.

Add the new Gen4 report function:

```python
async def _gather_gen4_report(fan: aiomodernforms.ModernFormsDevice, device_raw: dict) -> list[str]:
    """Build the Gen4-specific portion of the diagnostic report."""
    out = [_section("Raw /device data")]
    out.append(_json_block(redact(device_raw)))
    extra = list(unknown_keys(device_raw, GEN4_DEVICE_KNOWN_KEYS))
    if extra:
        out.append(f"\n**Unrecognized keys:** `{extra}`")

    out.append(_section("Raw /fixture read-all data"))
    try:
        fixture_raw = await fan._request(  # pylint: disable=protected-access
            {"action": 3}, path="fixture"
        )
        out.append(_json_block(fixture_raw))
        fixtures = fixture_raw.get("fixture", [])
        out.append(
            f"\n**Discovered {len(fixtures)} fixture(s):** "
            + ", ".join(f"type {f.get('type')} @ {f.get('addr')}" for f in fixtures)
        )
        for fixture in fixtures:
            extra = list(unknown_keys(fixture, GEN4_FIXTURE_KNOWN_KEYS))
            if extra:
                out.append(
                    f"\n**Unrecognized keys on fixture {fixture.get('addr')}:** `{extra}`"
                )
    except aiomodernforms.ModernFormsError as err:
        out.append(f"`/fixture` read-all request failed: `{err}`")

    return out
```

- [ ] **Step 3: Gate `run_active_tests()`'s unsupported checks**

In `run_active_tests()`, after the existing `relative_timers = fan.has_relative_timers()` line, add:

```python
    supports_adaptive_learning = fan.has_adaptive_learning()
    supports_sleep_timer = fan.has_sleep_timer()
```

Wrap the existing sleep-timer `check(...)` calls (both the `light(sleep=90)`/`light(sleep=0)` pair and the `fan(sleep=90)`/`fan(sleep=0)` pair) in `if supports_sleep_timer:` / `else: out.append("- ⏭️ Sleep timer: not supported on this device (skipped)")`, matching the existing `if supports_wind: ... else: out.append("- ⏭️ Breeze mode: ...")` pattern already in the function.

The existing script explicitly documents that `--active` never calls `adaptive_learning()` at all (see the module docstring and `--active` help text: "adaptive_learning are always skipped") — so no gating is needed there; it was already out of scope for `--active` before this feature existed, and stays that way.

Update the module docstring's list of Gen4-relevant capability flags and the `--active` help text is unaffected (still correct as written).

- [ ] **Step 4: Manual verification**

There's no automated test suite for `diagnose.py` (it's a standalone script, consistent with its current state — it has no existing tests either). Verify manually:

Run: `python -c "import diagnose"` 
Expected: No `ImportError`/`SyntaxError` — confirms the module at least parses and imports cleanly.

Run: `python -m py_compile diagnose.py`
Expected: Exits 0.

- [ ] **Step 5: Commit**

```bash
git add diagnose.py
git commit -m "feat: make diagnose.py generation-aware for Gen4 devices"
```

---

## Deferred: `mock_fan` Gen4 profile

The design spec (`docs/superpowers/specs/2026-07-29-gen4-fan-support-design.md`, §5) calls for extending `mock_fan` — a standalone dev-tool HTTP service that speaks the fan wire protocol back at a real `aiomodernforms.ModernFormsDevice` client, useful for exercising Home Assistant against a fake fan — with a `GEN4` profile alongside the planned `GEN1_2`/`GEN3` ones. That base service (`docs/superpowers/specs/2026-07-28-mock-fan-service-design.md` / `docs/superpowers/plans/2026-07-28-mock-fan-service.md`) doesn't exist in this repo yet — its code previously lived in a git worktree that's since become inaccessible, and is expected to be reintroduced separately. This section documents what the Gen4 extension should look like so it's easy to slot in once the base service exists — **do not implement this now.**

When the base `mock_fan` service exists, add a `GEN4` profile:

- **`POST /device`** — returns `{"systemType": "fan_g4", "deviceName": ..., "owner": ..., "iotmVer": ..., "scmVer": ..., "awayModeEnabled": <mutable>, "nwkState": {"certificateID": ..., "rssi": ...}}`. Honors `{"query": true}` (read), `{"awayModeEnabled": <bool>}` (write, echo the new device dict back), `{"reboot": true}` and `{"hardFactoryReset": true}` (both use the same hold-the-connection-open-past-the-client-timeout trick already planned for gen1_2/gen3's reboot/factory_reset, so `ModernFormsConnectionTimeoutError` gets raised and swallowed exactly like today).
- **`POST /fixture`** — one Fan fixture (`type: 13`) plus however many light fixtures (`type: 1`, tunable white, with a `detail.minColorTemp`/`maxColorTemp` pair) the mock is configured with via a new `--lights N` CLI flag (default 1). Addresses are just fixed test constants the mock assigns itself at startup — **not** computed from a MAC, matching this plan's Task 6/7/8 behavior exactly. `{"action": 3}` with no `addr` returns every fixture (the `fixture` array shape used throughout this plan's tests); `{"action": 3, "addr": N}` returns one; `{"action": 4, "addr": N, "state": {...}}` validates and applies (same validity rules as `apply_commands()` already does for gen1_2/gen3 — `fanSpeed` 1-6, `level` 1-10000, etc.) and echoes back only the changed fields under `"state"`, matching the real device's per-fixture (not full-shadow) response shape.
- **CLI**: `--generation gen4` alongside the existing `--generation {gen1_2,gen3}`; `--lights N` (only meaningful with `--generation gen4`).
- **Integration tests**: the same round-trip suite already planned for gen1_2/gen3, driven through the real `ModernFormsDevice` from this plan — `update()`, `fan()`, `light()`, `light_fixture()` (exercising a light beyond index 0), `away()`, `reboot()`, `factory_reset()`, plus confirming `has_adaptive_learning()`/`has_sleep_timer()` return `False` and `decommission()`/`enable_pairing_mode()`/`clear_paired_devices()`/`set_schedule()` raise `ModernFormsNotSupportedError`.

## Self-Review

**Spec coverage:**
- §1 (explicit `Generation`) → Task 2.
- §2 (detection) → Task 6.
- §3 (canonical translation, `Light`, `light_fixtures`, capability metadata) → Tasks 3, 4.
- §4 (control methods: `fan()`/`light()`/`light_fixture()`/`away()`/`adaptive_learning()`/`reboot()`/`factory_reset()`/unsupported-raises/`config()`) → Tasks 5, 7, 8, 9, 10, 11.
- §5 (`mock_fan` Gen4 profile) → explicitly deferred and documented above, per your instruction that the base service isn't available in this repo right now.
- §6 (`diagnose.py`) → Task 12.
- §7 (testing) → covered inline in every task (unit tests for `gen4.py`, `aresponses`-driven integration tests for `ModernFormsDevice`); `mock_fan`'s integration coverage is deferred along with `mock_fan` itself.
- Out-of-scope items (RGBW, non-fan WAC IoT types, `Configure`-action tuning fields, mDNS) → no tasks reference them, consistent with staying out of scope.

**Placeholder scan:** No "TBD"/"TODO" markers; every step has real code. The one exception is the `mock_fan` section, which is deliberately a deferred reference (not a task with steps) per your explicit request — it's clearly labeled as such and excluded from the task list and from `Deferred:` prose rather than presented as executable work.

**Type consistency:** `Generation`, `Light`, `State.to_dict()`, `gen4.build_state_data`/`build_info_data`/`build_fan_control_state`/`build_light_control_state`/`parse_fan_control_response`/`parse_light_control_response`, `ModernFormsDevice._update_legacy`/`_probe_gen4`/`_update_gen4`/`_apply_gen4_state_change`/`_apply_gen4_light_change`/`_gen4_fan_addr`/`_is_gen4`, and `light_fixture()`'s signature are each defined exactly once (Tasks 2-4, 6-8) and referenced identically by name in every later task that consumes them.

**Design refinement made during planning:** the spec describes detection as probing `/device` first. While drafting Task 6's tests, that order turned out to require adding a `/device` 404 mock to every one of the ~40 pre-existing tests in `tests/test_aiomodernforms.py` (since `aresponses` has no route-priority concept — routes match in strict registration order, confirmed by reading `aresponses`' source directly rather than guessing). Task 6 instead tries `/mf` first and only probes `/device` on failure — behaviorally equivalent (same caching, same end state, Gen4 still reliably detected via the same `/device` + `systemType` check), backward compatible with zero changes to any pre-existing test, and one fewer request for the common legacy case. Flagging this here since it's a deviation from the spec's literal wording, even though it preserves the spec's intent.
