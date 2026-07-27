# API Parity Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring `aiomodernforms` up to full parity with `WAC_Modern_Forms_3rd_Party_API_Reference.pdf` — fix the Gen 3 sleep-timer bug, capture every documented shadow/info field, add every documented write command, and add `/config-read` support.

**Architecture:** All changes are additive extensions to the existing three-module design (`const.py` for wire-format constants, `models.py` for `State`/`Info`/`Device` dataclasses and parsing, `modernforms.py` for the `ModernFormsDevice` client). Generation differences (Gen 1/2 vs Gen 3) are handled the same way the existing code already handles Breeze mode: by detecting which shadow keys a device's response actually contains, not by hardcoding a generation number.

**Tech Stack:** Python 3.11, aiohttp, pytest + pytest-asyncio + aresponses (HTTP mocking).

## Global Constraints

- Python `>=3.11` (`setup.py`).
- Line length 88 chars (black default; `flake8` `max-line-length=88`).
- mypy runs with `disallow_untyped_calls=True`, `disallow_untyped_defs=True`, `no_implicit_optional=True` — give every new function full parameter and return type hints, and never rely on an implicit `Optional` (e.g. write `Optional[int] = None`, not `int = None`). Where a new method mirrors an existing untyped sibling (e.g. `has_breeze_mode`, `reboot`), match that sibling's style so the file stays internally consistent.
- `flake8-docstrings` is enabled (`D202`, `W503` ignored) — every new public function/class needs a one-line docstring.
- Pre-commit hooks (black, isort, autopep8, pylint, mypy, flake8, pyupgrade `--py36-plus`) run automatically on `git commit`. If a hook reformats files, the commit aborts on the first attempt — run `git add -u` and re-run the same `git commit` command.
- Tests use `@pytest.mark.asyncio` and the `aresponses` fixture (auto-provided by the `aresponses` pytest plugin, already used throughout `tests/test_aiomodernforms.py` — no fixture setup needed).
- Run the full suite with `pytest tests/ -v` before every commit that touches source files.

---

### Task 1: Fix `away()`/`adaptive_learning()` missing-argument bug

**Files:**
- Modify: `aiomodernforms/modernforms.py:347-360`
- Test: `tests/test_aiomodernforms.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `ModernFormsDevice.away(away: bool)` and `ModernFormsDevice.adaptive_learning(adaptive_learning: bool)` — both now require their argument (no default). No other task depends on this signature.

**Context:** `async def away(self, away=bool):` uses `=bool` (the builtin type object) as the parameter's *default value* — not a type hint. Calling `device.away()` with no argument doesn't raise a clean error; it proceeds to build `{COMMAND_AWAY_MODE: bool, ...}` and only fails deep inside aiohttp's JSON encoder. The fix is to drop the bogus default so a missing argument fails immediately and obviously.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_aiomodernforms.py`, after `test_adaptive_learning` (currently ending at line 502):

```python
@pytest.mark.asyncio
async def test_away_requires_argument():
    """Test that away() requires an explicit boolean argument."""
    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        with pytest.raises(TypeError):
            await device.away()  # type: ignore[call-arg]


@pytest.mark.asyncio
async def test_adaptive_learning_requires_argument():
    """Test that adaptive_learning() requires an explicit boolean argument."""
    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        with pytest.raises(TypeError):
            await device.adaptive_learning()  # type: ignore[call-arg]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_aiomodernforms.py::test_away_requires_argument tests/test_aiomodernforms.py::test_adaptive_learning_requires_argument -v`
Expected: FAIL — no `TypeError` is raised (the call instead hangs trying to make an unmocked HTTP request, or errors with an unrelated `aresponses`/connection failure), because the current default silently swallows the missing argument.

- [ ] **Step 3: Fix the signatures**

In `aiomodernforms/modernforms.py`, change:

```python
    async def away(self, away=bool):
```

to:

```python
    async def away(self, away: bool):
```

And change:

```python
    async def adaptive_learning(self, adaptive_learning=bool):
```

to:

```python
    async def adaptive_learning(self, adaptive_learning: bool):
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_aiomodernforms.py -v`
Expected: PASS — all tests, including the two new ones and the pre-existing `test_away`/`test_adaptive_learning` (which already pass a real argument, so their behavior is unchanged).

- [ ] **Step 5: Commit**

```bash
git add aiomodernforms/modernforms.py tests/test_aiomodernforms.py
git commit -m "fix: require explicit argument for away() and adaptive_learning()"
```

---

### Task 2: Capture dropped dynamic-shadow fields in `State`

**Files:**
- Modify: `aiomodernforms/const.py` (append after line 77)
- Modify: `aiomodernforms/models.py:7-33` (imports), `:74-105` (`State` dataclass)
- Test: `tests/test_aiomodernforms.py:55-73` (fixture), new tests

**Interfaces:**
- Consumes: nothing new.
- Produces: `State.rf_pair_mode_active: bool`, `State.reset_rf_pair_list: bool`, `State.factory_reset: bool`, `State.decommission: bool`, `State.schedule: str`, `State.user_data: str`. Consumed by Task 6 (new control methods assert against these) and Task 7 (unrelated, no dependency).

**Context:** `tests/test_aiomodernforms.py`'s `basic_response`/`breeze_mode_response` fixtures (lines 36-73) already include `schedule`, `rfPairModeActive`, `resetRfPairList`, `factoryReset`, and `decommission` keys — they're sent by the mock device today but `State.from_dict` doesn't know about them, so they're silently dropped. `userData` (Gen 3 only) isn't in either fixture yet.

- [ ] **Step 1: Write the failing tests**

In `tests/test_aiomodernforms.py`, add `"userData": "cloud",` to the `breeze_mode_response` dict (currently lines 55-73), so it reads:

```python
breeze_mode_response = {
    "adaptiveLearning": False,
    "awayModeEnabled": False,
    "clientId": "MF_000000000000",
    "decommission": False,
    "factoryReset": False,
    "fanDirection": "forward",
    "fanOn": False,
    "fanSleepTimer": 0,
    "fanSpeed": 3,
    "lightBrightness": 50,
    "lightOn": False,
    "lightSleepTimer": 0,
    "resetRfPairList": False,
    "rfPairModeActive": False,
    "schedule": "",
    "userData": "cloud",
    "wind": False,
    "windSpeed": 2,
}
```

Then add two new tests, after `test_basic_status` (currently ending at line 111):

```python
@pytest.mark.asyncio
async def test_full_state_capture(aresponses):
    """Test that all documented dynamic shadow fields are captured on State."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        assert device.status.schedule == basic_response["schedule"]
        assert device.status.rf_pair_mode_active == basic_response["rfPairModeActive"]
        assert device.status.reset_rf_pair_list == basic_response["resetRfPairList"]
        assert device.status.factory_reset == basic_response["factoryReset"]
        assert device.status.decommission == basic_response["decommission"]
        assert device.status.user_data == ""


@pytest.mark.asyncio
async def test_gen3_user_data_capture(aresponses):
    """Test that Gen 3's userData field is captured on State."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=breeze_mode_response)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        assert device.status.user_data == breeze_mode_response["userData"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_aiomodernforms.py::test_full_state_capture tests/test_aiomodernforms.py::test_gen3_user_data_capture -v`
