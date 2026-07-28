# Mock Fan Service — Design

## Background

Testing the Home Assistant Modern Forms integration currently requires a real fan on the network. That makes it hard to exercise Gen 1/2 vs Gen 3 differences, breeze-mode vs non-breeze-mode fans, or the reboot/factory-reset disconnect behavior on demand. This repo already documents the wire protocol in detail — `const.py`'s command/state field names, `models.py`'s parsing of both generation shapes, and `2026-07-27-api-parity-design.md`'s catalog of Gen 1/2 vs Gen 3 differences — so that knowledge can drive a mock server that speaks the same protocol back.

## Goal

A standalone HTTP service that behaves like a real Modern Forms fan on the wire, configurable at startup as either a Gen 1/2 or Gen 3 fan, with breeze mode independently toggleable, for pointing a Home Assistant dev instance at during integration development.

## Scope

One mock fan per process, HTTP-only, in-repo dev tool (not published with the `aiomodernforms` package). Accurate happy-path protocol emulation plus the documented reboot/factory-reset/decommission disconnect behavior. No mDNS/discovery, no runtime reconfiguration, no fault injection beyond the documented disconnects, no multi-fan-per-process, no Basic Auth enforcement.

## Design

### 1. Architecture

New top-level `mock_fan/` directory in this repo, excluded from `setup.py`'s `find_packages(include=["aiomodernforms"])` so it never ships in the published package:

- `mock_fan/__main__.py` — CLI entry point (`python -m mock_fan ...`), argparse.
- `mock_fan/generations.py` — static profile data for Gen 1/2 vs Gen 3.
- `mock_fan/state.py` — mutable dynamic-shadow state plus command validation/application.
- `mock_fan/server.py` — `aiohttp.web.Application`, routing `POST /mf` and `POST /config-read`.

Chosen over `http.server` (synchronous, awkward for simulating held-open connections) and Flask (a second, sync web framework in an all-async codebase) because `aiohttp` is already a dependency here, matches the codebase's async style, and lets integration tests drive the mock with the real `aiomodernforms.ModernFormsDevice` client.

Run one process per simulated fan:

```
python -m mock_fan --generation gen3 --breeze --port 8080
python -m mock_fan --generation gen1_2 --port 8081
```

Point Home Assistant's Modern Forms integration at `<host>:<port>` exactly as it would point at a real fan.

### 2. Generation profiles

`generations.py` defines `GEN1_2` and `GEN3` profiles, mirroring the fixtures already in `tests/test_aiomodernforms.py` (`basic_info`/`gen3_info`, `gen1_2_config_response`/`gen3_config_response`):

| Field | Gen 1/2 | Gen 3 |
|---|---|---|
| `clientId`/MAC style | `MF_000000000000` | `MF_C82B9698E5AC` |
| `fanType`/`lightType`/`fanMotorType` | `1818-56` / `F6IN-120V-R1-30` / `DC125X25` | `2003-52` / `""` / `DC125X12` |
| `brand`/`dateCode` (static info) | absent | present (`0` / `"20220101"`) |
| Sleep timers | epoch: `fanSleepTimer`/`lightSleepTimer` | relative seconds: `fanTimer`/`lightTimer` |
| `/config-read` field names | `N`/`PO`/`HD`/`FW`/`RF`, Wi-Fi as percentage | `Name`/`Protocol`/`Firmware Rev`/`RF Rev` (no `HD`), Wi-Fi as dBm string |

Breeze mode (`wind`/`windSpeed`) is an orthogonal `--breeze` CLI flag, independent of generation. When enabled, the dynamic shadow includes `wind` (default `False`) and `windSpeed` (default `2`), matching `breeze_mode_response`. When disabled, those keys are omitted entirely — this is what `Device.has_wind()` keys off of.

### 3. Fan state

