# Gen4 Fan Support — Design

## Background

`WAC_IoT_Unified_REST_Interface_3rd_Party_V1.91.pdf` (a newer vendor doc than
`WAC_Modern_Forms_3rd_Party_API_Reference.pdf`) documents a "Gen4 Fan" that speaks an
entirely different wire protocol from the Gen 1/2/3 fans this library already
supports. Gen 1/2/3 fans expose one flat "shadow" endpoint (`/mf`) that returns the
whole device's state in a single response. Gen4 fans instead expose the generic WAC
IoT fixture/device REST model: the physical fan is a *system* containing one Fan
fixture and one or more Light fixtures (how many varies by fan model), each with its
own address, read and controlled individually via `/fixture`, plus a separate
`/device` endpoint for device-level info, away mode, reboot, and factory reset.

The PDF documents no equivalent for several Gen 1-3 features (sleep timers,
adaptive learning, RF pairing, schedules). To fill those gaps, this design also draws
on a real-world reference: a "vibe-coded" but hardware-verified third-party
integration ([Scoop2389/modern-forms-gen4](https://github.com/Scoop2389/modern-forms-gen4),
written against an actual Radiant 56" Gen4 fan per
[home-assistant/core#169247](https://github.com/home-assistant/core/issues/169247)).
That project isn't authoritative, but it's the only evidence available of what a real
Gen4 fan actually does on the wire, and it resolves the gaps the PDF leaves open:

- Gen4 fans self-identify via `POST /device {"query": true}` → `systemType` containing
  `"fan_g4"`.
- `awayModeEnabled` lives on `/device`, not on the Fan fixture.
- Light color is controlled via `mixColorTemp` (Kelvin) directly — the PDF's
  alternate `colorTempLevel` (1-7 step index) field is unused in practice.
- Sleep timers, adaptive learning, RF pairing, and schedules have no Gen4
  equivalent — this isn't just a PDF omission, the reference implementation doesn't
  attempt them either.

The reference implementation discovers fixture addresses by **computing** them from
the device's MAC address (a fixed formula per fixture type), because its author never
had the PDF and reverse-engineered purely from packet captures against one specific
fan model with exactly one downlight and one uplight. That doesn't generalize — a
different fan model with a different number of lights would need a different, unknown
formula — and computing a device's own addressing scheme from its MAC address isn't a
sound approach on its own terms. This design instead uses the PDF's actually-documented
discovery mechanism (`/fixture` read-all, see §2/§3), which returns every fixture's
real address directly from the device and scales to however many lights a given fan
model exposes, with no address arithmetic anywhere in this library.

No real Gen4 hardware is available to validate against directly; this design is
built from the PDF plus the above reference, with the `mock_fan` service (from
`2026-07-28-mock-fan-service-design.md`) as the safety net until someone with real
hardware can confirm it.

## Goal

Add Gen4 fan support to `aiomodernforms` without changing the existing asyncio API
surface — the Home Assistant Modern Forms integration should gain Gen4 support by
upgrading this library, not by changing its own code. New Gen4-only capabilities
(an arbitrary number of lights, color temperature, identify) are additive, and the
number of lights a given fan exposes is discovered from the device rather than
assumed — some models may have one light, some may have more.

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
follow up with `POST /fixture {"action": 3}` — the PDF-documented "read all" call
(`addr` omitted) that returns every fixture on the device in one response, each with
its real `addr`, `type`, and current `state`. No address is ever computed by this
library; every address used for control comes from what the device itself reported.

If `/device` errors (e.g. a Gen 1/2/3 fan 404s — it has no such endpoint) or
`systemType` doesn't match, fall back to the existing `/mf` flow unchanged, and set
`generation` to `GEN3` or `GEN1_2` based on the same `fanTimer`/`lightTimer`-presence
signal `has_relative_timers()` already uses. `generation` (and, for Gen4, the fixture
address list) is cached after the first successful `update()` — no re-discovery on
later polls.

### 3. Canonical translation, not a parallel model

A new `aiomodernforms/gen4.py` module holds pure translation functions: classifying
the `/fixture` read-all response's array by `type`, and mapping each fixture's
wire-shaped `state` into the *same* canonical dict keys `State.from_dict`/
`Info.from_dict` already consume (`fanOn`, `fanSpeed`, `lightBrightness`, ...).
`models.py` itself mostly stays generation-agnostic — it already tolerates optional
keys being absent (that's how Gen 1/2 vs Gen 3 coexist today).

**Extensibility note.** The PDF defines ten fixture types in total (single-color
dimmable, tunable white, RGBW, motorized trackhead, ELV single-color, wall station,
24V controller, fan, and two decorative-light variants) across a broader WAC IoT
product line (Ventrix, ColorScaping, InvisiLED, WAC Home Gateway) that this library
doesn't otherwise support and isn't taking on here — a fan has exactly one Fan
fixture and some number of Light-shaped fixtures, and that's what this design
handles. But the classification step is written as a lookup against the numeric
`type` field (`13` → fan; `{0, 1, 2, 14, 15}` → light-shaped; anything else — e.g. a
Wall Station at `11` — ignored) rather than any fan-specific assumption, so a future
"general WAC IoT client" effort covering the rest of the product line could build on
the same `/fixture` request/response handling instead of starting over. No code for
those other fixture/product types is written now.

**Multiple lights, with capability info.** A new small dataclass holds one light's
state:

```python
@dataclass
class Light:
    address: int | None  # None for gen1_2/gen3's single non-addressable light
    fixture_type: int | None  # None for gen1_2/gen3; raw WAC fixture type otherwise
    name: str
    on: bool
    brightness: int  # 1-100, same scale as State.light_brightness
    color_temp_kelvin: int | None
    min_color_temp_kelvin: int | None  # from the fixture's `detail`, when present
    max_color_temp_kelvin: int | None
```

`fixture_type` carries the raw numeric type the device reported (`0` = single-color
dimmable, `1` = tunable white, `2` = RGBW, `14`/`15` = decorative — documented as
behaving like tunable white) so a caller like the HA integration can decide exactly
what to advertise per light — brightness-only for `0`, brightness + color temp for
`1`/`14`/`15` — instead of guessing from which optional fields happen to be present.
`min_color_temp_kelvin`/`max_color_temp_kelvin` come from that same fixture's
`detail` object in the read-all response (no extra request) when the device reports
a range; `None` when it doesn't (e.g. a non-CCT light, or firmware that omits
`detail`). RGBW (`type == 2`) is deliberately not given color fields here — no known
Modern Forms fan model uses it, and it's out of scope until one does (see below).

`State` gains `light_fixtures: list[Light]`, populated for **every** generation, not
just Gen4:
- gen1_2/gen3: exactly one synthetic `Light(address=None, fixture_type=None, ...)`
  mirroring the existing `light_on`/`light_brightness` fields, with color temp bounds
  left `None` (Gen 1-3 has no color temperature control at all).
- gen4: one real `Light` per light-shaped fixture found in the read-all response, in
  the order the device returned them, with `address`/`fixture_type` set from that
  fixture.

This lets a caller iterate `status.light_fixtures` uniformly regardless of
generation or how many lights a specific fan model has, instead of branching on
generation or assuming a fixed count. The existing `light_on`/`light_brightness`/
`light_color_temp_kelvin` fields on `State` continue to exist unchanged, always
mirroring `light_fixtures[0]` — full backward compatibility for existing callers who
only ever cared about "the" light.

### 4. Control methods

`fan()` and `light()` keep their existing parameters and validation unchanged
(speed 1-6, brightness 1-100, direction string, etc.) — every existing call site
keeps working exactly as before. New Gen4-only capabilities are added as new
optional keyword-only parameters (detailed below), never by changing what an
existing parameter means. The *send* step becomes generation-aware:

- **gen1_2/gen3**: unchanged, POSTs the flat command dict to `/mf`.
- **gen4**: the validated inputs are translated (via `gen4.py`) into the fixture wire
  shape — `status`/`fanSpeed`/`wind`/`windSpeed`/boolean-`fanDirection` for the fan,
  `status`/`level` (×100 scale)/`mixColorTemp` for a light — and POSTed as
  `{"action": 4, "addr": <fixture>, "state": {...}}` to `/fixture`, using that
  fixture's real address as discovered on the last `update()`. The device echoes back
  the applied fixture state; that's translated back to canonical keys and merged into
  the cached `State` (only the touched fixture's keys change, since a fixture
  response only ever covers itself, unlike `/mf`'s always-full-shadow replies).
- `sleep=` on either method: validated as always, but the resulting timer command is
  dropped before sending when `generation == GEN4` (silent no-op — nothing sent).
- Both methods gain an optional `identify: bool | None = None` kwarg, sent as
  `findme` in the fixture state dict alongside other changes when `generation ==
  GEN4`; silently ignored otherwise (Gen 1-3 has no such field). New
  `has_identify()` ⇔ `generation == GEN4`, so callers know whether to expose it.
- `light()` always controls `light_fixtures[0]` — the first light the device
  reported, whatever it is.

**New `light_fixture()` method** — generalized light control, for any light beyond
the first:

```python
async def light_fixture(
    self,
    address: int | None,
    *,
    brightness: int | None = None,
    on: bool | None = None,
    color_temp_kelvin: int | None = None,
    identify: bool | None = None,
) -> None: ...
```

Same validation bounds as `light()`. `address` is one of the values found in
`status.light_fixtures[*].address` — pass `None` to target the gen1_2/gen3 synthetic
entry (routes through the existing `/mf` flat-endpoint path, `color_temp_kelvin`
silently ignored there since Gen 1-3 has no such field), or a real fixture address to
control that specific Gen4 light via `/fixture`. `light()` is implemented in terms of
this: `light(**kwargs)` ⇔ `light_fixture(status.light_fixtures[0].address, **kwargs)`.
This single method scales to however many lights `light_fixtures` contains; there's
no separate per-position method (no `uplight()`), since the number of additional
lights isn't fixed.

`light()`'s existing signature has no `color_temp_kelvin` parameter (Gen 1-3 never
had color temperature control, so it was never added there). Rather than change
`light()`'s signature incompatibly, it gains `color_temp_kelvin: int | None = None`
as a new optional keyword-only parameter — purely additive, existing
positional/keyword calls are unaffected, and it's silently ignored on gen1_2/gen3
like the other Gen4-only fields.

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

- Serves `POST /device` (returns `systemType: "fan_g4"`, plus
  `deviceName`/`iotmVer`/`scmVer`/`owner`/`awayModeEnabled`/`nwkState` fields; honors
  `reboot`/`hardFactoryReset` with the same hold-the-connection-open-past-timeout
  trick already designed for gen1-3's reboot/factory_reset) and `POST /fixture`
  (action 3 with no `addr` = read-all, returning the fan fixture plus however many
  light fixtures this mock instance is configured with; action 3 with an `addr` =
  read one; action 4 = control, echoing back only the changed fixture's state).
  Fixture addresses are just fixed test constants the mock assigns itself — nothing
  computed from a MAC, matching the real device's role as the source of truth for its
  own addresses.
- CLI gains `--generation gen4`; `--lights N` (default 1) controls how many light
  fixtures the mock reports, so the test suite can exercise 0, 1, 2, or more without
  the mock or the library caring about a specific "uplight" concept. Mocked lights
  default to `type: 1` (tunable white) with a `detail.minColorTemp`/`maxColorTemp`
  pair, so the `fixture_type`/color-temp-range plumbing has real read-all fixtures to
  exercise; the test fixture set also includes a `type: 0` (single-color, no color
  temp fields) light to confirm that case classifies and translates correctly.
- Integration tests run the same round-trip suite already planned for gen1_2/gen3
  (`update()`, `light()`/`fan()`/`away()`/`reboot()`/`factory_reset()`), plus new
  `light_fixture()` against each configured light, `identify` kwarg handling, and
  `has_adaptive_learning()`/`has_sleep_timer()` returning `False` — all driven
  through the real `ModernFormsDevice`.

### 6. `diagnose.py` changes

Currently assumes `/mf` + `/config-read` unconditionally. Changes:
- `gather_report()` first runs the same `/device` probe `update()` uses to determine
  `generation`, then branches which raw endpoints it dumps: gen1_2/gen3 keep today's
  `/mf` + `/config-read` dump; gen4 dumps the raw `/device` response and the raw
  `/fixture` read-all response instead, with the same redaction (owner/MAC/device
  name/certificate ID) and unknown-key detection applied to gen4's field set, and the
  discovered fixture count/types called out explicitly in the report (useful for
  spotting a fan model with an unexpected number of lights).
- `run_active_tests()` gains `has_adaptive_learning()`/`has_sleep_timer()` guards
  (skip with the existing "⏭️ not supported" style already used for breeze mode) and
  exercises `light_fixture()` against every entry in `status.light_fixtures` beyond
  the first. `--active` continues to never touch
  reboot/factory_reset/decommission/pairing/schedule on any generation.

### 7. Testing

- Unit tests for `gen4.py`'s pure translation functions: fixture-array classification
  by type (including an unrecognized type being ignored rather than erroring),
  canonical-dict round-tripping in both directions, brightness scale conversion at
  the boundaries (1, 100, 1, 10000), and `Light.fixture_type`/
  `min_color_temp_kelvin`/`max_color_temp_kelvin` populating from a fixture's
  `detail` when present and defaulting to `None` when absent.
- `test_aiomodernforms.py` gains a Gen4 fixture set (`/device` and `/fixture`
  read-all responses, including variants with 0, 1, and 3 light fixtures) exercising:
  `update()` populating `State`/`Info`/`generation`/`light_fixtures` correctly for
  each light count; `light()`/`fan()`/`light_fixture()`/`away()`/`reboot()`/
  `factory_reset()` round-tripping through `/device`+`/fixture`; `identify` kwarg
  sending `findme`; `has_adaptive_learning()`/`has_sleep_timer()`/`has_identify()`
  returning correctly; `decommission()`/`enable_pairing_mode()`/
  `clear_paired_devices()`/`set_schedule()` raising `ModernFormsNotSupportedError`;
  `config()` mapping `/device` fields into `ConfigInfo`.
- `mock_fan`'s integration test suite gains the Gen4 profile coverage described above.

## Out of scope

- `decommission()`, RF pairing, and schedules on Gen4 — no confirmed mapping exists.
- The Gen4 `Configure`-action tuning fields (`dimmingCurve`, `onRate`, `offRate`,
  `dimToWarm`, `dimMode`) — install-time settings, not runtime control.
- RGBW lights (fixture `type == 2`) — no known Modern Forms fan model has one; only
  `on`/`brightness` would be captured for such a fixture today, no RGB fields.
- Non-fan WAC IoT fixture/product types (motorized trackhead, ELV, wall station, 24V
  controller, and the Ventrix/ColorScaping/InvisiLED/WAC Home Gateway product lines),
  and the `/group`/`/automation`/`/network`/`/ota`/`/remote`/`/input`/`/fs`/
  `/integration`/`/debug` endpoints — a general WAC IoT client is a substantially
  larger effort than fan support and belongs in its own future spec once there's an
  actual consumer for it. The `/fixture` classification code in this design is
  written generically enough (dispatch on numeric `type`) not to block that later,
  but no such support is implemented now.
- mDNS/Bonjour discovery (consistent with prior specs).
- Validating against real Gen4 hardware — this design is built from the PDF spec
  plus one unverified third-party reverse-engineering effort; real-hardware
  confirmation is a follow-up once a tester with a physical Gen4 fan is available.
