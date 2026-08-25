# Home Assistant `modern_forms` integration — Gen4 support

> Self-contained prompt/spec for the work session that adds Gen4 support to
> the `modern_forms` Home Assistant integration
> (`wonderslug/home-assistant-core`, branch `modern-forms-breeze-mode`).
> Written to be handed to a fresh agent (or read cold by a human) with no
> other context — it does not assume you've seen the `aiomodernforms`
> conversation this came out of.

## Background

`aiomodernforms` (the Python client this integration uses,
`homeassistant/components/modern_forms/manifest.json` currently pins it via
`requirements: ["aiomodernforms==0.2.0"]`) has added support for Modern
Forms/WAC "Gen4" fans on top of its existing Gen 1/2/3 support, shipping as
**`aiomodernforms` 0.3.0**. Gen4 fans speak a different wire protocol
(`/device` + `/fixture`, with an arbitrary number of
independently-addressable light fixtures) instead of Gen 1/2/3's flat `/mf`
shadow endpoint (exactly one light). The library update keeps its existing
asyncio API stable and generation-agnostic — this integration talks to
`ModernFormsDevice`/`Device`/`State`/`Info` exactly as before; Gen4-ness
shows up as new data and new capability flags, not a new code path to
special-case.

Bump the `requirements` pin in `manifest.json` to
`["aiomodernforms==0.3.0"]` before starting — everything below assumes that
version. **Two real Gen4 fans have already been tested against the library
by a third party** (a Radiant 56", model `2603-56`, with a downlight +
uplight) — the wire-level behavior below is confirmed against real
hardware, not just the PDF spec.

## What the library now gives you

All of this is on `aiomodernforms.models.Device` (what `coordinator.data`
already is in `coordinator.py`) and its `.info`/`.state` — no new import
paths beyond what's already used, except `Generation`/`Light` if you want
them (`from aiomodernforms.models import Generation, Light`).

**`Device.info` (all generations, including Gen4 now):**
- `mac_address` — the fan's WiFi station MAC. **This is what makes Gen4 fans
  addable at all** — see "Critical: identity" below.
- `light_type` — non-empty string when the fan has at least one light
  fixture, `""` when it doesn't. Same truthy-check contract as legacy;
  Gen4 now populates it correctly.
- `fan_type` — a real model string for Gen4 (e.g. `"2603-56"`), where it was
  previously blank.
- `device_name`, `firmware_version`, `main_mcu_firmware_version`, `owner` —
  unchanged, already populated for Gen4.

**`Device.state` (unchanged shape, all generations):**
- The existing flat fields (`fan_on`, `fan_speed`, `fan_direction`, `wind`,
  `wind_speed`, `away_mode_enabled`, `light_on`, `light_brightness`,
  `light_color_temp_kelvin`, ...) all still work exactly as before, for every
  generation. For Gen4, the light fields mirror the **first** light fixture.
- **New: `state.light_fixtures: list[Light]`** — populated for *every*
  generation now, not just Gen4. For Gen 1/2/3 it's always a single
  synthetic entry (`address=None`, `fixture_type=None`) mirroring the flat
  fields above. For Gen4 it's one real entry per light fixture the device
  actually reports, each with:
  ```python
  @dataclass
  class Light:
      address: int | None  # None only for the legacy synthetic entry
      fixture_type: int | None
      name: str  # user-assigned name, e.g. "Uplight"
      on: bool
      brightness: int  # 1-100, same scale as state.light_brightness
      color_temp_kelvin: int | None
      min_color_temp_kelvin: int | None
      max_color_temp_kelvin: int | None
  ```

