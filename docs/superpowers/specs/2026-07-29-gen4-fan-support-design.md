# Gen4 Fan Support — Design

## Background

`WAC_IoT_Unified_REST_Interface_3rd_Party_V1.91.pdf` (a newer vendor doc than
`WAC_Modern_Forms_3rd_Party_API_Reference.pdf`) documents a "Gen4 Fan" that speaks an
entirely different wire protocol from the Gen 1/2/3 fans this library already
supports. Gen 1/2/3 fans expose one flat "shadow" endpoint (`/mf`) that returns the
whole device's state in a single response. Gen4 fans instead expose the generic WAC
IoT fixture/device REST model: the physical fan is a *system* containing one Fan
fixture and up to two Light fixtures (a downlight and an optional uplight), each with
its own address, read and controlled individually via `/fixture`, plus a separate
`/device` endpoint for device-level info, away mode, reboot, and factory reset.

The PDF alone doesn't fully specify how a client is meant to discover fixture
addresses, and documents no equivalent for several Gen 1-3 features (sleep timers,
adaptive learning, RF pairing, schedules). To fill those gaps, this design also draws
on a real-world reference: a "vibe-coded" but hardware-verified third-party
integration ([Scoop2389/modern-forms-gen4](https://github.com/Scoop2389/modern-forms-gen4),
written against an actual Radiant 56" Gen4 fan per
[home-assistant/core#169247](https://github.com/home-assistant/core/issues/169247)).
That project isn't authoritative, but it's the only evidence available of what a real
Gen4 fan actually does on the wire, and it resolves the gaps the PDF leaves open:

- Gen4 fans self-identify via `POST /device {"query": true}` → `systemType` containing
  `"fan_g4"`.
- Fixture addresses aren't discovered via `/fixture` list — they're **computed** from
  the device's AP MAC address: `fan_addr = (0x0D << 24) | last_3_MAC_bytes`,
  `downlight_addr = (0x05 << 24) | last_3_MAC_bytes`, `uplight_addr = downlight_addr + 1`.
  A device may have zero, one, or two lights; presence is discovered by probing.
- `awayModeEnabled` lives on `/device`, not on the Fan fixture.
- Light color is controlled via `mixColorTemp` (Kelvin) directly — the PDF's
  alternate `colorTempLevel` (1-7 step index) field is unused in practice.
- Sleep timers, adaptive learning, RF pairing, and schedules have no Gen4
  equivalent — this isn't just a PDF omission, the reference implementation doesn't
  attempt them either.

No real Gen4 hardware is available to validate against directly; this design is
built from the PDF plus the above reference, with the `mock_fan` service (from
`2026-07-28-mock-fan-service-design.md`) as the safety net until someone with real
hardware can confirm it.

## Goal

Add Gen4 fan support to `aiomodernforms` without changing the existing asyncio API
surface — the Home Assistant Modern Forms integration should gain Gen4 support by
upgrading this library, not by changing its own code. New Gen4-only capabilities
(uplight, color temperature, identify) are additive.

## Scope

Fan and light control, device info, reboot, and factory reset for Gen4 fans, plus
`mock_fan` and `diagnose.py` support for exercising and diagnosing them. Explicitly
**out of scope**: `decommission()`, RF pairing, and schedules on Gen4 (no confirmed
mapping exists); the Gen4 `Configure`-action tuning fields (`dimmingCurve`, `onRate`,
`offRate`, `dimToWarm`, `dimMode`); mDNS/discovery; validating against real hardware.

## Design

### 1. A single, explicit `generation`

`Device` (in `models.py`) gains a `generation: Generation` field, where `Generation`
is a small `str`-based enum:

```python
class Generation(str, Enum):
    GEN1_2 = "gen1_2"
    GEN3 = "gen3"
    GEN4 = "gen4"
```

This names the same three-way distinction already used informally elsewhere in the
codebase (the `mock_fan` design's `GEN1_2`/`GEN3` profiles, the test fixtures'
`gen1_2_config_response`/`gen3_config_response` naming) and gives it one canonical
home. It's set explicitly by `ModernFormsDevice` on every `update()` — not inferred
per-capability the way `has_wind()` infers breeze support from `state.wind`, because
some Gen4 gaps (adaptive learning, sleep timers) are invisible from field shape alone
(their absence looks identical to a Gen 1/2/3 device that simply reports `False`/`0`).

It becomes the single source of truth used throughout:
- Wire dispatch (`/mf` vs `/device`+`/fixture`) branches on `generation == GEN4`.
- `has_relative_timers()` ⇔ `generation == GEN3` (unchanged behavior, now expressed
  via the explicit field instead of only shape-inference).
- New `has_adaptive_learning()` / `has_sleep_timer()` ⇔ `generation != GEN4`.
- `mock_fan` and `diagnose.py` (below) key off the same enum.

### 2. Detection

On first `update()`, `ModernFormsDevice` tries `POST /device {"query": true}` (reusing
the existing generic `_request(commands, path)` helper — already path-parameterized
for `/config-read`). If the response's `systemType` contains `"fan_g4"` (a small
allow-list constant, so future values are a one-line change), the device is Gen4:
compute and cache the three fixture addresses from `apMac`, then `POST /fixture
{"action": 3, "addr": ...}` for the fan, and probe the downlight/uplight addresses the
same way (a 404 means "not present"; cached after the first check so it isn't
reprobed every poll).

If `/device` errors (e.g. a Gen 1/2/3 fan 404s — it has no such endpoint) or
`systemType` doesn't match, fall back to the existing `/mf` flow unchanged, and set
`generation` to `GEN3` or `GEN1_2` based on the same `fanTimer`/`lightTimer`-presence
signal `has_relative_timers()` already uses. `generation` is cached after the first
successful `update()` — no re-probing on later polls.

### 3. Canonical translation, not a parallel model

A new `aiomodernforms/gen4.py` module holds pure translation functions: fixture
address computation, and mapping between Gen4's wire shapes and the *same* canonical
dict keys `State.from_dict`/`Info.from_dict` already consume (`fanOn`, `fanSpeed`,
`lightBrightness`, ...). `models.py` itself stays generation-agnostic — it already
tolerates optional keys being absent (that's how Gen 1/2 vs Gen 3 coexist today).

New canonical fields with no Gen 1-3 equivalent, added to `State` as
`None`-defaulted (matching the existing `fan_timer`/`light_timer` precedent):
`light_color_temp_kelvin`, `uplight_on`, `uplight_brightness`,
`uplight_color_temp_kelvin`. `Device.has_uplight()` mirrors `has_wind()`.

### 4. Control methods

`fan()` and `light()` keep their exact existing signatures and validation
(speed 1-6, brightness 1-100, direction string, etc.) — only the *send* step becomes
generation-aware:

- **gen1_2/gen3**: unchanged, POSTs the flat command dict to `/mf`.
- **gen4**: the validated inputs are translated (via `gen4.py`) into the fixture wire
  shape — `status`/`fanSpeed`/`wind`/`windSpeed`/boolean-`fanDirection` for the fan,
  `status`/`level` (×100 scale)/`mixColorTemp` for a light — and POSTed as
  `{"action": 4, "addr": <fixture>, "state": {...}}` to `/fixture`. The device echoes
  back the applied fixture state; that's translated back to canonical keys and merged
  into the cached `State` (only the touched fixture's keys change, since a fixture
  response only ever covers itself, unlike `/mf`'s always-full-shadow replies).
- `sleep=` on either method: validated as always, but the resulting timer command is
  dropped before sending when `generation == GEN4` (silent no-op — nothing sent).
- Both methods gain an optional `identify: bool | None = None` kwarg, sent as
  `findme` in the fixture state dict alongside other changes when `generation ==
  GEN4`; silently ignored otherwise (Gen 1-3 has no such field). New
  `has_identify()` ⇔ `generation == GEN4`, so callers know whether to expose it.

**New `uplight()` method** — mirrors `light()` (`brightness`/`on`/`color_temp_kelvin`/
`identify`, same validation bounds) but targets the uplight fixture address. No-ops if
`has_uplight()` is `False`. Purely additive.

**`away()`**: gen1_2/gen3 unchanged (`/mf` shadow field). gen4 sends
`{"awayModeEnabled": ...}` to `/device` instead — same method signature, same
resulting `state.away_mode_enabled`.

**`adaptive_learning()`**: unchanged signature; silently no-ops when `generation ==
GEN4` (nothing sent). `has_adaptive_learning()` lets callers know not to bother.

**`reboot()`**: gen4 sends `{"reboot": true}` to `/device` instead of `/mf`; same
swallow-`ModernFormsConnectionTimeoutError` behavior as today.

**`factory_reset()`**: gen4 sends `{"hardFactoryReset": true}` to `/device` (the
immediate/no-response variant, matching the existing swallow-timeout convention).
`decommission()`, `enable_pairing_mode()`, `clear_paired_devices()`, `set_schedule()`
raise a new `ModernFormsNotSupportedError` when `generation == GEN4`, rather than
guessing at an unconfirmed mapping.

**`config()`**: gen4 issues a fresh `/device {"query": true}` (same opt-in
extra-round-trip semantics as gen1-3's `/config-read`) and maps into the existing
`ConfigInfo`: `device_name`←`deviceName`, `firmware_version`←`iotmVer`,
`rf_version`←`scmVer`, `certificate_id`←`nwkState.certificateID`,
`wifi_strength`←`nwkState.rssi`; `hardware_revision`/`protocol` stay `""` (not present
in the gen4 payload).

### 5. `mock_fan` — Gen4 profile

Extends the (currently in-progress, not yet merged) `mock_fan` design with a third
profile, `GEN4`, alongside `GEN1_2`/`GEN3`:

- Serves `POST /device` (returns `systemType: "fan_g4"`, a fixed `apMac`, plus
  `deviceName`/`iotmVer`/`scmVer`/`owner`/`awayModeEnabled`/`nwkState` fields; honors
  `reboot`/`hardFactoryReset` with the same hold-the-connection-open-past-timeout
  trick already designed for gen1-3's reboot/factory_reset) and `POST /fixture`
  (computes its three addresses using `gen4.compute_fixture_addresses()` — the same
  function the library itself uses, so a bug in address math can't accidentally
  cancel out between mock and client; action 3 = read, action 4 = control, echoing
  back only the changed fixture's state).
- CLI gains `--generation gen4`; `--uplight` flag controls whether the uplight
  fixture exists (mirroring `--breeze`'s independent-toggle pattern).
- Integration tests run the same round-trip suite already planned for gen1_2/gen3
  (`update()`, `light()`/`fan()`/`away()`/`reboot()`/`factory_reset()`), plus new
  `uplight()`, `identify` kwarg handling, and `has_adaptive_learning()`/
  `has_sleep_timer()` returning `False` — all driven through the real
  `ModernFormsDevice`.

### 6. `diagnose.py` changes

Currently assumes `/mf` + `/config-read` unconditionally. Changes:
- `gather_report()` first runs the same `/device` probe `update()` uses to determine
  `generation`, then branches which raw endpoints it dumps: gen1_2/gen3 keep today's
  `/mf` + `/config-read` dump; gen4 dumps raw `/device` and `/fixture` (fan,
  downlight if present, uplight if present) responses instead, with the same
  redaction (owner/MAC/device name/certificate ID) and unknown-key detection applied
  to gen4's field set.
- `run_active_tests()` gains `has_adaptive_learning()`/`has_sleep_timer()` guards
  (skip with the existing "⏭️ not supported" style already used for breeze mode) and
  exercises `uplight()` when `has_uplight()` is `True`. `--active` continues to never
  touch reboot/factory_reset/decommission/pairing/schedule on any generation.

### 7. Testing

- Unit tests for `gen4.py`'s pure translation functions: fixture address computation
  against known MACs, canonical-dict round-tripping in both directions, brightness
  scale conversion at the boundaries (1, 100, 1, 10000).
- `test_aiomodernforms.py` gains a Gen4 fixture set (`/device` and `/fixture`
  responses) exercising: `update()` populating `State`/`Info`/`generation`
  correctly; `light()`/`fan()`/`uplight()`/`away()`/`reboot()`/`factory_reset()`
  round-tripping through `/device`+`/fixture`; `identify` kwarg sending `findme`;
  `has_adaptive_learning()`/`has_sleep_timer()`/`has_uplight()`/`has_identify()`
  returning correctly; `decommission()`/`enable_pairing_mode()`/
  `clear_paired_devices()`/`set_schedule()` raising `ModernFormsNotSupportedError`;
  `config()` mapping `/device` fields into `ConfigInfo`.
- `mock_fan`'s integration test suite gains the Gen4 profile coverage described above.

## Out of scope

- `decommission()`, RF pairing, and schedules on Gen4 — no confirmed mapping exists.
- The Gen4 `Configure`-action tuning fields (`dimmingCurve`, `onRate`, `offRate`,
  `dimToWarm`, `dimMode`) — install-time settings, not runtime control.
- mDNS/Bonjour discovery (consistent with prior specs).
- Validating against real Gen4 hardware — this design is built from the PDF spec
  plus one unverified third-party reverse-engineering effort; real-hardware
  confirmation is a follow-up once a tester with a physical Gen4 fan is available.
