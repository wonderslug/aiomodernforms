# Mock Fan Light Toggle — Design

## Background

The `mock_fan` service (see `2026-07-28-mock-fan-service-design.md`) emulates a real Modern Forms fan over HTTP, currently always including light control (`lightOn`, `lightBrightness`, and the profile-appropriate sleep/timer field) in the dynamic shadow, with no way to turn it off. Real Modern Forms/WAC fans are sold in both light-kit and fan-only variants, the same way some are sold with and without breeze/wind support — a capability the mock already models via `--breeze`. There is currently no way to simulate a fan-only unit for testing how a Home Assistant integration behaves when no light entity should exist.

## Goal

Add a `--light`/`--no-light` toggle to the mock fan, analogous to `--breeze`, controlling whether light-related fields are present in the dynamic shadow at all. Unlike breeze, light defaults to **on** (most fans in the field have a light kit), so the CLI needs a different shape: `argparse.BooleanOptionalAction` rather than breeze's plain `store_true`.

## Design

### 1. State (`mock_fan/state.py`)

`FanState.__init__` gains a `light: bool` parameter alongside the existing `breeze: bool`, stored the same way (`self._light`) and threaded into both `_initial_shadow()` and `_build_validators()`, which each gain a matching `light: bool` parameter.

When `light=True` (default), behavior is byte-for-byte identical to today: `lightOn`, `lightBrightness`, and the profile-appropriate timer field (`lightSleepTimer` for `uses_relative_timers=False` profiles, `lightTimer` for `uses_relative_timers=True` profiles) are present in the initial shadow and have validators in `_build_validators()`.

When `light=False`, all three keys are omitted from `_initial_shadow()`'s return value, and none of the three get an entry in `_build_validators()`'s returned map. Since `apply_commands()` already silently ignores any command key with no validator entry, a `lightOn`/`lightBrightness`/timer command against a no-light fan is a no-op — exactly the same treatment `wind`/`windSpeed` already receive when `breeze=False`. `reset()` continues to call `_initial_shadow()` with the stored `self._light` flag, so a `factory_reset()`/`decommission()` on a no-light fan stays no-light afterward.

Nothing else in `state.py` changes: `snapshot()` and `apply_commands()`'s bodies are untouched, since the light/breeze gating lives entirely in what keys exist in the shadow and validator dicts, not in new conditional logic inside those methods.

### 2. Server (`mock_fan/server.py`)

`create_app()` gains `light: bool = True`, positioned alongside the existing `breeze` and `resume_delay_secs` parameters, passed straight through to `FanState`'s constructor via `MockFan`. No other server logic changes — `/mf` and `/config-read` handling is entirely agnostic to which shadow keys exist.

### 3. CLI (`mock_fan/__main__.py`)

A new argument:

```python
parser.add_argument(
    "--light",
    action=argparse.BooleanOptionalAction,
    default=True,
    help="Enable light control (default: enabled). Use --no-light to simulate a fan-only unit.",
)
```

This single declaration produces both `--light` and `--no-light` on the command line, defaulting `args.light` to `True` when neither is passed. `main()` passes `light=args.light` to `create_app()`, and the startup confirmation line gains a `light=on|off` segment:

```
Mock fan listening on 0.0.0.0:8080 (generation=gen3, breeze=off, light=on)
```

### 4. Unaffected

- `mock_fan/generations.py`: the static `lightType` field in each `GenerationProfile` is untouched — it reflects the fan model's static info response, not the dynamic light-control capability this flag toggles. A no-light mock fan still reports whatever `lightType` its profile already defines, exactly as a real fan-only unit's static info is unaffected by this flag today.
- `POST /config-read`: has no light-related fields today (same as breeze), so nothing changes there.
- The Makefile's `mock-fan` target and README already pass through arbitrary flags implicitly via the documented `python -m mock_fan` invocation; no changes needed there since `--light`/`--no-light` follows the same pattern `--breeze` already established.

### 5. Testing

- `tests/mock_fan/test_state.py`: mirror the existing breeze tests — `light=False` omits `lightOn`/`lightBrightness`/the timer field from `snapshot()`'s initial state; a `lightOn`/`lightBrightness` command against a `light=False` state is silently ignored (key absent from the resulting snapshot); `light=True` (including the implicit default via existing call sites) is unchanged, so no existing test needs modification.
- `tests/mock_fan/test_server.py`: one integration test creating `create_app(GEN1_2, breeze=False, light=False)` and confirming, via the real `aiomodernforms.ModernFormsDevice` client, that `device.light(on=True)` does not change `device.status.light_on` after a follow-up `update()` (the command is a no-op on the wire); one confirming the default (`light` omitted from `create_app()`) preserves today's behavior.
- `tests/mock_fan/test_cli.py`: two new assertions — `--generation gen1_2` alone yields `args.light is True`; `--generation gen1_2 --no-light` yields `args.light is False`.

## Out of scope

- Changing `mock_fan/generations.py`'s static `lightType` field based on the light flag (confirmed with the user: left as-is).
- Any change to the real `aiomodernforms` client library — it already handles a fan whose state response omits `lightOn`/`lightBrightness` the same way it handles one omitting `wind`/`windSpeed`: via `dict.get()` defaults. No `has_light()` capability method exists on `Device` today (unlike `has_wind()`), and adding one is a client-library change outside this mock service's scope.
