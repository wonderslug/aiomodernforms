# Light Brightness-Before-On Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix [issue #99](https://github.com/wonderslug/aiomodernforms/issues/99) — turning a light on with a new brightness in one `light()` call causes a visible flash at the old brightness, because both fields are sent in a single HTTP request.

**Architecture:** `ModernFormsDevice.light()` in `aiomodernforms/modernforms.py` currently builds one combined `commands` dict for `brightness`, `on`, and `sleep`, and sends it in a single `self.request()` call. This plan changes `light()` so that when `brightness is not None and on is True`, it sends two sequential requests — brightness first, then `on` (+ `sleep`) — instead of one. All other argument combinations keep the existing single-request behavior.

**Tech Stack:** Python 3.11, `aiohttp`, `pytest` + `pytest-asyncio` + `aresponses` for HTTP-mocked tests.

## Global Constraints

- Validation of `brightness` and `on` must happen before any HTTP request is sent (no partial device state on invalid input) — spec's "Design" step 1.
- Only the `brightness is not None and on is True` combination gets split into two requests; every other combination (brightness alone, on alone, `on=False` + brightness) stays a single combined request — spec's "Scope".
- `light()` continues to return nothing — callers read `device.status` afterward, matching its current signature.
- No new imports are needed: `COMMAND_LIGHT_BRIGHTNESS`, `COMMAND_LIGHT_POWER`, `COMMAND_LIGHT_SLEEP_TIMER`, `COMMAND_LIGHT_TIMER`, `LIGHT_BRIGHTNESS_LOW_VALUE`, `LIGHT_BRIGHTNESS_HIGH_VALUE`, and `ModernFormsInvalidSettingsError` are already imported in `aiomodernforms/modernforms.py`.

---

### Task 1: Split brightness-then-on requests in `light()`

**Files:**
- Modify: `aiomodernforms/modernforms.py:277-315` (the `light()` method)
- Test: `tests/test_aiomodernforms.py:336-375` (replace existing `test_light`), plus three new tests added directly after it

**Interfaces:**
- Consumes: `ModernFormsDevice.request(commands: dict | None)` (existing, unchanged) and `ModernFormsDevice._sleep_command(epoch_command, relative_command, sleep)` (existing, unchanged) — both already used by the current `light()` implementation.
- Produces: `ModernFormsDevice.light(*, brightness: int | None = None, on: bool | None = None, sleep: int | datetime | None = None) -> None` — same signature and return type as before; only the internal request pattern changes for the `brightness` + `on=True` combination.

- [ ] **Step 1: Replace `test_light` with a version asserting the two-request split**

In `tests/test_aiomodernforms.py`, replace the entire existing `test_light` function (lines 336-375, from `@pytest.mark.asyncio` through the final assert) with:

```python
@pytest.mark.asyncio
async def test_light(aresponses):
    """Test that turning on with a brightness sends brightness before on."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async def evaluate_brightness_request(request):
        data = await request.json()
        assert aiomodernforms.COMMAND_LIGHT_BRIGHTNESS in data
        assert aiomodernforms.COMMAND_LIGHT_POWER not in data
        assert aiomodernforms.COMMAND_LIGHT_SLEEP_TIMER not in data
        modified_response = basic_response.copy()
        modified_response[STATE_LIGHT_BRIGHTNESS] = data[
            aiomodernforms.COMMAND_LIGHT_BRIGHTNESS
        ]
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(modified_response),
        )

    async def evaluate_on_request(request):
        data = await request.json()
        assert aiomodernforms.COMMAND_LIGHT_POWER in data
        assert aiomodernforms.COMMAND_LIGHT_SLEEP_TIMER in data
        assert aiomodernforms.COMMAND_LIGHT_BRIGHTNESS not in data
        modified_response = basic_response.copy()
        modified_response[
            STATE_LIGHT_BRIGHTNESS
        ] = aiomodernforms.LIGHT_BRIGHTNESS_HIGH_VALUE
        modified_response[STATE_LIGHT_POWER] = data[aiomodernforms.COMMAND_LIGHT_POWER]
        modified_response[STATE_LIGHT_SLEEP_TIMER] = data[
            aiomodernforms.COMMAND_LIGHT_SLEEP_TIMER
        ]
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(modified_response),
        )

    aresponses.add("fan.local", "/mf", "POST", response=evaluate_brightness_request)
    aresponses.add("fan.local", "/mf", "POST", response=evaluate_on_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        sleep_time = datetime.now() + timedelta(minutes=2)
        await device.light(
            on=aiomodernforms.LIGHT_POWER_ON,
            brightness=aiomodernforms.LIGHT_BRIGHTNESS_HIGH_VALUE,
            sleep=sleep_time,
        )
        assert device.status.light_on == aiomodernforms.LIGHT_POWER_ON
        assert (
            device.status.light_brightness == aiomodernforms.LIGHT_BRIGHTNESS_HIGH_VALUE
        )
        assert device.status.light_sleep_timer == int(sleep_time.timestamp())
```

Note: `aresponses` serves queued responses in order — two for `device.update()`, then one each for the brightness request and the on+sleep request. If `light()` still sends only one request, the third `aresponses.add` response (`evaluate_brightness_request`) will be consumed by that single request, its assertions will fail (since a combined request contains `lightOn`, which `evaluate_brightness_request` asserts is absent), producing the expected failure.

- [ ] **Step 2: Add three regression tests immediately after `test_light`**

Insert these three new test functions directly after the `test_light` function you just replaced (before `test_light_sleep_datetime`):

