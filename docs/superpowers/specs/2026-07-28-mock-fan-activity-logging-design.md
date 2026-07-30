# Mock Fan Activity Logging — Design

## Background

The `mock_fan` service currently runs silently: once started, nothing is printed except the one-time startup banner. When using it to test a Home Assistant integration, there's no way to see what requests the integration is actually making — whether it's polling status, sending commands, what those commands are, or triggering a simulated reboot/factory-reset/decommission disconnect.

## Goal

Log each request the mock fan handles, always on, so activity is visible in the terminal while the mock is running.

## Design

### Mechanism

Python's standard `logging` module, not `print()`. `mock_fan/__main__.py`'s `main()` calls `logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")` before starting the server. `mock_fan/server.py` gets a module-level logger via `logging.getLogger(__name__)`.

Always on at `INFO` level, no `--quiet`/`--verbose` CLI flag — the tool's whole purpose here is watching its own activity, so there's no case for silencing it in this iteration. The existing one-time startup banner in `__main__.py` stays a plain `print()`, unchanged — it's not per-request activity, converting it adds nothing.

One side effect worth calling out: `aiohttp.web.run_app()` already has a built-in access logger that emits one line per request (`METHOD /path → status`) through this same `logging` module — it's just been silently dropped so far because nothing configured `logging` to a visible level. Once `basicConfig` is set, that access log starts appearing too, for free, alongside the semantic log lines below.

### What gets logged

All in `mock_fan/server.py`'s `_handle_mf` and `_handle_config_read`:

- **A request arriving during the simulated disconnect window** (i.e. `loop.time() < fan.unresponsive_until`, before the `asyncio.sleep(DISCONNECT_HOLD_SECS)` that holds it): `"request received while unresponsive (simulated disconnect) — holding connection"`.
- **A static info query** (`commands.get(COMMAND_QUERY_STATIC_DATA)` truthy): `"static info request"`.
- **A disruptive command** (`reboot`/`factoryReset`/`decommission`) being triggered: logged right before the state reset and the connection hold, naming whichever of the three fired and the configured resume delay — e.g. `"reboot received — disconnecting for 5.0s"`.
- **A command request** (the normal `apply_commands()` path): snapshot the shadow via `fan.state.snapshot()` before calling `apply_commands()`, and diff it against the returned snapshot — log only the keys whose values actually differ, e.g. `"applied changes: {'fanOn': True, 'fanSpeed': 5}"`. If nothing changed (a pure status read via `queryDynamicShadowData`, or every field in the request was invalid/rejected/already-matching), log `"status read (no changes)"` instead. This diff-based approach needs no changes to `FanState`'s interface — it's computed entirely in `server.py` from two `snapshot()` calls already available — and it naturally filters out the `queryDynamicShadowData` marker key, which was never a real shadow field and so never appears as "changed."
- **`POST /config-read`**: `"config-read request"`.

### Testing

Existing tests are unaffected — none of them assert on log output, and adding `logging.basicConfig` in `main()` (not at import time) means importing `mock_fan.server` for tests doesn't configure global logging as a side effect. New tests use `caplog` (pytest's built-in log-capture fixture) against the real integration-test pattern already established in `tests/mock_fan/test_server.py`: drive the real `aiomodernforms.ModernFormsDevice` client against a real `TestServer`, and assert the expected log message appears in `caplog.records` for each of the five cases above (static info request, config-read request, applied-changes with the right diff, status-read-with-no-changes, and a disruptive command's log line). The disconnect-window "holding connection" log line reuses the existing `resume_delay_secs`-shortening pattern from `test_reboot_disconnects_then_resumes` to keep the test fast.

## Out of scope

- A `--quiet`/`--verbose`/`--log-level` CLI flag.
- Suppressing or reformatting aiohttp's built-in access log.
- Structured/JSON logging output.
