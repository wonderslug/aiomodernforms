# API Parity Pass — Design

## Background

`WAC_Modern_Forms_3rd_Party_API_Reference.pdf` (the vendor's 3rd-party IP API definition) documents the full REST/JSON API surface for WAC and Modern Forms smart fans across three hardware generations. Comparing it against `aiomodernforms/modernforms.py`, `models.py`, and `const.py` surfaced several gaps and one likely bug.

## Findings

1. **Sleep timer bug (Gen 3).** The library always sends `fanSleepTimer`/`lightSleepTimer` as an epoch timestamp. That's correct for Gen 1/2 fans, but the reference documents Gen 3 fans using different property names — `fanTimer`/`lightTimer` — holding a relative **seconds-until-off** value, not an epoch timestamp. On real Gen 3 hardware, the current sleep-timer feature would silently no-op.
2. **Dropped shadow fields.** The dynamic shadow response includes `rfPairModeActive`, `resetRfPairList`, `factoryReset`, `decommission`, `schedule`, and (Gen 3) `userData`, none of which are captured by `State.from_dict` — they're parsed off the wire and discarded.
3. **Missing static info fields.** Gen 3's static shadow data includes `brand` and `dateCode`; `Info` doesn't capture either.
4. **Missing control methods.** The reference documents write access to pairing mode, RF pair-list reset, factory reset, decommission, and the schedule blob. None of these have corresponding library methods.
5. **`/config-read` not implemented.** A separate endpoint (distinct from the `/mf` shadow endpoint) returns hardware revision, RF library version, certificate ID, and Wi-Fi signal strength — data not available anywhere else in the library.
6. **Undocumented `reboot` command.** `COMMAND_REBOOT = "reboot"` isn't in the reference at all. Left as-is (presumed working against real hardware; removing carries more risk than leaving it), flagged here for future confirmation with WAC support.
7. **Drive-by bug.** `async def away(self, away=bool)` and `async def adaptive_learning(self, adaptive_learning=bool)` use `=bool` (the type itself) as the parameter default, not a type hint. Latent bug: calling either with no argument sends the literal `bool` type object as the command value instead of a real boolean.

## Scope

Full parity: fix the timer bug, capture every documented field, add every documented write method, and add `/config-read` support. Explicitly **out of scope**: mDNS discovery and device commissioning — those are a different concern (network discovery) from this library's job of talking to a fan whose IP is already known.

## Design

### 1. Generation-aware sleep timers

`State` gains two new fields alongside the existing epoch-based ones:

```python
fan_timer: Optional[int] = None   # Gen 3: seconds until fan turns off
light_timer: Optional[int] = None # Gen 3: seconds until light turns off
```

Populated via `data.get(STATE_FAN_TIMER)` / `data.get(STATE_LIGHT_TIMER)`, defaulting to `None` when absent (Gen 1/2 responses).

`Device.has_relative_timers() -> bool` mirrors the existing `has_wind()` capability-detection pattern:

```python
def has_relative_timers(self) -> bool:
    return self.state.fan_timer is not None or self.state.light_timer is not None
```

`ModernFormsDevice.light()` and `.fan()` currently duplicate epoch-timestamp math for the `sleep` argument. Extract it into a private helper:

```python
def _sleep_command(
    self, epoch_command: str, relative_command: str, sleep: Union[int, datetime]
) -> Dict[str, int]:
    """Build the timer command dict, choosing epoch or relative semantics
    based on what the device's last response told us it uses."""
```

Behavior:
- Device unknown (no `update()` yet) → epoch semantics (current/legacy behavior; matches how `wind`/`wind_speed` already silently no-op pre-`update()`).
- `has_relative_timers()` is `True` → relative semantics: an `int` sleep value is sent as-is (already seconds); a `datetime` is converted to `int((sleep - datetime.now()).total_seconds())`.
- Otherwise → existing epoch semantics, unchanged.

New constants: `STATE_FAN_TIMER = "fanTimer"`, `STATE_LIGHT_TIMER = "lightTimer"`, `COMMAND_FAN_TIMER = "fanTimer"`, `COMMAND_LIGHT_TIMER = "lightTimer"`.

### 2. Full field capture

`State` gains: `rf_pair_mode_active: bool`, `reset_rf_pair_list: bool`, `factory_reset: bool`, `decommission: bool`, `schedule: str`, `user_data: str` (all default `False`/`""` when absent), plus `fan_timer`/`light_timer` from Section 1.

`Info` gains: `brand: Optional[int]` (default `None`), `date_code: str` (default `""`).

All additions follow the existing `data.get(CONST, default)` pattern — no change to parsing behavior for responses that omit Gen-3-only keys.

New constants: `STATE_RF_PAIR_MODE_ACTIVE`, `STATE_RESET_RF_PAIR_LIST`, `STATE_FACTORY_RESET`, `STATE_DECOMMISSION`, `STATE_SCHEDULE`, `STATE_USER_DATA`, `INFO_BRAND`, `INFO_DATE_CODE`.

### 3. New control methods

On `ModernFormsDevice`, following the existing `away()`/`adaptive_learning()`/`reboot()` conventions:

```python
async def enable_pairing_mode(self, active: bool = True) -> None
async def clear_paired_devices(self) -> None       # fire-once trigger, like reboot()
async def factory_reset(self) -> None              # fire-once; swallows ModernFormsConnectionTimeoutError
async def decommission(self) -> None                # fire-once; swallows ModernFormsConnectionTimeoutError
async def set_schedule(self, data: str) -> None     # base64-encoded schedule blob
```

Reading the schedule is free via `status.schedule` once Section 2 lands.

`factory_reset()` and `decommission()` both disconnect/re-enter AP mode on success, so they catch `ModernFormsConnectionTimeoutError` the same way `reboot()` does.

Drive-by fix: change `away(self, away=bool)` → `away(self, away: bool)` and `adaptive_learning(self, adaptive_learning=bool)` → `adaptive_learning(self, adaptive_learning: bool)`.

New constants: `COMMAND_RF_PAIR_MODE = "rfPairModeActive"`, `COMMAND_RESET_RF_PAIR_LIST = "resetRfPairList"`, `COMMAND_FACTORY_RESET = "factoryReset"`, `COMMAND_DECOMMISSION = "decommission"`, `COMMAND_SCHEDULE = "schedule"`.

### 4. `/config-read` support

A separate endpoint from `/mf`, with data unavailable elsewhere: hardware revision, RF library version, certificate ID, Wi-Fi signal strength. Response shape differs by generation:

| Field | Gen 1/2 key | Gen 3 key |
|---|---|---|
| device name | `N` | `Name` |
| protocol | `PO` | `Protocol` |
| hardware revision | `HD` | *(not present)* |
| firmware version | `FW` | `Firmware Rev` |
| RF version | `RF` | `RF Rev` |
| certificate ID | `certificateId` | `certificateId` |
| Wi-Fi strength | `Wi-Fi strength` (percentage) | `Wi-Fi strength` (dBm string) |

The reference marks the Gen 1/2 endpoint as accepting `ANY` HTTP method, so both generations are queried with `POST`.

New `ConfigInfo` dataclass:

```python
@dataclass
class ConfigInfo:
    device_name: str
    protocol: str
    hardware_revision: str   # empty string on Gen 3, which doesn't send HD
    firmware_version: str
    rf_version: str
    certificate_id: str
    wifi_strength: str       # raw value; unit (percentage vs dBm) depends on
                              # generation — callers should not assume percentage
```

New method: `ModernFormsDevice.config() -> ConfigInfo`. Standalone/opt-in — not folded into `update()`, since it's an extra round-trip most callers won't need on every poll.

Requires generalizing `_request()`/URL construction: today `self._base_path` bakes in the `mf` endpoint at `__init__` time. Refactor so the endpoint path (`mf` vs `config-read`) is a per-call parameter, with `self._base_path` reduced to just the directory prefix.

### 5. Testing

- Extend the two existing dynamic-shadow-data fixtures (Gen 1/2-shaped and Gen 3-shaped) with the newly-captured fields (`schedule`, `userData`, `rfPairModeActive`, `resetRfPairList`, `factoryReset`, `decommission`) so field capture is exercised for both shapes.
- Add a third fixture using `fanTimer`/`lightTimer` (distinct from the current fixtures, which both use `fanSleepTimer`) to exercise `has_relative_timers()` and the relative-seconds branch of `light()`/`fan()`.
- New tests per new method: `enable_pairing_mode`, `clear_paired_devices`, `factory_reset` (+ timeout-swallowing behavior), `decommission` (+ same), `set_schedule`.
- New tests for `config()` against both a Gen 1/2-shaped and a Gen 3-shaped `/config-read` fixture, verifying the path/method used and field mapping — including that `wifi_strength` is passed through raw rather than coerced.
- Existing `away()`/`adaptive_learning()` tests continue to pass after the type-hint fix (no behavior change for real callers).

## Out of scope

- mDNS/Bonjour discovery of fans on the network.
- Device commissioning (pairing a fan to Wi-Fi/cloud for the first time) — the reference itself says this isn't officially supported via REST.