Expected: FAIL with `AttributeError: 'State' object has no attribute 'schedule'` (or similar for the other new attributes).

- [ ] **Step 3: Add the constants**

Append to `aiomodernforms/const.py` (after line 77, `SLEEP_TIMER_CANCEL = 0`):

```python

STATE_RF_PAIR_MODE_ACTIVE = "rfPairModeActive"
STATE_RESET_RF_PAIR_LIST = "resetRfPairList"
STATE_FACTORY_RESET = "factoryReset"
STATE_DECOMMISSION = "decommission"
STATE_SCHEDULE = "schedule"
STATE_USER_DATA = "userData"
```

- [ ] **Step 4: Update `State` in `aiomodernforms/models.py`**

Update the `from .const import (...)` block (lines 7-33) to add the six new names, keeping alphabetical order:

```python
from .const import (
    DEFAULT_WIND_SPEED,
    INFO_CLIENT_ID,
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
    STATE_ADAPTIVE_LEARNING,
    STATE_AWAY_MODE,
    STATE_DECOMMISSION,
    STATE_FACTORY_RESET,
    STATE_FAN_DIRECTION,
    STATE_FAN_POWER,
    STATE_FAN_SLEEP_TIMER,
    STATE_FAN_SPEED,
    STATE_LIGHT_BRIGHTNESS,
    STATE_LIGHT_POWER,
    STATE_LIGHT_SLEEP_TIMER,
    STATE_RESET_RF_PAIR_LIST,
    STATE_RF_PAIR_MODE_ACTIVE,
    STATE_SCHEDULE,
    STATE_USER_DATA,
    STATE_WIND_POWER,
    STATE_WIND_SPEED,
)
```

Update the `State` dataclass (lines 74-105):

```python
@dataclass
class State:
    """Object holding the state of Modern Forms Device."""

    fan_on: bool
    fan_speed: int
    fan_direction: str
    fan_sleep_timer: int
    light_on: bool
    light_brightness: int
    light_sleep_timer: int
    away_mode_enabled: bool
    adaptive_learning_enabled: bool
    wind: bool
    wind_speed: int
    rf_pair_mode_active: bool
    reset_rf_pair_list: bool
    factory_reset: bool
    decommission: bool
    schedule: str
    user_data: str

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> State:
        """Return State object from Modern Forms API response."""
        return State(
            fan_on=data.get(STATE_FAN_POWER, False),
            fan_speed=data.get(STATE_FAN_SPEED, 6),
            fan_direction=data.get(STATE_FAN_DIRECTION, "forward"),
            fan_sleep_timer=data.get(STATE_FAN_SLEEP_TIMER, 0),
            light_on=data.get(STATE_LIGHT_POWER, False),
            light_brightness=data.get(STATE_LIGHT_BRIGHTNESS, 100),
            light_sleep_timer=data.get(STATE_LIGHT_SLEEP_TIMER, 0),
            away_mode_enabled=data.get(STATE_AWAY_MODE, False),
            adaptive_learning_enabled=data.get(STATE_ADAPTIVE_LEARNING, False),
            wind=data.get(STATE_WIND_POWER, None),
            wind_speed=data.get(STATE_WIND_SPEED, DEFAULT_WIND_SPEED),
            rf_pair_mode_active=data.get(STATE_RF_PAIR_MODE_ACTIVE, False),
            reset_rf_pair_list=data.get(STATE_RESET_RF_PAIR_LIST, False),
            factory_reset=data.get(STATE_FACTORY_RESET, False),
            decommission=data.get(STATE_DECOMMISSION, False),
            schedule=data.get(STATE_SCHEDULE, ""),
            user_data=data.get(STATE_USER_DATA, ""),
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_aiomodernforms.py -v`
Expected: PASS — all tests, including the two new ones. Confirm no existing test broke (they only read fields that still exist with unchanged defaults).

- [ ] **Step 6: Commit**

```bash
git add aiomodernforms/const.py aiomodernforms/models.py tests/test_aiomodernforms.py
git commit -m "feat: capture rfPairModeActive, resetRfPairList, factoryReset, decommission, schedule, and userData in State"
```

---

### Task 3: Capture Gen 3 `Info` fields (`brand`, `dateCode`)

**Files:**
- Modify: `aiomodernforms/const.py` (append)
- Modify: `aiomodernforms/models.py:1-71` (imports, `Info` dataclass)
- Test: `tests/test_aiomodernforms.py:76-90` (new fixture), new tests

**Interfaces:**
- Consumes: nothing new.
- Produces: `Info.brand: Optional[int]`, `Info.date_code: str`. Not consumed by any other task.

- [ ] **Step 1: Write the failing tests**

In `tests/test_aiomodernforms.py`, add a new fixture after `basic_info` (currently ending at line 90):

```python
gen3_info = {
    "clientId": "MF_C82B9698E5AC",
    "mac": "C8:2B:96:98:E5:AC",
    "lightType": "",
    "fanType": "2003-52",
    "fanMotorType": "DC125X12",
    "brand": 0,
    "dateCode": "20220101",
    "owner": "someone@somewhere.com",
    "federatedIdentity": "us-east-1:f3da237b-c19c-4f61-b387-0e6dde2e470b",
    "deviceName": "Fan",
    "firmwareVersion": "02.00.0003",
    "mainMcuFirmwareVersion": "02.01.0000",
    "firmwareUrl": "",
}
```

Then add two tests, after `test_basic_status`:

```python
@pytest.mark.asyncio
async def test_gen3_info_capture(aresponses):
    """Test that Gen 3's brand and dateCode info fields are captured."""
    aresponses.add("fan.local", "/mf", "POST", response=gen3_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        assert device.info.brand == gen3_info["brand"]
        assert device.info.date_code == gen3_info["dateCode"]


@pytest.mark.asyncio
async def test_gen1_2_info_defaults(aresponses):
    """Test that Gen 1/2 info responses default brand/dateCode sensibly."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        assert device.info.brand is None
        assert device.info.date_code == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_aiomodernforms.py::test_gen3_info_capture tests/test_aiomodernforms.py::test_gen1_2_info_defaults -v`
Expected: FAIL with `TypeError: Info.__init__() got an unexpected keyword argument` or `AttributeError` once `Info.from_dict` is reached — actually fails first at collection/construction inside `from_dict` since `brand`/`date_code` don't exist yet as fields.

- [ ] **Step 3: Add the constants**

Append to `aiomodernforms/const.py` (after the `STATE_USER_DATA` line added in Task 2):

```python

INFO_BRAND = "brand"
INFO_DATE_CODE = "dateCode"
```

- [ ] **Step 4: Update `Info` in `aiomodernforms/models.py`**

Update the `typing` import (line 5) to add `Optional`:

```python
from typing import Any, Dict, Optional
```

Update the `.const` import block to add `INFO_BRAND` and `INFO_DATE_CODE`:

