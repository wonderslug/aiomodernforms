# Mock Fan Light Toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `--light`/`--no-light` toggle to the `mock_fan` service, analogous to the existing `--breeze` toggle, so a fan-only unit (no light kit) can be simulated. Unlike breeze, light defaults to **on**.

**Architecture:** Thread a `light: bool = True` parameter through the same three places `breeze: bool` already flows — `FanState`, `create_app()`, and the CLI — omitting `lightOn`/`lightBrightness`/the light timer field from the dynamic shadow and its validators when `light=False`, exactly mirroring how `wind`/`windSpeed` are omitted when `breeze=False`.

**Tech Stack:** Python 3.11+, `aiohttp`, `pytest` + `pytest-asyncio`, `argparse.BooleanOptionalAction` (stdlib, Python 3.9+) for the default-True CLI flag pair.

## Global Constraints

- Python >=3.11, use `from __future__ import annotations` and full type hints on every function/class.
- No new dependencies — `argparse.BooleanOptionalAction` is stdlib.
- Every `light` parameter (on `FanState.__init__`, `MockFan.__init__`, `create_app()`) **must default to `True`** — this is a correctness requirement, not a style choice: every existing call site in `tests/mock_fan/test_state.py` and `tests/mock_fan/test_server.py` calls these without a `light` argument, and must continue to pass unmodified.
- Every module/function/class needs a one-line docstring (this repo lints for this via flake8-docstrings).
- Reuse the existing `aiomodernforms.const` field-name constants (`COMMAND_LIGHT_POWER`, `COMMAND_LIGHT_BRIGHTNESS`, `COMMAND_LIGHT_SLEEP_TIMER`, `COMMAND_LIGHT_TIMER`) — no new constants needed, no hardcoded wire strings.
- Tests live under `tests/mock_fan/` (this repo's `pytest.ini` restricts testpaths to `tests`).
- This plan continues work already in progress on the `worktree-mock-fan-service` branch/worktree at `/Users/brian/development/aiomodernforms/.claude/worktrees/mock-fan-service` — do **not** create a new worktree or branch. Run all commands from that directory, using its existing venv (`.venv/bin/...`) — do not create a new venv.
- The prior plan's final review found that `pytest` passing locally is not sufficient — `flake8`/`isort --check-only` must also be run and pass before each task is considered done, since CI's `pre-commit run --all-files` lints more broadly than a plain test run catches. Each task's verification step below includes these explicitly; do not skip them.
- The Makefile's `lint-black`/`lint-flake8`/`lint-pylint`/`lint-mypy` targets already cover `mock_fan` (fixed in the prior plan's final review) — no Makefile changes needed in this plan.

---

### Task 1: Light toggle in fan state

**Files:**
- Modify: `mock_fan/state.py` (entire file — replace with the version below)
- Test: `tests/mock_fan/test_state.py` (append new tests; existing tests unchanged)

**Interfaces:**
- Consumes: `mock_fan.generations.GenerationProfile`, `GEN1_2`, `GEN3` (already exist).
- Produces: `FanState.__init__(self, profile: GenerationProfile, breeze: bool, light: bool = True) -> None` — the `light` parameter is new; `snapshot()`, `reset()`, `apply_commands()` signatures are unchanged. Later tasks (server) rely on this exact signature, including the `light` default.

- [ ] **Step 1: Write the failing tests**