```python
@pytest.mark.asyncio
async def test_light_off_with_brightness_single_request(aresponses):
    """Test that turning off with a brightness change stays a single request."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async def evaluate_request(request):
        data = await request.json()
        assert aiomodernforms.COMMAND_LIGHT_POWER in data
        assert aiomodernforms.COMMAND_LIGHT_BRIGHTNESS in data
        modified_response = basic_response.copy()
        modified_response[STATE_LIGHT_POWER] = data[aiomodernforms.COMMAND_LIGHT_POWER]
        modified_response[STATE_LIGHT_BRIGHTNESS] = data[
            aiomodernforms.COMMAND_LIGHT_BRIGHTNESS
        ]
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(modified_response),
        )

    aresponses.add("fan.local", "/mf", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        await device.light(
            on=aiomodernforms.LIGHT_POWER_OFF,
            brightness=aiomodernforms.LIGHT_BRIGHTNESS_LOW_VALUE,
        )
        assert device.status.light_on == aiomodernforms.LIGHT_POWER_OFF
        assert (
            device.status.light_brightness == aiomodernforms.LIGHT_BRIGHTNESS_LOW_VALUE
        )


@pytest.mark.asyncio
async def test_light_brightness_only_single_request(aresponses):
    """Test that changing only brightness stays a single request."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async def evaluate_request(request):
        data = await request.json()
        assert aiomodernforms.COMMAND_LIGHT_BRIGHTNESS in data
        assert aiomodernforms.COMMAND_LIGHT_POWER not in data
        modified_response = basic_response.copy()
        modified_response[STATE_LIGHT_BRIGHTNESS] = data[
            aiomodernforms.COMMAND_LIGHT_BRIGHTNESS
        ]
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(modified_response),
        )

    aresponses.add("fan.local", "/mf", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        await device.light(brightness=aiomodernforms.LIGHT_BRIGHTNESS_HIGH_VALUE)
        assert (
            device.status.light_brightness == aiomodernforms.LIGHT_BRIGHTNESS_HIGH_VALUE
        )


@pytest.mark.asyncio
async def test_light_on_only_single_request(aresponses):
    """Test that turning on without a brightness stays a single request."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async def evaluate_request(request):
        data = await request.json()
        assert aiomodernforms.COMMAND_LIGHT_POWER in data
        assert aiomodernforms.COMMAND_LIGHT_BRIGHTNESS not in data
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
        await device.light(on=aiomodernforms.LIGHT_POWER_ON)
        assert device.status.light_on == aiomodernforms.LIGHT_POWER_ON
```

These three exercise argument combinations that are *not* changing behavior. Each registers exactly one `aresponses.add` for the `light()` call itself — if `light()` ever sent two requests for these combinations, the second request would have no queued response left and the test would fail. They act as regression guards against over-splitting.

- [ ] **Step 3: Run the light tests and confirm the expected mixed result**

Run: `.venv/bin/pytest tests/test_aiomodernforms.py -k light -v`

Expected: `test_light` **FAILS** (current `light()` still sends a single combined request, so `evaluate_brightness_request`'s `assert aiomodernforms.COMMAND_LIGHT_POWER not in data` fails). The three new regression tests **PASS** (their argument combinations already produce single requests under the current implementation, so they're unaffected by this step and will continue to pass after Step 4).

- [ ] **Step 4: Implement the brightness-before-on split in `light()`**

In `aiomodernforms/modernforms.py`, replace the `light()` method (lines 277-315) with:

```python
    async def light(
        self,
        *,
        brightness: int | None = None,
        on: bool | None = None,
        sleep: int | datetime | None = None,
    ):
        """Change Fans Light state."""
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
        if sleep is not None:
            sleep_commands = self._sleep_command(
                COMMAND_LIGHT_SLEEP_TIMER, COMMAND_LIGHT_TIMER, sleep
            )

        if brightness is not None and on is True:
            # Setting brightness and turning on in a single request makes the
            # fan briefly show the previous brightness before jumping to the
            # new one. Sending brightness first avoids the flash.
            await self.request(commands={COMMAND_LIGHT_BRIGHTNESS: brightness})
            await self.request(commands={COMMAND_LIGHT_POWER: on, **sleep_commands})
            return

        commands: dict[str, bool | int] = {}
        if brightness is not None:
            commands[COMMAND_LIGHT_BRIGHTNESS] = brightness
        if on is not None:
            commands[COMMAND_LIGHT_POWER] = on
        commands.update(sleep_commands)

        await self.request(commands=commands)
```

This preserves the original validation order (brightness, then `on`, then `sleep` via `_sleep_command`) so `test_invalid_setting` (which checks each raises `ModernFormsInvalidSettingsError` with zero HTTP calls) keeps passing unchanged.

- [ ] **Step 5: Run the light tests again and confirm all pass**

Run: `.venv/bin/pytest tests/test_aiomodernforms.py -k light -v`

Expected: **PASS** — all light tests green, including the rewritten `test_light` and the three new regression tests.

- [ ] **Step 6: Run the full test suite**

Run: `.venv/bin/pytest tests/test_aiomodernforms.py -v`

Expected: **PASS** — no other test touches `light()`'s internals, but this confirms nothing else regressed (e.g. `test_invalid_setting`, which exercises `light()` validation paths).

- [ ] **Step 7: Run pre-commit checks (matches CI)**

Run: `pre-commit run --all-files --show-diff-on-failure`

Expected: **PASS**. This repo's CI (`.github/workflows/ci.yml`) runs `pre-commit run --all-files` (black, flake8, isort, mypy, pylint, etc.) before the test job; running it locally now catches formatting/lint issues before commit. If black reformats the new code, re-run the test suite (Step 6) to confirm nothing broke.

- [ ] **Step 8: Commit**

```bash
git add aiomodernforms/modernforms.py tests/test_aiomodernforms.py
git commit -m "Send light brightness before turning on to avoid a flash (#99)"
```