```python
from .const import (
    DEFAULT_WIND_SPEED,
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
    STATE_ADAPTIVE_LEARNING,
    STATE_AWAY_MODE,
    STATE_DECOMMISSION,
    STATE_FACTORY_RESET,
    STATE_FAN_DIRECTION,
    STATE_FAN_POWER,
    STATE_FAN_SLEEP_TIMER,
    STATE_FAN_SPEED,
    STATE_LIGHT_BRIGHTNESS,
    STATE_LIGHT_POWER,
    STATE_LIGHT_SLEEP_TIMER,
    STATE_RESET_RF_PAIR_LIST,
    STATE_RF_PAIR_MODE_ACTIVE,
    STATE_SCHEDULE,
    STATE_USER_DATA,
    STATE_WIND_POWER,
    STATE_WIND_SPEED,
)
```

Update the `Info` dataclass (originally lines 37-71):

```python
@dataclass
class Info:
    """Info about the Modern Forms device."""

    client_id: str
    mac_address: str
    light_type: str
    fan_type: str
    fan_motor_type: str
    production_lot_number: str
    product_sku: str
    owner: str
    federated_identity: str
    device_name: str
    firmware_version: str
    main_mcu_firmware_version: str
    firmware_url: str
    brand: Optional[int]
    date_code: str

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> Info:
        """Return Info object from Modern Forms API response."""
        return Info(
            client_id=data.get(INFO_CLIENT_ID, ""),
            mac_address=data.get(INFO_MAC, ""),
            light_type=data.get(INFO_LIGHT_TYPE, ""),
            fan_type=data.get(INFO_FAN_TYPE, ""),
            fan_motor_type=data.get(INFO_FAN_MOTOR_TYPE, ""),
            production_lot_number=data.get(INFO_PRODUCTION_LOT_NUMBER, ""),
            product_sku=data.get(INFO_PRODUCT_SKU, ""),
            owner=data.get(INFO_OWNER, ""),
            federated_identity=data.get(INFO_FEDERATED_IDENTITY, ""),
            device_name=data.get(INFO_DEVICE_NAME, ""),
            firmware_version=data.get(INFO_FIRMWARE_VERSION, ""),
            main_mcu_firmware_version=data.get(INFO_MAIN_MCU_FIRMWARE_VERSION, ""),
            firmware_url=data.get(INFO_FIRMWARE_URL, ""),
            brand=data.get(INFO_BRAND),
            date_code=data.get(INFO_DATE_CODE, ""),
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_aiomodernforms.py -v`
Expected: PASS — all tests.

- [ ] **Step 6: Commit**

```bash
git add aiomodernforms/const.py aiomodernforms/models.py tests/test_aiomodernforms.py
git commit -m "feat: capture Gen 3 brand and dateCode info fields"
```

---

### Task 4: Relative-timer capability detection (`fan_timer`/`light_timer`, `has_relative_timers()`)

**Files:**
- Modify: `aiomodernforms/const.py` (append)
- Modify: `aiomodernforms/models.py` (`State` fields, `Device.has_relative_timers()`)
- Modify: `aiomodernforms/modernforms.py:206-213` (add public proxy after `has_breeze_mode`)
- Test: `tests/test_aiomodernforms.py` (new fixture, new tests)

**Interfaces:**
- Consumes: `ModernFormsNotInitializedError` (already imported in `modernforms.py`).
- Produces: `State.fan_timer: Optional[int]`, `State.light_timer: Optional[int]`, `Device.has_relative_timers() -> bool`, `ModernFormsDevice.has_relative_timers()`. Consumed by Task 5 (`_sleep_command` branches on this).

**Context:** Gen 3 fans report sleep timers under different keys than Gen 1/2 (`fanTimer`/`lightTimer` holding seconds-until-off, vs `fanSleepTimer`/`lightSleepTimer` holding an epoch timestamp). This task only adds *detection* — reading the new keys and exposing a capability check, mirroring the existing `has_wind()` / `has_breeze_mode()` pair exactly. Task 5 wires this into `light()`/`fan()`.

- [ ] **Step 1: Write the failing tests**

Add a new fixture to `tests/test_aiomodernforms.py`, after `breeze_mode_response`:

```python
gen3_relative_timer_response = {
    "adaptiveLearning": False,
    "awayModeEnabled": False,
    "clientId": "MF_C82B9698E5AC",
    "decommission": False,
    "factoryReset": False,
    "fanDirection": "forward",
    "fanOn": False,
    "fanTimer": 0,
    "fanSpeed": 3,
    "lightBrightness": 50,
    "lightOn": False,
    "lightTimer": 0,
    "resetRfPairList": False,
    "rfPairModeActive": False,
    "schedule": "",
    "userData": "cloud",
    "wind": False,
    "windSpeed": 2,
}
```

Add tests, after `test_nonupdated_device_for_breeze_mode` (currently ending at line 363):

```python
@pytest.mark.asyncio
async def test_has_relative_timers_true_for_gen3(aresponses):
    """Test that a Gen 3-style response (fanTimer/lightTimer) is detected."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add(
        "fan.local", "/mf", "POST", response=gen3_relative_timer_response
    )

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        assert device.status.fan_timer == gen3_relative_timer_response["fanTimer"]
        assert device.status.light_timer == gen3_relative_timer_response["lightTimer"]
        assert device.has_relative_timers() is True


@pytest.mark.asyncio
async def test_has_relative_timers_false_for_gen1_2(aresponses):
    """Test that a Gen 1/2-style response is not mistaken for relative timers."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        assert device.status.fan_timer is None
        assert device.status.light_timer is None
        assert device.has_relative_timers() is False


@pytest.mark.asyncio
async def test_nonupdated_device_for_relative_timers():
    """Test that has_relative_timers only looks at an initialized device."""
    with pytest.raises(ModernFormsNotInitializedError):
        async with aiomodernforms.ModernFormsDevice("fan.local") as device:
            device.has_relative_timers()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_aiomodernforms.py::test_has_relative_timers_true_for_gen3 tests/test_aiomodernforms.py::test_has_relative_timers_false_for_gen1_2 tests/test_aiomodernforms.py::test_nonupdated_device_for_relative_timers -v`
Expected: FAIL with `AttributeError: 'State' object has no attribute 'fan_timer'` (first test) and `AttributeError: 'ModernFormsDevice' object has no attribute 'has_relative_timers'` (other two).

- [ ] **Step 3: Add the constants**

Append to `aiomodernforms/const.py` (after the `INFO_DATE_CODE` line added in Task 3):

```python

STATE_FAN_TIMER = "fanTimer"
STATE_LIGHT_TIMER = "lightTimer"
```

- [ ] **Step 4: Update `State` and `Device` in `aiomodernforms/models.py`**

Add `STATE_FAN_TIMER` and `STATE_LIGHT_TIMER` to the `.const` import block:

```python
from .const import (
    DEFAULT_WIND_SPEED,
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
    STATE_ADAPTIVE_LEARNING,
    STATE_AWAY_MODE,
    STATE_DECOMMISSION,
    STATE_FACTORY_RESET,
    STATE_FAN_DIRECTION,
    STATE_FAN_POWER,
    STATE_FAN_SLEEP_TIMER,
    STATE_FAN_SPEED,
    STATE_FAN_TIMER,
    STATE_LIGHT_BRIGHTNESS,
    STATE_LIGHT_POWER,
    STATE_LIGHT_SLEEP_TIMER,
    STATE_LIGHT_TIMER,
    STATE_RESET_RF_PAIR_LIST,
    STATE_RF_PAIR_MODE_ACTIVE,
    STATE_SCHEDULE,
    STATE_USER_DATA,
    STATE_WIND_POWER,
    STATE_WIND_SPEED,
)
```