First, replace the `from aiomodernforms.const import (...)` block at the top of `tests/mock_fan/test_state.py` with this (adds `COMMAND_LIGHT_POWER`, `COMMAND_LIGHT_SLEEP_TIMER`, `COMMAND_LIGHT_TIMER`, alphabetically sorted to match the file's existing style):

```python
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
```

Then append these test functions to the end of the file:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/mock_fan/test_state.py -v`
Expected: the 6 new tests FAIL with `TypeError: FanState.__init__() got an unexpected keyword argument 'light'` (or similar) — `light` doesn't exist yet on `FanState`.

- [ ] **Step 3: Replace `mock_fan/state.py` with this implementation**

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/mock_fan/test_state.py -v`
Expected: PASS (23 tests: 17 existing + 6 new)

- [ ] **Step 5: Lint check**

Run: `.venv/bin/flake8 mock_fan/state.py tests/mock_fan/test_state.py && .venv/bin/isort --check-only mock_fan/state.py tests/mock_fan/test_state.py`
Expected: both commands exit with no output (clean)

- [ ] **Step 6: Commit**

```bash
git add mock_fan/state.py tests/mock_fan/test_state.py
git commit -m "Add light toggle to mock fan state"
```

---

### Task 2: Light toggle in the HTTP server

**Files:**
- Modify: `mock_fan/server.py`
- Test: `tests/mock_fan/test_server.py` (append one new test; existing tests unchanged)

**Interfaces:**
- Consumes: `FanState.__init__(self, profile: GenerationProfile, breeze: bool, light: bool = True) -> None` (Task 1).
- Produces: `create_app(profile: GenerationProfile, breeze: bool, light: bool = True, resume_delay_secs: float = 5.0) -> aiohttp.web.Application` — the `light` parameter is new, inserted between `breeze` and `resume_delay_secs`; the CLI (Task 3) relies on this exact signature and default.

- [ ] **Step 1: Write the failing test**

Append this test to the end of `tests/mock_fan/test_server.py` (no new imports needed — `create_app`, `GEN1_2`, `aiomodernforms`, and `pytest` are already imported in this file):

```python
@pytest.mark.asyncio
async def test_light_disabled_ignores_light_commands():
    """A light=False fan silently ignores light() commands end-to-end."""
    app = create_app(GEN1_2, breeze=False, light=False)
    async with TestClient(TestServer(app)) as client:
        async with aiomodernforms.ModernFormsDevice(
            client.host, port=client.port, session=client.session
        ) as device:
            await device.update()
            await device.light(on=True, brightness=75)
            assert device.status.light_on is False
            assert device.status.light_brightness == 100
```

Note: a second test confirming light stays enabled by default (`create_app()` called without `light=`) is deliberately **not** added — `test_light_and_fan_round_trip`, already in this file and unmodified by this task, already calls `create_app(GEN1_2, breeze=False)` (no `light` argument) and asserts `device.light(on=True, brightness=75)` results in `light_on is True` / `light_brightness == 75`. That test passing is exactly the proof the default is unchanged; a second near-identical test would be redundant.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/mock_fan/test_server.py -v -k test_light_disabled_ignores_light_commands`
Expected: FAIL with `TypeError: create_app() got an unexpected keyword argument 'light'`

- [ ] **Step 3: Modify `mock_fan/server.py`**

Replace the `MockFan` class (currently lines 65-75) with:

```python
class MockFan:
    """Holds a mock fan's state and its simulated-disconnect window."""

    def __init__(
        self,
        profile: GenerationProfile,
        breeze: bool,
        resume_delay_secs: float,
        light: bool = True,
    ) -> None:
        """Initialize the mock fan's state for the given profile/breeze/light."""
        self.profile = profile
        self.state = FanState(profile, breeze, light)
        self.resume_delay_secs = resume_delay_secs
        self.unresponsive_until: float = 0.0
```

Replace the `create_app` function (currently lines 112-120) with:

```python
def create_app(
    profile: GenerationProfile,
    breeze: bool,
    light: bool = True,
    resume_delay_secs: float = 5.0,
) -> web.Application:
    """Build the aiohttp application for a mock fan of the given profile."""
    app = web.Application()
    app["fan"] = MockFan(profile, breeze, resume_delay_secs, light=light)
    app.router.add_post("/mf", _handle_mf)
    app.router.add_post("/config-read", _handle_config_read)
    return app
```

Everything else in `mock_fan/server.py` (the `_static_info`, `_handle_mf`, `_handle_config_read` functions, and the module-level constants) is unchanged.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/mock_fan/test_server.py -v`
Expected: PASS (9 tests: 8 existing + 1 new). The reboot/factory-reset tests will still take a few seconds each — that's expected, unrelated to this change.

- [ ] **Step 5: Lint check**

Run: `.venv/bin/flake8 mock_fan/server.py tests/mock_fan/test_server.py && .venv/bin/isort --check-only mock_fan/server.py tests/mock_fan/test_server.py`
Expected: both commands exit with no output (clean)

- [ ] **Step 6: Run the full suite once**

Run: `.venv/bin/pytest tests/ -q`
Expected: PASS, 99 tests (92 from before this plan + 6 from Task 1 + 1 from Task 2)

- [ ] **Step 7: Commit**

```bash
git add mock_fan/server.py tests/mock_fan/test_server.py
git commit -m "Add light toggle to mock fan HTTP server"
```

---

### Task 3: CLI flag and documentation

**Files:**
- Modify: `mock_fan/__main__.py`
- Modify: `README.md:84-86`
- Test: `tests/mock_fan/test_cli.py` (append new tests; existing tests unchanged)

**Interfaces:**
- Consumes: `create_app(profile: GenerationProfile, breeze: bool, light: bool = True, resume_delay_secs: float = 5.0) -> aiohttp.web.Application` (Task 2).
- Produces: `_parse_args()`'s returned `argparse.Namespace` gains a `.light: bool` attribute (default `True`). `main()`'s signature is unchanged.

- [ ] **Step 1: Write the failing tests**

Append these test functions to the end of `tests/mock_fan/test_cli.py`:

```python
def test_light_defaults_to_true():
    """--light defaults to True when neither --light nor --no-light is given."""
    args = _parse_args(["--generation", "gen1_2"])
    assert args.light is True


def test_no_light_flag():
    """--no-light sets args.light to False."""
    args = _parse_args(["--generation", "gen1_2", "--no-light"])
    assert args.light is False


def test_explicit_light_flag():
    """--light explicitly sets args.light to True."""
    args = _parse_args(["--generation", "gen1_2", "--light"])
    assert args.light is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/mock_fan/test_cli.py -v -k "light"`
Expected: FAIL with `AttributeError: 'Namespace' object has no attribute 'light'`

- [ ] **Step 3: Modify `mock_fan/__main__.py`**

Replace this block:

```text
    parser.add_argument(
        "--breeze",
        action="store_true",
        help="Enable breeze (wind) mode support.",
    )
    parser.add_argument(
        "--host",
```

with:

```text
    parser.add_argument(
        "--breeze",
        action="store_true",
        help="Enable breeze (wind) mode support.",
    )
    parser.add_argument(
        "--light",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Enable light control (default: enabled). "
            "Use --no-light to simulate a fan-only unit."
        ),
    )
    parser.add_argument(
        "--host",
```

Then replace the `main()` function with:

```python
def main(argv: list[str] | None = None) -> None:
    """Run the mock fan server until interrupted."""
    args = _parse_args(argv)
    profile = PROFILES[args.generation]
    app = create_app(profile, breeze=args.breeze, light=args.light)
    print(
        f"Mock fan listening on {args.host}:{args.port}"
        f" (generation={profile.name}, breeze={'on' if args.breeze else 'off'},"
        f" light={'on' if args.light else 'off'})"
    )
    web.run_app(app, host=args.host, port=args.port, print=None)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/mock_fan/test_cli.py -v`
Expected: PASS (7 tests: 4 existing + 3 new)

- [ ] **Step 5: Update the README**

In `README.md`, replace this paragraph (currently lines 84-86):

```markdown
`--generation` is `gen1_2` or `gen3` and is required; `--breeze` optionally
enables breeze/wind mode support. Point your client at the printed
host/port exactly as you would a real fan.
```

with:

```markdown
`--generation` is `gen1_2` or `gen3` and is required; `--breeze` optionally
enables breeze/wind mode support; `--no-light` simulates a fan-only unit
with no light kit (light is on by default). Point your client at the
printed host/port exactly as you would a real fan.
```

- [ ] **Step 6: Manually smoke-test the CLI**

Run: `.venv/bin/python -m mock_fan --generation gen1_2 --no-light --port 8091` in one terminal, then in another:
```bash
curl -s -X POST http://127.0.0.1:8091/mf -d '{"queryDynamicShadowData": true}' | python3 -m json.tool
```
Expected: the JSON response has no `lightOn`, `lightBrightness`, or `lightSleepTimer` keys. Stop the server with Ctrl-C.

- [ ] **Step 7: Lint check and full suite**

Run: `.venv/bin/flake8 mock_fan tests/mock_fan && .venv/bin/isort --check-only mock_fan tests/mock_fan && .venv/bin/mypy -p mock_fan && .venv/bin/pytest tests/ -q`
Expected: flake8 and isort clean (no output), mypy clean, pytest shows 102 passed (99 from Task 2 + 3 new)

- [ ] **Step 8: Commit**

```bash
git add mock_fan/__main__.py tests/mock_fan/test_cli.py README.md
git commit -m "Add --light/--no-light CLI flag to mock fan"
```