**Capability flags on `Device`** (already the pattern `number.py` uses for
`has_wind()` — extend this pattern, don't check `generation` directly):
- `has_wind()` — unchanged.
- `has_sleep_timer()` — **new**, `False` on Gen4 (no sleep timer concept at
  all there), `True` otherwise.
- `has_adaptive_learning()` — **new**, `False` on Gen4, `True` otherwise.
- `has_identify()` — **new**, `True` only on Gen4. No Gen 1/2/3 equivalent.
- `has_relative_timers()` — unchanged (Gen3-only quirk, already handled).

**Control methods** (`ModernFormsDevice`, i.e. `coordinator.modern_forms`):
- `fan(...)` — unchanged signature, gained `identify: bool | None = None`
  (Gen4 only; silently ignored elsewhere, per the library's established
  "silent no-op on unsupported generations" convention — no
  generation-check needed on your side).
- `light(...)` — unchanged, always targets the *first* light fixture
  (`state.light_fixtures[0]`). Gained `color_temp_kelvin: int | None` and
  `identify: bool | None`.
- **New: `light_fixture(address, *, brightness=None, on=None, sleep=None,
  color_temp_kelvin=None, identify=None)`** — targets one specific fixture
  by `address` (from `Light.address`). Pass `address=None` to target the
  legacy synthetic entry (routes through `/mf`, same as calling `light()`).
  This is what you'll call for every fixture in `state.light_fixtures` when
  building per-fixture entities.
- `away(away: bool)`, `adaptive_learning(...)`, `reboot()`,
  `factory_reset()` — unchanged, all already generation-aware internally.
- `decommission()`, `enable_pairing_mode()`, `clear_paired_devices()`,
  `set_schedule(...)` — raise `aiomodernforms.ModernFormsNotSupportedError`
  on Gen4 (no equivalent exists). Already wrapped by
  `modernforms_exception_handler` in `__init__.py`, which doesn't currently
  special-case this exception — decide whether it needs a distinct
  translation key, or whether letting it fall through as a generic
  `ModernFormsError` is fine (none of today's entities call these on a path
  a user can reach without already knowing the fan's generation).

## Critical: identity (must fix before anything else works)

Fetched and read the actual current integration code
(`entity.py`, `config_flow.py`, `light.py`, `fan.py`, `switch.py`,
`number.py`, `binary_sensor.py`, `sensor.py`) to confirm this rather than
assume it — here's what's actually there today:

- **`config_flow.py:214,219`**: `self.mac = device.info.mac_address` →
  `await self.async_set_unique_id(self.mac)`. This is the config entry's
  identity — it's what stops duplicate entries and matches zeroconf
  discovery to an existing entry.
- **`entity.py:117-124`**: `DeviceInfo(identifiers={(DOMAIN, mac_address)},
  connections={(CONNECTION_NETWORK_MAC, mac_address)}, ..., model=fan_type)`
  — the device registry identity.
- **Every entity's unique_id is built from `info.mac_address`**: light is
  literally `f"{mac_address}"` (bare, no suffix), fan the same, switches/
  sensors/number are `f"{mac_address}_{key}"`.

None of this needs to change — it already reads `info.mac_address`/
`info.fan_type` generically, for any generation. It was simply broken for
Gen4 because the library left those fields blank; that's now fixed. **Bump
the `aiomodernforms` requirement and this identity plumbing starts working
for Gen4 with zero code changes.** Confirm this in practice (config flow
successfully adds a Gen4 fan, shows the right model, doesn't collide with a
second one) before moving on to the parity/functionality work below.

## Parity work: per-fixture light entities

`light.py` currently creates exactly **one** hardcoded
`ModernFormsLightEntity` per config entry (see `async_setup_entry`) with
unique_id `f"{mac_address}"`. It reads `state.light_on`/
`state.light_brightness` and always calls the flat `light()` method. This
already works, unchanged, for Gen 1/2/3 and for a single-light Gen4 fan
(since those fields mirror `light_fixtures[0]`) — but a multi-light Gen4 fan
(e.g. the tested Radiant 56", uplight + downlight) would only ever get one
HA light entity, silently hiding the second fixture.

**Rework `light.py` to loop `coordinator.data.state.light_fixtures`,
creating one entity per `Light`.** The hard constraint is backward
compatibility — this must not change behavior for any existing Gen 1/2/3
install:

```python
for light in coordinator.data.state.light_fixtures:
    entities.append(
        ModernFormsLightEntity(
            entry_id=..., coordinator=..., light_address=light.address
        )
    )
```

- **Unique ID branches on `light.address`:**
  - `address is None` (the Gen 1/2/3 synthetic entry, and single-light Gen4
    fans if you choose to keep them on the legacy path) → unique_id must
    stay **exactly** `f"{mac_address}"`, matching today's behavior bit for
    bit. Changing this orphans every existing entity in every production
    install.
  - `address is not None` (real Gen4 fixture) → new suffixed id, e.g.
    `f"{mac_address}_{address}"`.
- **Control calls branch the same way:** the `address is None` entity keeps
  calling `light(...)` unchanged; every `address is not None` entity calls
  `light_fixture(address, ...)` instead.
- **Naming:** use `light.name` (e.g. `"Uplight"`/`"Downlight"`) for real
  Gen4 fixtures. Leave the legacy entity's naming exactly as-is (it
  currently has no explicit name and inherits the device name via
  `_attr_has_entity_name = True` — don't add one, that would rename
  existing entities).
- **Setup gating stays `if not coordinator.data.info.light_type: return`**
  — unchanged, now correctly non-empty for Gen4 fans that have lights.

## New functionality (not just parity)

These aren't required to match legacy behavior — Gen4 genuinely exposes
more than Gen 1/2/3 ever did. Consider each on its own merits:

1. **Color temperature control on light entities.** `light.py` currently
   only supports `ColorMode.BRIGHTNESS`. Gen4 light fixtures report real
   `min_color_temp_kelvin`/`max_color_temp_kelvin` (confirmed on real
   hardware: 2700-5000K on the tested Radiant 56") and `color_temp_kelvin`
   is settable via `light_fixture(address, color_temp_kelvin=...)` /
   `light(color_temp_kelvin=...)`. Add `ColorMode.COLOR_TEMP` to a light
   entity's supported color modes when `light.min_color_temp_kelvin` and
   `light.max_color_temp_kelvin` are both set, using HA's native-Kelvin
   `LightEntity` attrs (`color_temp_kelvin`, `min_color_temp_kelvin`,
   `max_color_temp_kelvin`) — no unit conversion needed, they map straight
   across from the `Light` dataclass.

2. **Identify/"flash" button.** `has_identify()` is Gen4-only and unused by
   the integration today. Both `fan(identify=True)` and
   `light_fixture(address, identify=True)` /
   `light(identify=True)` trigger the device's physical identify signal
   (`findme` on the wire). With multiple light entities per fan now
   possible, a per-entity (or per-device) "Identify" button would help a
   user confirm which physical fixture an HA entity corresponds to during
   setup. Candidate: new `button.py` platform, one `ModernFormsIdentifyFan`
   entity gated on `coordinator.data.has_identify()`, calling
   `coordinator.modern_forms.fan(identify=True)`; optionally one per light
   fixture too, calling `light_fixture(address, identify=True)`.

3. **Capability-gate the entities that assume Gen 1/2/3.** While auditing
   the existing platforms for this work, two gaps surfaced that aren't
   Gen4-specific bugs so much as the integration never having had a reason
   to check capability before:
   - `switch.py`: `ModernFormsAdaptiveLearningSwitch` is created
     unconditionally. Gate it on `coordinator.data.has_adaptive_learning()`
     (mirrors the existing `has_wind()` gate in `number.py`).
   - `binary_sensor.py` / `sensor.py`: the fan sleep-timer entities
     (`ModernFormsFanSleepTimerActive`,
     `ModernFormsFanTimerRemainingTimeSensor`) are created unconditionally
     regardless of generation; the light sleep-timer entities are gated on
     `info.light_type` alone. Gate all four on
     `coordinator.data.has_sleep_timer()` (in addition to — not instead of —
     the light ones' existing `light_type` check). Without this, a Gen4 fan
     gets sleep-timer entities that are permanently meaningless.
   This is worth doing regardless of whether items 1-2 are pursued — it's
   correctness work that also makes the integration more resilient to
   whatever a hypothetical future generation looks like, matching the
   library's own "capability flags, not generation checks" design.

## Testing without hardware

`aiomodernforms` ships a Gen4 mock server for exactly this purpose:

```bash
python -m mock_fan --generation gen4 --lights 2 --port 8080
```

This reports a mock MAC (`AA:BB:CC:00:11:22`), a mock model (`"2603-56"`),
and two independently-controllable light fixtures — enough to exercise the
config flow's unique_id path, per-fixture light entity creation, and
color-temp control end-to-end before testing against real hardware. `git
clone` `wonderslug/aiomodernforms`, branch `worktree-gen4-fan-support` (or
whatever it's merged to by the time you read this), and point
`config_flow`'s user-flow host field at `127.0.0.1:8080`.

## Suggested order of work

1. Bump `manifest.json`'s `requirements` pin to `aiomodernforms==0.3.0`,
   confirm config flow + basic fan/away/breeze entities work against a
   Gen4 mock fan with zero other code changes (validates the identity fix
   landed correctly).
2. Rework `light.py` for per-fixture entities (parity — the only real
   functional gap for existing users with multi-light Gen4 fans).
3. Capability-gate `switch.py`/`binary_sensor.py`/`sensor.py` (small,
   low-risk correctness fixes).
4. Color temperature support on light entities (new functionality).
5. Identify button (new functionality, smallest and most optional of the
   four).

Test each stage against `mock_fan --generation gen1_2` (or `gen3`) as well
as `gen4` — the whole point of this design is that legacy behavior doesn't
move.