Add `fan_timer`/`light_timer` fields to `State` (append to the field list) and to `from_dict`:

```python
@dataclass
class State:
    """Object holding the state of Modern Forms Device."""

    fan_on: bool
    fan_speed: int
    fan_direction: str
    fan_sleep_timer: int
    fan_timer: Optional[int]
    light_on: bool
    light_brightness: int
    light_sleep_timer: int
    light_timer: Optional[int]
    away_mode_enabled: bool
    adaptive_learning_enabled: bool
    wind: bool
    wind_speed: int
    rf_pair_mode_active: bool
    reset_rf_pair_list: bool
    factory_reset: bool
    decommission: bool
    schedule: str
    user_data: str

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> State:
        """Return State object from Modern Forms API response."""
        return State(
            fan_on=data.get(STATE_FAN_POWER, False),
            fan_speed=data.get(STATE_FAN_SPEED, 6),
            fan_direction=data.get(STATE_FAN_DIRECTION, "forward"),
            fan_sleep_timer=data.get(STATE_FAN_SLEEP_TIMER, 0),
            fan_timer=data.get(STATE_FAN_TIMER),
            light_on=data.get(STATE_LIGHT_POWER, False),
            light_brightness=data.get(STATE_LIGHT_BRIGHTNESS, 100),
            light_sleep_timer=data.get(STATE_LIGHT_SLEEP_TIMER, 0),
            light_timer=data.get(STATE_LIGHT_TIMER),
            away_mode_enabled=data.get(STATE_AWAY_MODE, False),
            adaptive_learning_enabled=data.get(STATE_ADAPTIVE_LEARNING, False),
            wind=data.get(STATE_WIND_POWER, None),
            wind_speed=data.get(STATE_WIND_SPEED, DEFAULT_WIND_SPEED),
            rf_pair_mode_active=data.get(STATE_RF_PAIR_MODE_ACTIVE, False),
            reset_rf_pair_list=data.get(STATE_RESET_RF_PAIR_LIST, False),
            factory_reset=data.get(STATE_FACTORY_RESET, False),
            decommission=data.get(STATE_DECOMMISSION, False),
            schedule=data.get(STATE_SCHEDULE, ""),
            user_data=data.get(STATE_USER_DATA, ""),
        )
```

This requires `Optional` in `models.py`'s `typing` import — already added in Task 3 (`from typing import Any, Dict, Optional`).

Add a method to the `Device` class (after `has_wind`, currently lines 128-130):

```python
    def has_relative_timers(self) -> bool:
        """See if the Fan uses relative (seconds-until-off) sleep timers."""
        return self.state.fan_timer is not None or self.state.light_timer is not None
```

- [ ] **Step 5: Add the public proxy in `aiomodernforms/modernforms.py`**

Add, after `has_breeze_mode` (currently lines 206-213):

```python
    def has_relative_timers(self):
        """See if the Fan uses relative (seconds-until-off) sleep timers."""
        if self._device is None:
            raise ModernFormsNotInitializedError(
                "The device has not been initialized.  "
                + "Please run update on the device before getting state"
            )
        return self._device.has_relative_timers()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_aiomodernforms.py -v`
Expected: PASS — all tests.

- [ ] **Step 7: Commit**

```bash
git add aiomodernforms/const.py aiomodernforms/models.py aiomodernforms/modernforms.py tests/test_aiomodernforms.py
git commit -m "feat: detect Gen 3 relative sleep timers via has_relative_timers()"
```

---

### Task 5: Generation-aware sleep timer commands (`_sleep_command`)

**Files:**
- Modify: `aiomodernforms/const.py` (append)
- Modify: `aiomodernforms/modernforms.py:15-42` (imports), `:215-263` (`light`), `:265-345` (`fan`)
- Modify: `aiomodernforms/__init__.py:2-34` (exports)
- Test: `tests/test_aiomodernforms.py`

**Interfaces:**
- Consumes: `Device.has_relative_timers()` and `State.fan_timer`/`light_timer` (Task 4); `gen3_relative_timer_response` fixture (Task 4).
- Produces: `ModernFormsDevice._sleep_command(epoch_command: str, relative_command: str, sleep: Union[int, datetime]) -> Dict[str, int]` (private — only `light()`/`fan()` call it). `light()`/`fan()`'s external behavior for the `sleep` parameter is otherwise unchanged for Gen 1/2 devices.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_aiomodernforms.py`'s `.const` import block, alongside the other `STATE_*` imports:

```python
    STATE_FAN_TIMER,
    STATE_LIGHT_TIMER,
```

(these constants already exist as of Task 4; this just imports them into the test file).

Add tests, after `test_fan_with_breeze_mode` (currently ending at line 344):

```python
@pytest.mark.asyncio
async def test_light_sleep_relative_timer_int(aresponses):
    """Test that light sleep uses relative seconds on a Gen 3-style device."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add(
        "fan.local", "/mf", "POST", response=gen3_relative_timer_response
    )

    async def evaluate_request(request):
        data = await request.json()
        assert aiomodernforms.COMMAND_LIGHT_TIMER in data
        assert aiomodernforms.COMMAND_LIGHT_SLEEP_TIMER not in data
        assert data[aiomodernforms.COMMAND_LIGHT_TIMER] == 120
        modified_response = gen3_relative_timer_response.copy()
        modified_response[STATE_LIGHT_TIMER] = data[aiomodernforms.COMMAND_LIGHT_TIMER]
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(modified_response),
        )

    aresponses.add("fan.local", "/mf", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        await device.light(sleep=120)
        assert device.status.light_timer == 120


@pytest.mark.asyncio
async def test_fan_sleep_relative_timer_datetime(aresponses):
    """Test that fan sleep uses relative seconds on a Gen 3-style device."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add(
        "fan.local", "/mf", "POST", response=gen3_relative_timer_response
    )

    async def evaluate_request(request):
        data = await request.json()
        assert aiomodernforms.COMMAND_FAN_TIMER in data
        assert aiomodernforms.COMMAND_FAN_SLEEP_TIMER not in data
        modified_response = gen3_relative_timer_response.copy()
        modified_response[STATE_FAN_TIMER] = data[aiomodernforms.COMMAND_FAN_TIMER]
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(modified_response),
        )

    aresponses.add("fan.local", "/mf", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        sleep_time = datetime.now() + timedelta(minutes=2)
        await device.fan(sleep=sleep_time)
        assert device.status.fan_timer == pytest.approx(120, abs=2)


@pytest.mark.asyncio
async def test_light_sleep_relative_timer_clear(aresponses):
    """Test that sleep=0 cancels the timer under relative-timer semantics too."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add(
        "fan.local", "/mf", "POST", response=gen3_relative_timer_response
    )

    async def evaluate_request(request):
        data = await request.json()
        assert data.get(aiomodernforms.COMMAND_LIGHT_TIMER) == 0
        modified_response = gen3_relative_timer_response.copy()
        modified_response[STATE_LIGHT_TIMER] = 0
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(modified_response),
        )

    aresponses.add("fan.local", "/mf", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        await device.light(sleep=0)
        assert device.status.light_timer == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_aiomodernforms.py::test_light_sleep_relative_timer_int tests/test_aiomodernforms.py::test_fan_sleep_relative_timer_datetime tests/test_aiomodernforms.py::test_light_sleep_relative_timer_clear -v`
