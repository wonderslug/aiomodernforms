# Mock Fan Gen4 Profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Gen4 profile to the `mock_fan` service (a standalone dev-tool HTTP server that speaks the Modern Forms wire protocol, used for developing/testing clients like a Home Assistant integration without real hardware) — completing the "Deferred: mock_fan Gen4 profile" section of `docs/superpowers/plans/2026-07-29-gen4-fan-support.md`, which was written before `mock_fan`'s Gen1_2/Gen3 implementation existed. It exists now (merged via #286), so this plan builds directly against its real code rather than a speculative design.

**Architecture:** A new `mock_fan/gen4.py` module holds Gen4-specific static data and mutable fixture state (`Fixture`, `Gen4FanState`), kept separate from the existing `generations.py`/`state.py` because Gen4 is a different wire protocol (`/device` + `/fixture`, N addressable light fixtures), not just different static values on the same `/mf` + `/config-read` shape. `mock_fan/server.py` gains `create_gen4_app()` and two new handlers, reusing the existing disconnect-simulation mechanism (extracted into two small shared helpers rather than duplicated). `mock_fan/__main__.py` gains a `gen4` `--generation` choice and a `--lights N` flag.

**Tech Stack:** Python 3.11, aiohttp, pytest + pytest-asyncio, `aiohttp.test_utils` (`TestClient`/`TestServer`) for integration tests driven through the real `aiomodernforms.ModernFormsDevice` client.

## Global Constraints