`state.py` holds one mutable dataclass for the dynamic shadow: `fanOn`, `fanSpeed`, `fanDirection`, `lightOn`, `lightBrightness`, `awayModeEnabled`, `adaptiveLearning`, `rfPairModeActive`, `resetRfPairList`, `factoryReset`, `decommission`, `schedule`, plus the active profile's timer fields and (if breeze enabled) `wind`/`windSpeed`. Initial defaults: fan off, light off, speed 3, brightness 50, direction forward — matching `basic_response`.

`apply_commands(commands: dict) -> dict`:
- For each recognized command key present in the incoming dict, validate against real constraints:
  - `fanSpeed`: integer 1-6.
  - `lightBrightness`: integer 1-100.
  - `windSpeed`: integer 1-3, and only if breeze is enabled for this profile.
  - `wind`: boolean, only if breeze is enabled for this profile.
  - `fanDirection`: one of `forward`/`reverse`.
  - Boolean fields (`fanOn`, `lightOn`, `awayModeEnabled`, `adaptiveLearning`, `rfPairModeActive`): must be boolean.
- Valid values are applied; invalid ones are silently ignored (not applied, no error returned) — mirroring typical embedded-firmware behavior of no-oping bad input, since the API reference documents no error-response contract for invalid values.
- Returns the full updated dynamic shadow dict — real responses always echo full state, never a diff.

### 4. HTTP protocol handling

**`POST /mf`** — single endpoint for both queries and commands, matching the real device:

- Body `{"queryStaticShadowData": true}` → respond with the static `Info` dict for the active generation profile (state-independent).
- Any other body, including `{"queryDynamicShadowData": true}` or an empty `{}` → apply any command fields present via `apply_commands()`, then respond with the full current dynamic shadow dict.
- If the body contains `factoryReset: true`, `decommission: true`, or `reboot: true`: apply the corresponding state change (`factoryReset`/`decommission` reset the dynamic shadow to its startup defaults), then **never write a response** on that connection — hold it open past the client's request timeout so `aiomodernforms` observes a real `TimeoutError` → `ModernFormsConnectionTimeoutError`, which `factory_reset()`/`decommission()`/`reboot()` already catch and swallow. After a fixed 5-second delay, the server resumes responding normally to new connections, simulating the device coming back online — useful for exercising HA's reconnect behavior.

**`POST /config-read`** — returns the generation-appropriate config dict, built from the same profile data as `/mf`'s static info, independent of dynamic state.

No authentication is enforced, regardless of whether the client sends Basic Auth credentials.

### 5. CLI

```
python -m mock_fan --generation {gen1_2,gen3} [--breeze] [--host HOST] [--port PORT]
```

- `--generation`: required, no default — forces an explicit choice.
- `--breeze`: flag, default off.
- `--host`: default `0.0.0.0`.
- `--port`: default `8080` (matches `diagnose.py`'s `--port` convention; avoids requiring root for port 80).

On startup, prints one confirmation line (generation, breeze on/off, host:port).

### 6. Testing

1. **Unit tests** for `state.py`'s `apply_commands()`: valid values applied, invalid ones silently ignored, wind/windSpeed rejected when breeze disabled, correct timer field used per generation.
2. **Integration tests** using `aiohttp`'s test utilities to run the mock server in-process, driven by the real `aiomodernforms.ModernFormsDevice` client — proving round-trip correctness against the actual client this mock exists to support. Covers: `update()` populating `Info`/`State` correctly per generation; `light()`/`fan()`/`away()`/`adaptive_learning()` round-tripping; `has_breeze_mode()`/`has_relative_timers()` reporting correctly per profile; `config()` returning gen-correct fields; `reboot()`/`factory_reset()`/`decommission()` raising-then-swallowing `ModernFormsConnectionTimeoutError`, and the server resuming normal responses afterward.

## Out of scope

- mDNS/Bonjour discovery (matches the precedent in `2026-07-27-api-parity-design.md` — HA is pointed at a known IP).
- Runtime capability switching / admin endpoint.
- Fault injection beyond the documented reboot/factory_reset/decommission disconnect (arbitrary timeouts, malformed JSON, HTTP error codes).
- Multiple simulated fans in a single process.
- Basic Auth enforcement.