Expected: FAIL with `AttributeError: module 'aiomodernforms' has no attribute 'COMMAND_LIGHT_TIMER'` (or the assertion `COMMAND_LIGHT_TIMER in data` failing, since `light()`/`fan()` still always send the epoch-timer command).

- [ ] **Step 3: Add the constants**

Append to `aiomodernforms/const.py` (after the `STATE_LIGHT_TIMER` line added in Task 4):

```python

COMMAND_FAN_TIMER = "fanTimer"
COMMAND_LIGHT_TIMER = "lightTimer"
```

- [ ] **Step 4: Add `_sleep_command` and rewire `light()`/`fan()` in `aiomodernforms/modernforms.py`**

Update the `.const` import block (lines 15-42) to add `COMMAND_FAN_TIMER` and `COMMAND_LIGHT_TIMER`, alphabetically:

```python
from .const import (
    COMMAND_ADAPTIVE_LEARNING,
    COMMAND_AWAY_MODE,
    COMMAND_FAN_DIRECTION,
    COMMAND_FAN_POWER,
    COMMAND_FAN_SLEEP_TIMER,
    COMMAND_FAN_SPEED,
    COMMAND_FAN_TIMER,
    COMMAND_LIGHT_BRIGHTNESS,
    COMMAND_LIGHT_POWER,
    COMMAND_LIGHT_SLEEP_TIMER,
    COMMAND_LIGHT_TIMER,
    COMMAND_QUERY_STATIC_DATA,
    COMMAND_QUERY_STATUS,
    COMMAND_REBOOT,
    COMMAND_WIND,
    COMMAND_WIND_SPEED,
    DEFAULT_API_ENDPOINT,
    DEFAULT_PORT,
    DEFAULT_TIMEOUT_SECS,
    FAN_DIRECTION_FORWARD,
    FAN_DIRECTION_REVERSE,
    FAN_SPEED_HIGH_VALUE,
    FAN_SPEED_LOW_VALUE,
    LIGHT_BRIGHTNESS_HIGH_VALUE,
    LIGHT_BRIGHTNESS_LOW_VALUE,
    SLEEP_TIMER_CANCEL,
    WIND_SPEED_HIGH_VALUE,
    WIND_SPEED_LOW_VALUE,
)
```

Add a new private method, immediately before `light()` (currently line 215):

```python
    def _sleep_command(
        self, epoch_command: str, relative_command: str, sleep: Union[int, datetime]
    ) -> Dict[str, int]:
        """Build the timer command for `sleep`.

        Gen 1/2 fans store sleep timers as an epoch timestamp under
        `epoch_command`. Gen 3 fans store them as seconds-until-off under
        `relative_command`. Which one a given device uses is only knowable
        after `update()` has populated `has_relative_timers()`; before that,
        epoch semantics (the historical default) are used.
        """
        use_relative = self._device is not None and self._device.has_relative_timers()
        command = relative_command if use_relative else epoch_command

        if isinstance(sleep, int):
            if sleep <= 0:
                return {command: SLEEP_TIMER_CANCEL}
            if use_relative:
                return {command: sleep}
            sleep_till = datetime.now() + timedelta(seconds=sleep)
            return {command: int(sleep_till.timestamp())}

        if isinstance(sleep, datetime) and not (
            sleep < datetime.now() or sleep > (datetime.now() + timedelta(hours=24))
        ):
            if use_relative:
                return {command: int((sleep - datetime.now()).total_seconds())}
            return {command: int(sleep.timestamp())}

        raise ModernFormsInvalidSettingsError(
            "The time to sleep till must be a datetime object that is not more"
            + " then 24 hours into the future, or an interger for number of"
            + " seconds to sleep. 0 cancels the sleep timer."
        )
```

In `light()`, replace the existing `sleep` block:

```python
        if sleep is not None:
            if isinstance(sleep, int):
                # turns off sleep timer
                commands[COMMAND_LIGHT_SLEEP_TIMER] = SLEEP_TIMER_CANCEL
                if sleep > 0:
                    # count as number of seconds to sleep
                    sleep_till = datetime.now() + timedelta(seconds=sleep)
                    commands[COMMAND_LIGHT_SLEEP_TIMER] = int(sleep_till.timestamp())
            elif isinstance(sleep, datetime) and not (
                sleep < datetime.now() or sleep > (datetime.now() + timedelta(hours=24))
            ):
                commands[COMMAND_LIGHT_SLEEP_TIMER] = int(sleep.timestamp())
            else:
                raise ModernFormsInvalidSettingsError(
                    "The time to sleep till must be a datetime object that is not more"
                    + " then 24 hours into the future, or an interger for number of"
                    + " seconds to sleep. 0 cancels the sleep timer."
                )
```

with:

```python
        if sleep is not None:
            commands.update(
                self._sleep_command(
                    COMMAND_LIGHT_SLEEP_TIMER, COMMAND_LIGHT_TIMER, sleep
                )
            )
```

In `fan()`, replace the equivalent `sleep` block:

```python
        if sleep is not None:
            if isinstance(sleep, int):
                # turns off sleep timer
                commands[COMMAND_FAN_SLEEP_TIMER] = SLEEP_TIMER_CANCEL
                if sleep > 0:
                    # count as number of seconds to sleep
                    sleep_till = datetime.now() + timedelta(seconds=sleep)
                    commands[COMMAND_FAN_SLEEP_TIMER] = int(sleep_till.timestamp())
            elif isinstance(sleep, datetime) and not (
                sleep < datetime.now() or sleep > (datetime.now() + timedelta(hours=24))
            ):
                commands[COMMAND_FAN_SLEEP_TIMER] = int(sleep.timestamp())
            else:
                raise ModernFormsInvalidSettingsError(
                    "The time to sleep till must be a datetime object that is not more"
                    + " then 24 hours into the future, or an interger for number of"
                    + " seconds to sleep. 0 cancels the sleep timer."
                )
```

with:

```python
        if sleep is not None:
            commands.update(
                self._sleep_command(COMMAND_FAN_SLEEP_TIMER, COMMAND_FAN_TIMER, sleep)
            )
```

- [ ] **Step 5: Export the new constants in `aiomodernforms/__init__.py`**

Update the `.const` import block (lines 2-34) to add `COMMAND_FAN_TIMER` and `COMMAND_LIGHT_TIMER`, alphabetically:

```python
from .const import (  # noqa
    ADAPTIVE_LEARNING_OFF,
    ADAPTIVE_LEARNING_ON,
    AWAY_MODE_OFF,
    AWAY_MODE_ON,
    COMMAND_ADAPTIVE_LEARNING,
    COMMAND_AWAY_MODE,
    COMMAND_FAN_DIRECTION,
    COMMAND_FAN_POWER,
    COMMAND_FAN_SLEEP_TIMER,
    COMMAND_FAN_SPEED,
    COMMAND_FAN_TIMER,
    COMMAND_LIGHT_BRIGHTNESS,
    COMMAND_LIGHT_POWER,
    COMMAND_LIGHT_SLEEP_TIMER,
    COMMAND_LIGHT_TIMER,
    COMMAND_QUERY_STATUS,
    COMMAND_REBOOT,
    COMMAND_WIND,
    COMMAND_WIND_SPEED,
    FAN_DIRECTION_FORWARD,
    FAN_DIRECTION_REVERSE,
    FAN_POWER_OFF,
    FAN_POWER_ON,
    FAN_SPEED_HIGH_VALUE,
    FAN_SPEED_LOW_VALUE,
    LIGHT_BRIGHTNESS_HIGH_VALUE,
    LIGHT_BRIGHTNESS_LOW_VALUE,
    LIGHT_POWER_OFF,
    LIGHT_POWER_ON,
    WIND_OFF,
    WIND_ON,
    WIND_SPEED_HIGH_VALUE,
    WIND_SPEED_LOW_VALUE,
)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_aiomodernforms.py -v`
Expected: PASS — all tests, including the pre-existing epoch-based sleep tests (`test_light`, `test_light_sleep_datetime`, `test_light_sleep_int`, `test_light_sleep_clear`, `test_fan`, `test_fan_sleep_datetime`, `test_fan_sleep_int`, `test_fan_sleep_clear`, `test_invalid_setting`), since those all use `basic_response`/no-`update()` devices where `has_relative_timers()` is `False`.

- [ ] **Step 7: Commit**

```bash
git add aiomodernforms/const.py aiomodernforms/modernforms.py aiomodernforms/__init__.py tests/test_aiomodernforms.py
git commit -m "feat: send Gen 3 relative sleep timers (fanTimer/lightTimer) when supported"
```

---

### Task 6: New control methods (pairing, RF reset, factory reset, decommission, schedule)

**Files:**
- Modify: `aiomodernforms/const.py` (append)
- Modify: `aiomodernforms/modernforms.py:43-50` (exceptions import already present), `:353-360` region (insert new methods after `adaptive_learning`, before `reboot`)
- Modify: `aiomodernforms/__init__.py` (exports)
- Test: `tests/test_aiomodernforms.py`

**Interfaces:**
- Consumes: `State.rf_pair_mode_active`, `State.reset_rf_pair_list`, `State.factory_reset`, `State.decommission`, `State.schedule` (Task 2); `ModernFormsConnectionTimeoutError` (already imported).
- Produces: `ModernFormsDevice.enable_pairing_mode(active: bool = True)`, `.clear_paired_devices()`, `.factory_reset()`, `.decommission()`, `.set_schedule(data: str)`. Not consumed by any other task.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_aiomodernforms.py`'s `.const` import block:

```python
    STATE_RF_PAIR_MODE_ACTIVE,
    STATE_SCHEDULE,
```

Add tests, after `test_adaptive_learning` (currently ending at line 502, now shifted later by earlier tasks — insert in the same logical spot, right before `test_invalid_setting`):

```python
@pytest.mark.asyncio
async def test_enable_pairing_mode(aresponses):
    """Test enabling RF pairing mode."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async def evaluate_request(request):
        data = await request.json()
        assert aiomodernforms.COMMAND_RF_PAIR_MODE in data
        modified_response = basic_response.copy()
        modified_response[STATE_RF_PAIR_MODE_ACTIVE] = data[
            aiomodernforms.COMMAND_RF_PAIR_MODE
        ]
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(modified_response),
        )

    aresponses.add("fan.local", "/mf", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        await device.enable_pairing_mode()
        assert device.status.rf_pair_mode_active is True


@pytest.mark.asyncio
async def test_clear_paired_devices(aresponses):
    """Test clearing RF-paired devices."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async def evaluate_request(request):
        data = await request.json()
        assert data.get(aiomodernforms.COMMAND_RESET_RF_PAIR_LIST) is True
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(basic_response),
        )

    aresponses.add("fan.local", "/mf", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        await device.clear_paired_devices()


@pytest.mark.asyncio
async def test_factory_reset(aresponses):
    """Test how factory reset is handled, including the resulting disconnect."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        with patch(
            "aiomodernforms.ModernFormsDevice.request",
            side_effect=ModernFormsConnectionTimeoutError,
        ):
            await device.factory_reset()


@pytest.mark.asyncio
async def test_decommission(aresponses):
    """Test how decommission is handled, including the resulting disconnect."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        with patch(
            "aiomodernforms.ModernFormsDevice.request",
            side_effect=ModernFormsConnectionTimeoutError,
        ):
            await device.decommission()


@pytest.mark.asyncio
async def test_set_schedule(aresponses):
    """Test setting the schedule blob."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async def evaluate_request(request):
        data = await request.json()
        assert aiomodernforms.COMMAND_SCHEDULE in data
        modified_response = basic_response.copy()
        modified_response[STATE_SCHEDULE] = data[aiomodernforms.COMMAND_SCHEDULE]
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(modified_response),
        )

    aresponses.add("fan.local", "/mf", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        await device.set_schedule("AAAAAPwDAGSgBQAAnAkAZEAL")
        assert device.status.schedule == "AAAAAPwDAGSgBQAAnAkAZEAL"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_aiomodernforms.py::test_enable_pairing_mode tests/test_aiomodernforms.py::test_clear_paired_devices tests/test_aiomodernforms.py::test_factory_reset tests/test_aiomodernforms.py::test_decommission tests/test_aiomodernforms.py::test_set_schedule -v`
Expected: FAIL with `AttributeError: 'ModernFormsDevice' object has no attribute 'enable_pairing_mode'` (and similarly for the other four).

- [ ] **Step 3: Add the constants**

Append to `aiomodernforms/const.py` (after the `COMMAND_LIGHT_TIMER` line added in Task 5):

```python

COMMAND_RF_PAIR_MODE = "rfPairModeActive"
COMMAND_RESET_RF_PAIR_LIST = "resetRfPairList"
COMMAND_FACTORY_RESET = "factoryReset"
COMMAND_DECOMMISSION = "decommission"
COMMAND_SCHEDULE = "schedule"
```

- [ ] **Step 4: Add the methods in `aiomodernforms/modernforms.py`**

Update the `.const` import block (extended in Task 5) to add these five names, alphabetically:

```python
from .const import (
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
    COMMAND_QUERY_STATIC_DATA,
    COMMAND_QUERY_STATUS,
    COMMAND_REBOOT,
    COMMAND_RESET_RF_PAIR_LIST,
    COMMAND_RF_PAIR_MODE,
    COMMAND_SCHEDULE,
    COMMAND_WIND,
    COMMAND_WIND_SPEED,
    DEFAULT_API_ENDPOINT,
    DEFAULT_PORT,
    DEFAULT_TIMEOUT_SECS,
    FAN_DIRECTION_FORWARD,
    FAN_DIRECTION_REVERSE,
    FAN_SPEED_HIGH_VALUE,
    FAN_SPEED_LOW_VALUE,
    LIGHT_BRIGHTNESS_HIGH_VALUE,
    LIGHT_BRIGHTNESS_LOW_VALUE,
    SLEEP_TIMER_CANCEL,
    WIND_SPEED_HIGH_VALUE,
    WIND_SPEED_LOW_VALUE,
)
```

Add the new methods, after `adaptive_learning` and before `reboot`:

```python
    async def enable_pairing_mode(self, active: bool = True):
        """Toggle RF pairing mode, used to pair remotes or wall controls."""
        await self.request(commands={COMMAND_RF_PAIR_MODE: active})

    async def clear_paired_devices(self):
        """Clear all RF-paired devices (remotes, wall controls) from the fan."""
        await self.request(commands={COMMAND_RESET_RF_PAIR_LIST: True})

    async def factory_reset(self):
        """Factory reset the fan.

        Clears Wi-Fi credentials, decommissions the fan from the cloud,
        clears RF pairings, and returns the fan to AP mode.
        """
        try:
            await self.request(commands={COMMAND_FACTORY_RESET: True})
        except ModernFormsConnectionTimeoutError:
            # a successful factory reset drops the connection
            pass

    async def decommission(self):
        """Decommission the fan from the cloud and return it to AP mode."""
        try:
            await self.request(commands={COMMAND_DECOMMISSION: True})
        except ModernFormsConnectionTimeoutError:
            # a successful decommission drops the connection
            pass

    async def set_schedule(self, data: str):
        """Set the fan's base64-encoded schedule blob."""
        await self.request(commands={COMMAND_SCHEDULE: data})