- Python `>=3.11`. Use `from __future__ import annotations` and modern union syntax (`int | None`, not `Optional[int]`), matching every existing file in `mock_fan/` and `aiomodernforms/`.
- Line length 88 chars (black default; `flake8` `max-line-length=88`).
- mypy runs with `disallow_untyped_calls=True`, `disallow_untyped_defs=True`, `no_implicit_optional=True`, `strict_optional=True` (config file is `mypi.ini`, **not** `mypy.ini` — a pre-existing repo typo; bare `mypy` silently skips these settings, always pass `--config-file mypi.ini` explicitly).
- `flake8-docstrings` is enabled (`D202`, `W503` ignored) — every new public function/class/method needs a one-line docstring.
- Pre-commit hooks (black, isort, autopep8, pylint, mypy, flake8, pyupgrade `--py36-plus`) run automatically on `git commit`. If a hook reformats files, the commit aborts on the first attempt — run `git add -u` and re-run the same `git commit` command.
- Tests use `@pytest.mark.asyncio`. `mock_fan`'s integration tests (`tests/mock_fan/test_server.py`) don't use `aresponses` — they run the mock server in-process via `aiohttp.test_utils.TestClient(TestServer(app))` and drive it with the real `aiomodernforms.ModernFormsDevice`. Follow this existing pattern exactly for new Gen4 integration tests.
- Run the full suite with `pytest tests/ -v` before every commit that touches source files.
- **No fixture address is ever computed** (e.g. from a MAC address) — this mock assigns itself fixed, arbitrary addresses as plain constants, matching the design principle established in the main Gen4 plan (the device is always the sole source of truth for its own addresses; a mock is no different from a real device in this respect).
- `mock_fan/` and `tests/mock_fan/` are excluded from the published package (`setup.py`'s `find_packages(include=["aiomodernforms"])`) — nothing in this plan touches `setup.py`.

---

### Task 1: `mock_fan/gen4.py` — Gen4 fixture data and mutable state

**Files:**
- Create: `mock_fan/gen4.py`
- Create: `tests/mock_fan/test_gen4.py`

**Interfaces:**
- Consumes: nothing new from other tasks (this is the first task).
- Produces: `mock_fan.gen4.Fixture` (dataclass: `address: int`, `fixture_type: int`, `name: str`, `state: dict[str, object]`, `detail: dict[str, object]`, `validators: dict[str, Callable[[object], bool]]`, with `apply_commands(commands) -> dict[str, object]` and `as_wire_dict() -> dict[str, object]` methods); `mock_fan.gen4.Gen4FanState` (constructor `Gen4FanState(lights: int = 1)`, with `.fan: Fixture`, `.lights: list[Fixture]`, `.away_mode_enabled: bool`, `.all_fixtures() -> list[Fixture]`, `.find(address: int) -> Fixture | None`, `.reset() -> None`); `mock_fan.gen4.device_data(away_mode_enabled: bool) -> dict[str, object]`; constants `mock_fan.gen4.DEVICE_NAME`, `FAN_ADDR`, `LIGHT_FIXTURE_TYPE`. Consumed by Task 2 (`server.py`'s Gen4 handlers).

**Context:** This is pure, no-I/O logic — the same style as the existing `mock_fan/state.py`'s `FanState`/`apply_commands`, just modeling Gen4's per-fixture addressing instead of one flat shadow dict. `aiomodernforms/const.py` already has every `GEN4_*` wire-field constant this needs (from the main Gen4 plan) — reuse them, don't redefine.

- [ ] **Step 1: Write the failing tests**

Create `tests/mock_fan/test_gen4.py`:

```python
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
    assert changed == {}
    assert state.fan.state[COMMAND_FAN_SPEED] == 6


def test_gen4_fixture_apply_commands_only_returns_changed_keys():
    """apply_commands() returns only the keys it actually applied, not the full state."""
    state = Gen4FanState(lights=0)
    changed = state.fan.apply_commands({GEN4_FIELD_STATUS: True, GEN4_FIELD_FINDME: True})
    assert changed == {GEN4_FIELD_STATUS: True, GEN4_FIELD_FINDME: True}
    assert COMMAND_FAN_SPEED not in changed


def test_gen4_fixture_light_validates_level_and_color_temp():
    """A light fixture validates level (1-10000) and mixColorTemp."""
    state = Gen4FanState(lights=1)
    light = state.lights[0]
    changed = light.apply_commands({GEN4_FIELD_LEVEL: 7500, GEN4_FIELD_MIX_COLOR_TEMP: 4000})
    assert changed == {GEN4_FIELD_LEVEL: 7500, GEN4_FIELD_MIX_COLOR_TEMP: 4000}

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/mock_fan/test_gen4.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mock_fan.gen4'`.

- [ ] **Step 3: Create `mock_fan/gen4.py`**

```python
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
    GEN4_DEVICE_SYSTEM_TYPE,
    GEN4_FIELD_ADDR,
    GEN4_FIELD_DETAIL,
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
        """Initialize the fan fixture and `lights` light fixtures at startup defaults."""
        self.away_mode_enabled = False
        self.fan = Fixture(
            address=FAN_ADDR,
            fixture_type=GEN4_FIXTURE_TYPE_FAN,
            name="Fan",
            state=_initial_fan_state(),
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
        STATE_AWAY_MODE: away_mode_enabled,
        GEN4_DEVICE_NWK_STATE: {
            GEN4_NWK_CERTIFICATE_ID: _MOCK_CERTIFICATE_ID,
            GEN4_NWK_RSSI: "-42",
        },
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/mock_fan/test_gen4.py -v`
Expected: PASS — all tests.

- [ ] **Step 5: Commit**

```bash
git add mock_fan/gen4.py tests/mock_fan/test_gen4.py
git commit -m "feat: add mock_fan Gen4 fixture data and state"
```

---

### Task 2: `mock_fan/server.py` — Gen4 HTTP handlers

**Files:**
- Modify: `mock_fan/server.py`
- Modify: `tests/mock_fan/test_server.py`

**Interfaces:**
- Consumes: `mock_fan.gen4.Gen4FanState`, `mock_fan.gen4.device_data` (Task 1).
- Produces: `mock_fan.server.create_gen4_app(lights: int = 1, resume_delay_secs: float = 5.0) -> web.Application`. Consumed by Task 3 (`__main__.py` CLI dispatch).

**Context:** The existing `_handle_mf` inlines its own "hold the connection open to simulate a disconnect" logic (used for `reboot`/`factoryReset`/`decommission`). The new Gen4 `/device` handler needs the identical behavior for `reboot`/`hardFactoryReset`. Rather than duplicate the 300-second-sleep pattern, extract it into two small shared helpers first, refactor `_handle_mf` to use them (a behavior-preserving refactor — the existing legacy tests, especially `test_reboot_disconnects_then_resumes`, `test_activity_logging_disruptive_command_and_hold`, and `test_factory_reset_resets_state`, must all still pass unmodified and prove nothing changed), then add the Gen4 handlers on top of the same shared helpers.

- [ ] **Step 1: Write the failing tests**

Add to `tests/mock_fan/test_server.py`, after the existing imports add:

```python
from mock_fan.server import create_gen4_app
```

Then add these tests (anywhere after the existing tests):

```python
@pytest.mark.asyncio
async def test_gen4_update_populates_info_and_state():
    """update() against a mock Gen4 fan populates State/Info/generation correctly."""
    app = create_gen4_app(lights=1)
    async with TestClient(TestServer(app)) as client:
        async with aiomodernforms.ModernFormsDevice(
            client.host, port=client.port, session=client.session
        ) as device:
            await device.update()
            assert device.status.fan_on is False
            assert device.status.fan_speed == 3
            assert len(device.status.light_fixtures) == 1
            assert device.has_adaptive_learning() is False
            assert device.has_sleep_timer() is False
            assert device.has_identify() is True


@pytest.mark.asyncio
async def test_gen4_zero_lights():
    """A Gen4 mock fan with lights=0 reports no light fixtures."""
    app = create_gen4_app(lights=0)
    async with TestClient(TestServer(app)) as client:
        async with aiomodernforms.ModernFormsDevice(
            client.host, port=client.port, session=client.session
        ) as device:
            await device.update()
            assert device.status.light_fixtures == []


@pytest.mark.asyncio
async def test_gen4_multiple_lights():
    """A Gen4 mock fan with lights=3 exposes three independently addressable lights."""
    app = create_gen4_app(lights=3)
    async with TestClient(TestServer(app)) as client:
        async with aiomodernforms.ModernFormsDevice(
            client.host, port=client.port, session=client.session
        ) as device:
            await device.update()
            assert len(device.status.light_fixtures) == 3

            second_light_addr = device.status.light_fixtures[1].address
            await device.light_fixture(second_light_addr, on=True, brightness=80)
            assert device.status.light_fixtures[1].on is True
            assert device.status.light_fixtures[1].brightness == 80
            # The other lights are untouched.
            assert device.status.light_fixtures[0].on is False
            assert device.status.light_fixtures[2].on is False


@pytest.mark.asyncio
async def test_gen4_fan_and_light_round_trip():
    """fan()/light() commands round-trip through the mock Gen4 fan."""
    app = create_gen4_app(lights=1)
    async with TestClient(TestServer(app)) as client:
        async with aiomodernforms.ModernFormsDevice(
            client.host, port=client.port, session=client.session
        ) as device:
            await device.update()
            await device.fan(on=True, speed=5, direction=FAN_DIRECTION_REVERSE)
            assert device.status.fan_on is True
            assert device.status.fan_speed == 5
            assert device.status.fan_direction == FAN_DIRECTION_REVERSE

            await device.light(on=True, brightness=75)
            assert device.status.light_on is True
            assert device.status.light_brightness == 75


@pytest.mark.asyncio
async def test_gen4_away_round_trip():
    """away() round-trips through the mock Gen4 fan's /device endpoint."""
    app = create_gen4_app(lights=0)
    async with TestClient(TestServer(app)) as client:
        async with aiomodernforms.ModernFormsDevice(
            client.host, port=client.port, session=client.session
        ) as device:
            await device.update()
            await device.away(True)
            assert device.status.away_mode_enabled is True


@pytest.mark.asyncio
async def test_gen4_unsupported_methods_raise():
    """decommission/pairing/schedule raise ModernFormsNotSupportedError on mock Gen4."""
    app = create_gen4_app(lights=0)
    async with TestClient(TestServer(app)) as client:
        async with aiomodernforms.ModernFormsDevice(
            client.host, port=client.port, session=client.session
        ) as device:
            await device.update()
            with pytest.raises(aiomodernforms.ModernFormsNotSupportedError):
                await device.decommission()


@pytest.mark.asyncio
async def test_gen4_reboot_disconnects_then_resumes():
    """reboot() against a mock Gen4 fan times out (swallowed), then resumes."""
    app = create_gen4_app(lights=0, resume_delay_secs=0.05)
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
async def test_gen4_factory_reset_resets_state():
    """factory_reset() resets the mock Gen4 fan's fixtures to startup defaults."""
    app = create_gen4_app(lights=0, resume_delay_secs=0.05)
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

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/mock_fan/test_server.py -k gen4 -v`
Expected: FAIL with `ImportError: cannot import name 'create_gen4_app'`.

- [ ] **Step 3: Extract shared disconnect helpers, refactor `_handle_mf` to use them**

In `mock_fan/server.py`, add these two module-level functions right after the `DISCONNECT_HOLD_SECS`/`DEVICE_NAME` constants:

```python
def _unresponsive_after(loop: asyncio.AbstractEventLoop, resume_delay_secs: float) -> float:
    """Return the loop-time deadline after which a fan resumes responding."""
    return loop.time() + resume_delay_secs


async def _hold_connection() -> None:
    """Hold a connection open long enough to look disconnected to any client."""
    await asyncio.sleep(DISCONNECT_HOLD_SECS)
```

In `_handle_mf`, replace:

```python
    if loop.time() < fan.unresponsive_until:
        _LOGGER.info(
            "request received while unresponsive (simulated disconnect) —"
            " holding connection"
        )
        await asyncio.sleep(DISCONNECT_HOLD_SECS)
```

with:

```python
    if loop.time() < fan.unresponsive_until:
        _LOGGER.info(
            "request received while unresponsive (simulated disconnect) —"
            " holding connection"
        )
        await _hold_connection()
```

And replace:

```python
        fan.unresponsive_until = loop.time() + fan.resume_delay_secs
        _LOGGER.info(
            "%s received — disconnecting for %.1fs", trigger, fan.resume_delay_secs
        )
        await asyncio.sleep(DISCONNECT_HOLD_SECS)
```

with:

```python
        fan.unresponsive_until = _unresponsive_after(loop, fan.resume_delay_secs)
        _LOGGER.info(
            "%s received — disconnecting for %.1fs", trigger, fan.resume_delay_secs
        )
        await _hold_connection()
```

Run `pytest tests/mock_fan/ -v` now (before adding any Gen4 code) to confirm this refactor alone is behavior-preserving — every existing test must still pass unmodified.

- [ ] **Step 4: Add `MockGen4Fan`, `create_gen4_app`, and the two Gen4 handlers**

Add the following imports to `mock_fan/server.py`'s `from aiomodernforms.const import (...)` block: `COMMAND_REBOOT`, `GEN4_DEVICE_HARD_FACTORY_RESET`, `GEN4_FIELD_ACTION`, `GEN4_FIELD_ADDR`, `GEN4_FIELD_FIXTURE_LIST`, `GEN4_FIELD_STATE`, `GEN4_FIXTURE_ACTION_CONTROL`, `STATE_AWAY_MODE` (alphabetized in). Add `from .gen4 import Gen4FanState, device_data`.

Do NOT import `GEN4_FIXTURE_ACTION_READ` — nothing in `_handle_fixture` needs to check for it explicitly (any action value other than `GEN4_FIXTURE_ACTION_CONTROL` falls through to the read branches below), and an unused import would fail `flake8` (F401).

Add after the existing `MockFan` class:

```python
class MockGen4Fan:
    """Holds a mock Gen4 fan's fixture state and its simulated-disconnect window."""

    def __init__(self, lights: int, resume_delay_secs: float) -> None:
        """Initialize Gen4 fixture state for the given light count."""
        self.state = Gen4FanState(lights=lights)
        self.resume_delay_secs = resume_delay_secs
        self.unresponsive_until: float = 0.0
```

Add after `_handle_config_read`:

```python
async def _handle_device(request: web.Request) -> web.Response:
    """Handle POST /device: query/awayModeEnabled, reboot, hardFactoryReset."""
    fan: MockGen4Fan = request.app["gen4_fan"]
    loop = asyncio.get_running_loop()

    if loop.time() < fan.unresponsive_until:
        _LOGGER.info(
            "request received while unresponsive (simulated disconnect) —"
            " holding connection"
        )
        await _hold_connection()

    body = await request.json()

    if body.get(GEN4_DEVICE_HARD_FACTORY_RESET) or body.get(COMMAND_REBOOT):
        trigger = "hardFactoryReset" if body.get(GEN4_DEVICE_HARD_FACTORY_RESET) else "reboot"
        if trigger == "hardFactoryReset":
            fan.state.reset()
        fan.unresponsive_until = _unresponsive_after(loop, fan.resume_delay_secs)
        _LOGGER.info(
            "%s received — disconnecting for %.1fs", trigger, fan.resume_delay_secs
        )
        await _hold_connection()

    if isinstance(body.get(STATE_AWAY_MODE), bool):
        fan.state.away_mode_enabled = body[STATE_AWAY_MODE]

    return web.json_response(device_data(fan.state.away_mode_enabled))


async def _handle_fixture(request: web.Request) -> web.Response:
    """Handle POST /fixture: read-all, read-one, and control."""
    fan: MockGen4Fan = request.app["gen4_fan"]
    loop = asyncio.get_running_loop()

    if loop.time() < fan.unresponsive_until:
        _LOGGER.info(
            "request received while unresponsive (simulated disconnect) —"
            " holding connection"
        )
        await _hold_connection()

    body = await request.json()
    action = body.get(GEN4_FIELD_ACTION)
    addr = body.get(GEN4_FIELD_ADDR)

    if action == GEN4_FIXTURE_ACTION_CONTROL and addr is not None:
        fixture = fan.state.find(addr)
        if fixture is None:
            return web.json_response(
                {GEN4_FIELD_ACTION: action, "result": "-2"}, status=400
            )
        changed = fixture.apply_commands(body.get(GEN4_FIELD_STATE, {}))
        _LOGGER.info("fixture %s applied changes: %s", addr, changed)
        return web.json_response(
            {GEN4_FIELD_ACTION: action, "result": "0", GEN4_FIELD_STATE: changed}
        )

    if addr is not None:
        fixture = fan.state.find(addr)
        if fixture is None:
            return web.json_response(
                {GEN4_FIELD_ACTION: action, "result": "-2"}, status=400
            )
        _LOGGER.info("fixture %s read request", addr)
        return web.json_response(
            {GEN4_FIELD_ACTION: action, "result": "0", **fixture.as_wire_dict()}
        )

    fixtures = fan.state.all_fixtures()
    _LOGGER.info("fixture read-all request (%d fixtures)", len(fixtures))
    return web.json_response(
        {
            GEN4_FIELD_ACTION: action,
            "result": "0",
            "count": len(fixtures),
            GEN4_FIELD_FIXTURE_LIST: [f.as_wire_dict() for f in fixtures],
        }
    )
```

Add after `create_app`:

```python
def create_gen4_app(
    lights: int = 1, resume_delay_secs: float = 5.0
) -> web.Application:
    """Build the aiohttp application for a mock Gen4 fan."""
    app = web.Application()
    app["gen4_fan"] = MockGen4Fan(lights=lights, resume_delay_secs=resume_delay_secs)
    app.router.add_post("/device", _handle_device)
    app.router.add_post("/fixture", _handle_fixture)
    return app
```

Add a one-line comment above the `if action == GEN4_FIXTURE_ACTION_CONTROL` check noting that any other action value (in practice always the documented "read" action, `3`) is treated as a read — this is why the function never imports or compares against a read-action constant.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/mock_fan/ -v`
Expected: PASS — all tests, including every pre-existing legacy test (proving the disconnect-helper refactor from Step 3 was behavior-preserving) and every new Gen4 test.

- [ ] **Step 6: Commit**

```bash
git add mock_fan/server.py tests/mock_fan/test_server.py
git commit -m "feat: add Gen4 /device and /fixture handlers to mock_fan server"
```

---

### Task 3: `mock_fan/__main__.py` — CLI wiring

**Files:**
- Modify: `mock_fan/__main__.py`
- Modify: `tests/mock_fan/test_cli.py`
- Modify: `Makefile`
- Modify: `README.md`

**Interfaces:**
- Consumes: `mock_fan.server.create_gen4_app` (Task 2).
- Produces: no new public interface — this is the CLI entry point, not a library.

**Context:** `_parse_args`'s `--generation` currently uses `choices=sorted(PROFILES)`, where `PROFILES` only has `gen1_2`/`gen3` keys (Gen4 isn't a `GenerationProfile` — it's a different shape entirely, so it was never meant to live in that dict). Add `"gen4"` as a third accepted choice alongside `PROFILES`'s keys, and a new `--lights N` int flag that only makes sense when `--generation gen4` (silently unused otherwise — no cross-flag validation needed, matching the existing CLI's minimal-friction style).

- [ ] **Step 1: Write the failing tests**

Add to `tests/mock_fan/test_cli.py`:

```python
def test_gen4_generation_accepted():
    """--generation gen4 is a valid choice, distinct from the PROFILES dict."""
    args = _parse_args(["--generation", "gen4"])
    assert args.generation == "gen4"


def test_lights_defaults_to_one():
    """--lights defaults to 1 when omitted."""
    args = _parse_args(["--generation", "gen4"])
    assert args.lights == 1


def test_lights_explicit_value():
    """--lights accepts an explicit integer count."""
    args = _parse_args(["--generation", "gen4", "--lights", "3"])
    assert args.lights == 3


def test_lights_zero():
    """--lights 0 is accepted (a Gen4 fan with no lights)."""
    args = _parse_args(["--generation", "gen4", "--lights", "0"])
    assert args.lights == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/mock_fan/test_cli.py -k "gen4 or lights" -v`
Expected: FAIL — `--generation gen4` is rejected as an invalid choice (`SystemExit`), and `args.lights` doesn't exist.

- [ ] **Step 3: Update `_parse_args` and `main`**

In `mock_fan/__main__.py`, add `from .server import create_app, create_gen4_app` (replacing the existing `from .server import create_app` line).

Change the `--generation` argument's `choices`:

```python
    parser.add_argument(
        "--generation",
        required=True,
        choices=sorted([*PROFILES, "gen4"]),
        help="Fan hardware generation to emulate.",
    )
```

Add a new argument, anywhere after `--light`:

```python
    parser.add_argument(
        "--lights",
        type=int,
        default=1,
        help=(
            "Number of light fixtures on the mock Gen4 fan (default: 1). "
            "Only applies with --generation gen4."
        ),
    )
```

Replace the body of `main()` from `profile = PROFILES[args.generation]` through the `print(...)` call with:

```python
    if args.generation == "gen4":
        app = create_gen4_app(lights=args.lights)
        print(
            f"Mock fan listening on {args.host}:{args.port}"
            f" (generation=gen4, lights={args.lights})"
        )
    else:
        profile = PROFILES[args.generation]
        app = create_app(profile, breeze=args.breeze, light=args.light)
        print(
            f"Mock fan listening on {args.host}:{args.port}"
            f" (generation={profile.name}, breeze={'on' if args.breeze else 'off'},"
            f" light={'on' if args.light else 'off'})"
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/mock_fan/ -v`
Expected: PASS — all tests, including every pre-existing CLI test (`--generation gen1_2`/`gen3` still work exactly as before) and the four new Gen4 CLI tests.

- [ ] **Step 5: Update `Makefile` and `README.md`**

In `Makefile`'s `mock-fan` target, add a `LIGHTS` passthrough:

```makefile
.PHONY: mock-fan
mock-fan: ## Run a mock fan server (usage: make mock-fan GENERATION=gen3 [BREEZE=1] [LIGHTS=2] [PORT=8080]).
	@if [ -z "$(GENERATION)" ]; then \
		echo "Usage: make mock-fan GENERATION=<gen1_2|gen3|gen4> [BREEZE=1] [LIGHTS=2] [PORT=8080]"; \
		exit 1; \
	fi
	python -m mock_fan --generation $(GENERATION) --port $${PORT:-8080} $(if $(BREEZE),--breeze,) $(if $(LIGHTS),--lights $(LIGHTS),)
```

In `README.md`, in the mock-fan usage section (the block starting `To develop or test a client...`), add a line after the existing `--generation`/`--breeze`/`--no-light` explanation:

```markdown
For Gen4, use `--generation gen4 --lights N` (`--breeze`/`--no-light` don't apply —
Gen4 always exposes breeze fields on the fan fixture, and light count is controlled
by `--lights`, default 1; `--lights 0` simulates a fan with no light kit).
```

- [ ] **Step 6: Run the full suite one more time**

Run: `pytest tests/ -v`
Expected: PASS — the entire repo's test suite (both `tests/test_aiomodernforms.py` and `tests/mock_fan/`), confirming this task's `Makefile`/`README.md` doc changes didn't break anything (they aren't executable, but this is the final check before committing).

- [ ] **Step 7: Commit**

```bash
git add mock_fan/__main__.py tests/mock_fan/test_cli.py Makefile README.md
git commit -m "feat: add --generation gen4 and --lights CLI support to mock_fan"
```

---

## Self-Review

**Spec coverage:** the design spec's (`2026-07-29-gen4-fan-support-design.md`) §5 and the main plan's "Deferred: mock_fan Gen4 profile" section called for: a `GEN4` profile alongside `GEN1_2`/`GEN3` (→ Task 1's `Gen4FanState` fills this role, deliberately not shoehorned into `GenerationProfile`); `/device` + `/fixture` handlers with the same disconnect-simulation trick as reboot/factory_reset (→ Task 2); a `--generation gen4` / `--lights N` CLI (→ Task 3); integration tests through the real `ModernFormsDevice` covering `update()`, `light()`/`fan()`/`light_fixture()`, `away()`, `reboot()`, and `has_adaptive_learning()`/`has_sleep_timer()` returning `False` plus `decommission()` raising `ModernFormsNotSupportedError` (→ Task 2's tests). `factory_reset()` round-tripping is also covered (Task 2). Not carried over from the deferred section: `hardFactoryReset` was folded into the same disconnect-simulation path as `reboot` rather than kept as a fully separate no-response-until-timeout path with different semantics — this matches how the real `factory_reset()`/`reboot()` both already swallow the same exception, so one shared mechanism is correct and simpler than the deferred section's original phrasing implied.

**Placeholder scan:** no "TBD"/"TODO" markers; every step has complete, real code.

**Type consistency:** `Fixture`, `Gen4FanState`, `device_data`, `MockGen4Fan`, `create_gen4_app`, `_unresponsive_after`, `_hold_connection` are each defined exactly once (Tasks 1-2) and referenced identically by name in every later task/step that consumes them.
