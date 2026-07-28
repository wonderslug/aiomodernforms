# Light: Set Brightness Before Turning On

## Problem

[Issue #99](https://github.com/wonderslug/aiomodernforms/issues/99): calling `ModernFormsDevice.light(brightness=X, on=True)` sends a single HTTP request containing both `lightBrightness` and `lightOn` in one JSON payload. The fan's firmware appears to apply `lightOn` using the *previous* brightness value momentarily, then jump to the newly commanded brightness — producing a brief visible flash at the old brightness when a light is turned on with a new brightness in the same call.

The issue proposes the fix directly: send the brightness command first, then send the "on" command as a separate call.

## Scope

Only the case that actually flashes: `light()` called with both `brightness is not None` and `on is True`. All other combinations (brightness alone, on alone, `on=False` + brightness, brightness/on with `on` omitted) keep today's single combined-request behavior — there's no flash to avoid in those cases, and splitting them would just add unnecessary round-trips or change behavior with no benefit (confirmed with the user during design).

## Design

Modify `ModernFormsDevice.light()` in `aiomodernforms/modernforms.py`:

1. Validate `brightness` and `on` exactly as today (range check, boolean check) — **before** any request is sent, so invalid input never causes a partially-applied device state.
2. Compute the `sleep` command dict (if `sleep` is given) via the existing `_sleep_command()` helper, same as today.
3. If `brightness is not None and on is True`:
   - Send request 1: `{COMMAND_LIGHT_BRIGHTNESS: brightness}` only.
   - Send request 2: `{COMMAND_LIGHT_POWER: True, **sleep_commands}`.
4. Otherwise: build the single combined `commands` dict exactly as today (brightness, on, sleep merged) and send one request.

Each `self.request()` call already updates `self._device` from the response, so device state stays consistent across the two calls with no extra bookkeeping. `light()` continues to return nothing, matching its current signature — callers read `device.status` afterward.

## Error Handling

No new error paths are introduced. If request 1 (brightness) in the split case raises (`ModernFormsConnectionError`, `ModernFormsConnectionTimeoutError`, etc.), request 2 is never sent, leaving brightness set but the light not yet turned on. This is an inherent risk of any multi-step network operation and is not made worse by this change; there's no reasonable way to make two separate HTTP calls atomic, and no atomic combined API exists on the device.

## Testing

- Update the existing `test_light` test (currently asserts a single POST carrying brightness+on+sleep together) to reflect the new two-request behavior for the `on=True` + `brightness` case: request 1 carries only brightness, request 2 carries `on` + `sleep`.
- Add a regression test confirming `brightness` + `on=False` together still produce a single combined request (unchanged behavior).
- Add regression tests confirming brightness-only and on-only calls remain single requests (unchanged behavior).