```

- [ ] **Step 5: Export the new constants in `aiomodernforms/__init__.py`**

Add `COMMAND_DECOMMISSION`, `COMMAND_FACTORY_RESET`, `COMMAND_RESET_RF_PAIR_LIST`, `COMMAND_RF_PAIR_MODE`, and `COMMAND_SCHEDULE` to the `.const` import block, alphabetically (same pattern as Step 5 of Task 5).

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_aiomodernforms.py -v`
Expected: PASS — all tests.

- [ ] **Step 7: Commit**

```bash
git add aiomodernforms/const.py aiomodernforms/modernforms.py aiomodernforms/__init__.py tests/test_aiomodernforms.py
git commit -m "feat: add enable_pairing_mode, clear_paired_devices, factory_reset, decommission, and set_schedule"
```

---

### Task 7: `/config-read` support

**Files:**
- Modify: `aiomodernforms/const.py` (append)
- Modify: `aiomodernforms/models.py` (new `ConfigInfo` dataclass)
- Modify: `aiomodernforms/modernforms.py:89-92` (`__init__`), `:111-176` (`_request`), new `config()` method, imports
- Test: `tests/test_aiomodernforms.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `ConfigInfo` dataclass (`device_name`, `protocol`, `hardware_revision`, `firmware_version`, `rf_version`, `certificate_id`, `wifi_strength`, all `str`); `ModernFormsDevice.config() -> ConfigInfo`; `ModernFormsDevice._request(commands=None, path=DEFAULT_API_ENDPOINT)` (added `path` parameter — existing callers are unaffected since it defaults to the current behavior).

**Context:** `/config-read` is a separate endpoint from `/mf` with data unavailable anywhere else (hardware revision, RF library version, certificate ID, Wi-Fi signal strength). Its response shape differs by generation — Gen 1/2 uses keys `N`/`PO`/`HD`/`FW`/`RF`, Gen 3 uses `Name`/`Protocol`/`Firmware Rev`/`RF Rev` (no hardware-revision key at all). Even `Wi-Fi strength`'s *type* differs between the reference's own examples — Gen 1/2 shows it as a JSON number (`100`), Gen 3 shows it as a JSON string (`"-48"`) — so `ConfigInfo.wifi_strength` is a `str` with an explicit cast to handle both.

- [ ] **Step 1: Write the failing tests**

Add two new fixtures to `tests/test_aiomodernforms.py`, after `gen3_info`:

```python
gen1_2_config_response = {
    "T": "Current Configuration",
    "N": "WAC Windermier Fan(83DEF0)",
    "C": [{"N": "APPLICATION", "C": []}],
    "PO": "com.modernforms.fan",
    "HD": "WAC_WINDERMIER_REV_5",
    "FW": "01.03.0021",
    "RF": "wl0: Oct  6 2016 01:32:44 version 5.90.230.15 ",
    "certificateId": "6v6amxh5vbb2qjnkrp2av8i8r1tk1svzwn4ktrr9ds2ljz65ycfq1y026r6b77pt",
    "Wi-Fi strength": 100,
}

gen3_config_response = {
    "Name": "MF_Fan_98E5AC",
    "Protocol": "com.modernforms.fan",
    "Firmware Rev": "02.00.0003",
    "RF Rev": "v3.2.2",
    "certificateId": "6v6amxh5vbb2qjnkrp2av8i8r1tk1svzwn4ktrr9ds2ljz65ycfq1y026r6b77pt",
    "Wi-Fi strength": "-48",
}
```

Add tests, after `test_gen1_2_info_defaults`:

```python
@pytest.mark.asyncio
async def test_config_gen1_2(aresponses):
    """Test config() against a Gen 1/2-shaped /config-read response."""
    aresponses.add(
        "fan.local", "/config-read", "POST", response=gen1_2_config_response
    )

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        config = await device.config()
        assert config.device_name == "WAC Windermier Fan(83DEF0)"
        assert config.protocol == "com.modernforms.fan"
        assert config.hardware_revision == "WAC_WINDERMIER_REV_5"
        assert config.firmware_version == "01.03.0021"
        assert config.certificate_id.startswith("6v6amxh5vbb2qjnkrp2av8i8r1tk1svzwn4ktrr")
        assert config.wifi_strength == "100"


@pytest.mark.asyncio
async def test_config_gen3(aresponses):
    """Test config() against a Gen 3-shaped /config-read response."""
    aresponses.add(
        "fan.local", "/config-read", "POST", response=gen3_config_response
    )

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        config = await device.config()
        assert config.device_name == "MF_Fan_98E5AC"
        assert config.protocol == "com.modernforms.fan"
        assert config.hardware_revision == ""
        assert config.firmware_version == "02.00.0003"
        assert config.rf_version == "v3.2.2"
        assert config.wifi_strength == "-48"


@pytest.mark.asyncio
async def test_config_uses_config_read_path(aresponses):
    """Test that regular /mf traffic (update()) is unaffected by config()."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)
    aresponses.add(
        "fan.local", "/config-read", "POST", response=gen3_config_response
    )

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        config = await device.config()
        assert device.status.fan_on == basic_response["fanOn"]
        assert config.device_name == "MF_Fan_98E5AC"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_aiomodernforms.py::test_config_gen1_2 tests/test_aiomodernforms.py::test_config_gen3 tests/test_aiomodernforms.py::test_config_uses_config_read_path -v`
Expected: FAIL with `AttributeError: 'ModernFormsDevice' object has no attribute 'config'`.

- [ ] **Step 3: Add the constants**

Append to `aiomodernforms/const.py` (after the `COMMAND_SCHEDULE` line added in Task 6):

```python

CONFIG_READ_API_ENDPOINT = "config-read"

CONFIG_NAME_LEGACY = "N"
CONFIG_NAME = "Name"
CONFIG_PROTOCOL_LEGACY = "PO"
CONFIG_PROTOCOL = "Protocol"
CONFIG_HARDWARE_REVISION = "HD"
CONFIG_FIRMWARE_VERSION_LEGACY = "FW"
CONFIG_FIRMWARE_VERSION = "Firmware Rev"
CONFIG_RF_VERSION_LEGACY = "RF"
CONFIG_RF_VERSION = "RF Rev"
CONFIG_CERTIFICATE_ID = "certificateId"
CONFIG_WIFI_STRENGTH = "Wi-Fi strength"
```

- [ ] **Step 4: Add `ConfigInfo` in `aiomodernforms/models.py`**

Add the new names to the `.const` import block:

```python
from .const import (
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
    DEFAULT_WIND_SPEED,
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
    STATE_ADAPTIVE_LEARNING,
    STATE_AWAY_MODE,
    STATE_DECOMMISSION,
    STATE_FACTORY_RESET,
    STATE_FAN_DIRECTION,
    STATE_FAN_POWER,
    STATE_FAN_SLEEP_TIMER,
    STATE_FAN_SPEED,
    STATE_FAN_TIMER,
    STATE_LIGHT_BRIGHTNESS,
    STATE_LIGHT_POWER,
    STATE_LIGHT_SLEEP_TIMER,
    STATE_LIGHT_TIMER,
    STATE_RESET_RF_PAIR_LIST,
    STATE_RF_PAIR_MODE_ACTIVE,
    STATE_SCHEDULE,
    STATE_USER_DATA,
    STATE_WIND_POWER,
    STATE_WIND_SPEED,
)
```

Add the dataclass, after `Info` and before `State`:

```python
@dataclass
class ConfigInfo:
    """Config-read info about the Modern Forms device.

    Fetched from a separate `/config-read` endpoint whose response shape
    differs by fan generation. `wifi_strength` is kept as the raw string
    the device returned: Gen 1/2 fans report it as a percentage, Gen 3
    fans report it as a dBm value — callers must interpret it themselves.
    """

    device_name: str
    protocol: str
    hardware_revision: str
    firmware_version: str
    rf_version: str
    certificate_id: str
    wifi_strength: str

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> ConfigInfo:
        """Return ConfigInfo object from a Modern Forms /config-read response."""
        return ConfigInfo(
            device_name=data.get(CONFIG_NAME, data.get(CONFIG_NAME_LEGACY, "")),
            protocol=data.get(CONFIG_PROTOCOL, data.get(CONFIG_PROTOCOL_LEGACY, "")),
            hardware_revision=data.get(CONFIG_HARDWARE_REVISION, ""),
            firmware_version=data.get(
                CONFIG_FIRMWARE_VERSION, data.get(CONFIG_FIRMWARE_VERSION_LEGACY, "")
            ),
            rf_version=data.get(
                CONFIG_RF_VERSION, data.get(CONFIG_RF_VERSION_LEGACY, "")
            ),
            certificate_id=data.get(CONFIG_CERTIFICATE_ID, ""),
            wifi_strength=str(data.get(CONFIG_WIFI_STRENGTH, "")),
        )
```

- [ ] **Step 5: Refactor `_request()` and add `config()` in `aiomodernforms/modernforms.py`**

Update the `.models` import (currently `from .models import Device`) to:

```python
from .models import ConfigInfo, Device
```

Add `CONFIG_READ_API_ENDPOINT` to the `.const` import block (it sorts after the `COMMAND_*` names and before `DEFAULT_API_ENDPOINT`):

```python
from .const import (
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
    COMMAND_QUERY_STATIC_DATA,
    COMMAND_QUERY_STATUS,
    COMMAND_REBOOT,
    COMMAND_RESET_RF_PAIR_LIST,
    COMMAND_RF_PAIR_MODE,
    COMMAND_SCHEDULE,
    COMMAND_WIND,
    COMMAND_WIND_SPEED,
    CONFIG_READ_API_ENDPOINT,
    DEFAULT_API_ENDPOINT,
    DEFAULT_PORT,
    DEFAULT_TIMEOUT_SECS,
    FAN_DIRECTION_FORWARD,
    FAN_DIRECTION_REVERSE,
    FAN_SPEED_HIGH_VALUE,
    FAN_SPEED_LOW_VALUE,
    LIGHT_BRIGHTNESS_HIGH_VALUE,
    LIGHT_BRIGHTNESS_LOW_VALUE,
    SLEEP_TIMER_CANCEL,
    WIND_SPEED_HIGH_VALUE,
    WIND_SPEED_LOW_VALUE,
)
```

In `__init__`, remove the line that bakes the `mf` endpoint into `self._base_path`:

```python
        if self._base_path[-1] != "/":
            self._base_path += "/"

        self._base_path += DEFAULT_API_ENDPOINT
```

becomes:

```python
        if self._base_path[-1] != "/":
            self._base_path += "/"
```

In `_request`, add a `path` parameter and use it in the URL:

```python
    async def _request(
        self, commands: Optional[dict] = None, path: str = DEFAULT_API_ENDPOINT
    ) -> Any:
        """Handle a request to a Modern Forms Fan device."""
        scheme = "https" if self._tls else "http"
        url = URL.build(
            scheme=scheme,
            host=self._host,
            port=self._port,
            path=self._base_path + path,
        )
```

(the rest of `_request` is unchanged).

Add `config()`, after the `info` property and before `has_breeze_mode`:

```python
    async def config(self) -> ConfigInfo:
        """Retrieve config-read data: hardware revision, RF library version,
        certificate ID, and current Wi-Fi signal strength."""
        config_data = await self._request(commands={}, path=CONFIG_READ_API_ENDPOINT)
        return ConfigInfo.from_dict(config_data)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_aiomodernforms.py -v`
Expected: PASS — all tests, including every test from Tasks 1-6 (confirming the `_request`/`__init__` refactor didn't change `/mf` behavior).

- [ ] **Step 7: Commit**

```bash
git add aiomodernforms/const.py aiomodernforms/models.py aiomodernforms/modernforms.py tests/test_aiomodernforms.py
git commit -m "feat: add /config-read support via ModernFormsDevice.config()"
```

---

### Task 8: Full regression pass

**Files:** none (verification only).

**Interfaces:** none — this task only runs the existing tooling.

- [ ] **Step 1: Run the full test suite with coverage**

Run: `pytest tests/ -v --cov=aiomodernforms --cov-report=term-missing`
Expected: PASS — every test across all seven prior tasks, plus all pre-existing tests. Review the coverage report for any of the new fields/methods left unexercised and add a test if so.

- [ ] **Step 2: Run the full pre-commit hook suite**

Run: `pre-commit run --all-files`
Expected: PASS (black, isort, autopep8, pylint, mypy, flake8, pyupgrade, and the misc hygiene hooks). If any hook reformats files, `git add -u` the result.

- [ ] **Step 3: Commit any formatting fixes, if needed**

```bash
git add -u
git commit -m "chore: apply pre-commit formatting fixes"
```

(Skip this step entirely if Step 2 made no changes.)
