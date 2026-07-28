"""Diagnostic tool for reporting fan compatibility to a GitHub issue.

Connects to a Modern Forms / WAC fan on the local network and prints a
Markdown report of what it found: parsed status/info, the raw API
responses, and any response keys this library doesn't recognize yet
(useful for spotting model/generation differences like WAC and Modern
Forms cloud-side field names, both of which speak the same shape).

Personally identifying and credential-like fields (account email, AWS
identity, MAC address, device name, certificate ID) are redacted before
anything is printed, and the host/IP passed on the command line is never
included in the report output, so the result should be safe to paste
into a public GitHub issue as-is. Still, skim it once before posting.

Pass --active to additionally exercise the fan's reversible control
commands (light, fan speed/direction/power, breeze mode, away mode) and
confirm they work end-to-end, not just that the device is reachable.
Original state is restored afterward regardless of test outcome.
Destructive or disruptive commands are never sent: reboot, factory_reset,
decommission, clear_paired_devices, enable_pairing_mode, set_schedule, and
adaptive_learning are always skipped.

Usage:
    python diagnose.py 192.168.1.85
    python diagnose.py 192.168.1.85 --active > report.md
    python diagnose.py 192.168.1.85 --port 8080 --tls > report.md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Awaitable, Callable, Iterable
from datetime import datetime
from typing import Any

import aiomodernforms
from aiomodernforms import const
from aiomodernforms.__version__ import __version__
from aiomodernforms.models import ConfigInfo, Device

REDACTED = "<redacted>"

# Fields that identify a specific device, account, or person. These are
# never printed, regardless of which raw response they show up in.
SENSITIVE_KEYS = {
    const.INFO_OWNER,  # account email address
    const.INFO_FEDERATED_IDENTITY,  # AWS Cognito identity
    const.INFO_MAC,
    const.INFO_DEVICE_NAME,  # user-assigned name, e.g. "Living Room"
    const.CONFIG_CERTIFICATE_ID,
    const.CONFIG_NAME_LEGACY,  # config-read device name, Gen 1/2
    const.CONFIG_NAME,  # config-read device name, Gen 3
}

# Every key this library currently parses out of each endpoint's response.
# Anything else present in a real response is new/undocumented and worth
# calling out explicitly in the report.
STATIC_KNOWN_KEYS = {
    const.INFO_CLIENT_ID,
    const.INFO_MAC,
    const.INFO_LIGHT_TYPE,
    const.INFO_FAN_TYPE,
    const.INFO_FAN_MOTOR_TYPE,
    const.INFO_PRODUCTION_LOT_NUMBER,
    const.INFO_PRODUCT_SKU,
    const.INFO_OWNER,
    const.INFO_FEDERATED_IDENTITY,
    const.INFO_DEVICE_NAME,
    const.INFO_FIRMWARE_VERSION,
    const.INFO_MAIN_MCU_FIRMWARE_VERSION,
    const.INFO_FIRMWARE_URL,
    const.INFO_BRAND,
    const.INFO_DATE_CODE,
}

DYNAMIC_KNOWN_KEYS = {
    const.INFO_CLIENT_ID,
    const.STATE_FAN_POWER,
    const.STATE_FAN_SPEED,
    const.STATE_FAN_DIRECTION,
    const.STATE_FAN_SLEEP_TIMER,
    const.STATE_FAN_TIMER,
    const.STATE_LIGHT_POWER,
    const.STATE_LIGHT_BRIGHTNESS,
    const.STATE_LIGHT_SLEEP_TIMER,
    const.STATE_LIGHT_TIMER,
    const.STATE_AWAY_MODE,
    const.STATE_ADAPTIVE_LEARNING,
    const.STATE_WIND_POWER,
    const.STATE_WIND_SPEED,
    const.STATE_RF_PAIR_MODE_ACTIVE,
    const.STATE_RESET_RF_PAIR_LIST,
    const.STATE_FACTORY_RESET,
    const.STATE_DECOMMISSION,
    const.STATE_SCHEDULE,
    const.STATE_USER_DATA,
}

CONFIG_KNOWN_KEYS = {
    const.CONFIG_NAME,
    const.CONFIG_NAME_LEGACY,
    const.CONFIG_PROTOCOL,
    const.CONFIG_PROTOCOL_LEGACY,
    const.CONFIG_HARDWARE_REVISION,
    const.CONFIG_FIRMWARE_VERSION,
    const.CONFIG_FIRMWARE_VERSION_LEGACY,
    const.CONFIG_RF_VERSION,
    const.CONFIG_RF_VERSION_LEGACY,
    const.CONFIG_CERTIFICATE_ID,
    const.CONFIG_WIFI_STRENGTH,
    const.CONFIG_WIFI_STRENGTH_ALT,
    const.CONFIG_WIFI_STRENGTH_ALT2,
}


def _redact_client_id(value: Any) -> Any:
    """Keep the brand prefix (diagnostically useful); redact the MAC suffix."""
    if isinstance(value, str) and "_" in value:
        prefix = value.split("_", 1)[0]
        return f"{prefix}_{REDACTED}"
    return REDACTED


def redact(raw: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of a raw API response with sensitive fields redacted."""
    cleaned = dict(raw)
    for key in cleaned:
        if key == const.INFO_CLIENT_ID:
            cleaned[key] = _redact_client_id(cleaned[key])
        elif key in SENSITIVE_KEYS:
            cleaned[key] = REDACTED
        elif key == const.STATE_SCHEDULE and cleaned[key]:
            cleaned[key] = f"<{len(cleaned[key])} chars, redacted>"
    return cleaned


def unknown_keys(raw: dict[str, Any], known: set[str]) -> Iterable[str]:
    """Keys present in a raw response that this library doesn't parse yet."""
    return sorted(set(raw) - known)


def _json_block(data: Any) -> str:
    return "```json\n" + json.dumps(data, indent=2, sort_keys=True) + "\n```"


def _section(title: str) -> str:
    return f"\n### {title}\n"


async def run_active_tests(fan: aiomodernforms.ModernFormsDevice) -> list[str]:
    """Exercise reversible control commands and restore original state after.

    Never sends destructive or disruptive commands: reboot, factory_reset,
    decommission, clear_paired_devices, enable_pairing_mode, set_schedule,
    and adaptive_learning are always skipped. `fan._device` must already be
    populated (the caller is expected to have fetched status first).
    """
    out = [_section("Active control tests")]
    out.append(
        "Exercising light, fan, breeze, and away-mode controls. Original "
        "state is restored at the end regardless of test outcome."
    )

    original = fan.status
    results: list[tuple[str, bool, str]] = []
    supports_wind = original.wind is not None
    relative_timers = fan.has_relative_timers()

    async def check(
        name: str, action: Awaitable[Any], verify: Callable[[], tuple[bool, str]]
    ) -> None:
        try:
            await action
            ok, detail = verify()
            results.append((name, ok, detail))
        except Exception as exc:  # pylint: disable=broad-except
            results.append((name, False, f"raised {type(exc).__name__}: {exc}"))

    try:
        target_light_on = not original.light_on
        await check(
            "light(on=...)",
            fan.light(on=target_light_on),
            lambda: (
                fan.status.light_on == target_light_on,
                f"light_on={fan.status.light_on}",
            ),
        )

        target_brightness = 50 if original.light_brightness != 50 else 75
        await check(
            "light(brightness=...)",
            fan.light(brightness=target_brightness),
            lambda: (
                fan.status.light_brightness == target_brightness,
                f"light_brightness={fan.status.light_brightness}",
            ),
        )

        await check(
            "light(sleep=90) [set timer]",
            fan.light(sleep=90),
            lambda: (
                (
                    fan.status.light_timer
                    if relative_timers
                    else fan.status.light_sleep_timer
                )
                != 0,
                f"light_timer={fan.status.light_timer} "
                f"light_sleep_timer={fan.status.light_sleep_timer}",
            ),
        )
        await check(
            "light(sleep=0) [cancel timer]",
            fan.light(sleep=0),
            lambda: (
                (
                    fan.status.light_timer
                    if relative_timers
                    else fan.status.light_sleep_timer
                )
                == 0,
                f"light_timer={fan.status.light_timer} "
                f"light_sleep_timer={fan.status.light_sleep_timer}",
            ),
        )

        target_speed = 2 if original.fan_speed != 2 else 3
        await check(
            "fan(speed=...)",
            fan.fan(speed=target_speed),
            lambda: (
                fan.status.fan_speed == target_speed,
                f"fan_speed={fan.status.fan_speed}",
            ),
        )

        target_direction = (
            const.FAN_DIRECTION_REVERSE
            if original.fan_direction == const.FAN_DIRECTION_FORWARD
            else const.FAN_DIRECTION_FORWARD
        )
        await check(
            "fan(direction=...)",
            fan.fan(direction=target_direction),
            lambda: (
                fan.status.fan_direction == target_direction,
                f"fan_direction={fan.status.fan_direction}",
            ),
        )

        target_fan_on = not original.fan_on
        await check(
            "fan(on=...)",
            fan.fan(on=target_fan_on),
            lambda: (
                fan.status.fan_on == target_fan_on,
                f"fan_on={fan.status.fan_on}",
            ),
        )

        await check(
            "fan(sleep=90) [set timer]",
            fan.fan(sleep=90),
            lambda: (
                (
                    fan.status.fan_timer
                    if relative_timers
                    else fan.status.fan_sleep_timer
                )
                != 0,
                f"fan_timer={fan.status.fan_timer} "
                f"fan_sleep_timer={fan.status.fan_sleep_timer}",
            ),
        )
        await check(
            "fan(sleep=0) [cancel timer]",
            fan.fan(sleep=0),
            lambda: (
                (
                    fan.status.fan_timer
                    if relative_timers
                    else fan.status.fan_sleep_timer
                )
                == 0,
                f"fan_timer={fan.status.fan_timer} "
                f"fan_sleep_timer={fan.status.fan_sleep_timer}",
            ),
        )

        if supports_wind:
            target_wind_speed = 2 if original.wind_speed != 2 else 1
            await check(
                "fan(wind=True, wind_speed=...) [breeze mode]",
                fan.fan(wind=True, wind_speed=target_wind_speed),
                lambda: (
                    bool(fan.status.wind)
                    and fan.status.wind_speed == target_wind_speed,
                    f"wind={fan.status.wind} wind_speed={fan.status.wind_speed}",
                ),
            )
            await check(
                "fan(wind=False) [breeze mode off]",
                fan.fan(wind=False),
                lambda: (not fan.status.wind, f"wind={fan.status.wind}"),
            )
        else:
            out.append("- ⏭️ Breeze mode: not supported on this device (skipped)")

        await check(
            "away(True)",
            fan.away(True),
            lambda: (
                bool(fan.status.away_mode_enabled),
                f"away_mode_enabled={fan.status.away_mode_enabled}",
            ),
        )
        await check(
            "away(False)",
            fan.away(False),
            lambda: (
                not fan.status.away_mode_enabled,
                f"away_mode_enabled={fan.status.away_mode_enabled}",
            ),
        )
    finally:
        # The test sequence above always ends by canceling both sleep timers
        # (sleep=0). If either was already counting down before testing
        # started, re-arm it below for roughly the time remaining.
        if relative_timers:
            original_light_timer = original.light_timer or 0
            original_fan_timer = original.fan_timer or 0
        else:
            now_epoch = int(datetime.now().timestamp())
            original_light_timer = max(0, (original.light_sleep_timer or 0) - now_epoch)
            original_fan_timer = max(0, (original.fan_sleep_timer or 0) - now_epoch)

        restore_error = None
        try:
            await fan.light(on=original.light_on, brightness=original.light_brightness)
            fan_kwargs: dict[str, Any] = {
                "on": original.fan_on,
                "speed": original.fan_speed,
                "direction": original.fan_direction,
            }
            if supports_wind:
                fan_kwargs["wind"] = original.wind
                fan_kwargs["wind_speed"] = original.wind_speed
            await fan.fan(**fan_kwargs)
            await fan.away(original.away_mode_enabled)
            if original_light_timer:
                await fan.light(sleep=original_light_timer)
            if original_fan_timer:
                await fan.fan(sleep=original_fan_timer)
        except Exception as exc:  # pylint: disable=broad-except
            restore_error = exc

        restored = fan.status
        restore_checks = {
            "light_on": (restored.light_on, original.light_on),
            "light_brightness": (restored.light_brightness, original.light_brightness),
            "fan_on": (restored.fan_on, original.fan_on),
            "fan_speed": (restored.fan_speed, original.fan_speed),
            "fan_direction": (restored.fan_direction, original.fan_direction),
            "away_mode_enabled": (
                restored.away_mode_enabled,
                original.away_mode_enabled,
            ),
        }
        fully_restored = restore_error is None and all(
            got == want for got, want in restore_checks.values()
        )

        out.append("\n#### Test results\n")
        for name, ok, detail in results:
            out.append(f"- {'✅' if ok else '❌'} `{name}` — {detail}")

        out.append("\n#### Restore state\n")
        if restore_error is not None:
            out.append(
                f"❌ **Restore failed:** raised {type(restore_error).__name__}: "
                f"{restore_error}. **The device may be left in a modified "
                "state — please check it manually.**"
            )
        else:
            out.append(
                "✅ Fully restored to original state."
                if fully_restored
                else "❌ **State did not fully restore — check the device manually:**"
            )
            if not fully_restored:
                for field, (got, want) in restore_checks.items():
                    if got != want:
                        out.append(f"  - `{field}`: expected `{want}`, got `{got}`")
            if original_light_timer or original_fan_timer:
                out.append(
                    "  - Note: a sleep timer was already running before "
                    "testing started; it was re-armed for approximately "
                    "the remaining time, not restored to the exact original "
                    "value."
                )

    return out


async def gather_report(
    host: str,
    port: int,
    tls: bool,
    username: str = "",
    password: str = "",
    active: bool = False,
) -> str:
    """Connect to a fan and build the full Markdown diagnostic report."""
    out = []
    out.append("## aiomodernforms device diagnostic report")
    out.append(f"\n- Library version: `{__version__}`")
    out.append("- Host: *(redacted — LAN address, not useful in a bug report)*")

    async with aiomodernforms.ModernFormsDevice(
        host, port=port, tls=tls, username=username, password=password
    ) as fan:
        try:
            static_raw = await fan._request(  # pylint: disable=protected-access
                {const.COMMAND_QUERY_STATIC_DATA: True}
            )
            dynamic_raw = await fan._request()  # pylint: disable=protected-access
        except aiomodernforms.ModernFormsError as err:
            out.append(f"\n**Could not reach the device's `/mf` endpoint:** `{err}`")
            return "\n".join(out)

        device = Device(state_data=dynamic_raw, info_data=static_raw)
        fan._device = device  # pylint: disable=protected-access

        out.append(_section("Parsed capability flags"))
        out.append(f"- `has_wind()` (Breeze mode support): `{device.has_wind()}`")
        out.append(
            "- `has_relative_timers()` (Gen 3 seconds-until-off sleep timers): "
            f"`{device.has_relative_timers()}`"
        )

        out.append(_section("Raw static shadow data (queryStaticShadowData)"))
        out.append(_json_block(redact(static_raw)))
        extra = list(unknown_keys(static_raw, STATIC_KNOWN_KEYS))
        if extra:
            out.append(f"\n**Unrecognized keys:** `{extra}`")

        out.append(_section("Raw dynamic shadow data (queryDynamicShadowData)"))
        out.append(_json_block(redact(dynamic_raw)))
        extra = list(unknown_keys(dynamic_raw, DYNAMIC_KNOWN_KEYS))
        if extra:
            out.append(f"\n**Unrecognized keys:** `{extra}`")

        out.append(_section("Raw /config-read data"))
        try:
            config_raw = await fan._request(  # pylint: disable=protected-access
                commands={}, path=const.CONFIG_READ_API_ENDPOINT
            )
            out.append(_json_block(redact(config_raw)))
            extra = list(unknown_keys(config_raw, CONFIG_KNOWN_KEYS))
            if extra:
                out.append(f"\n**Unrecognized keys:** `{extra}`")
            config = ConfigInfo.from_dict(config_raw)
            if not config.wifi_strength:
                out.append(
                    "\n**Note:** `wifi_strength` came back empty — this "
                    "firmware may use a Wi-Fi signal key this library "
                    "doesn't recognize yet."
                )
        except aiomodernforms.ModernFormsError as err:
            out.append(f"`/config-read` request failed: `{err}`")

        if active:
            out.extend(await run_active_tests(fan))

    return "\n".join(out)


def main() -> None:
    """Parse arguments and print the diagnostic report."""
    parser = argparse.ArgumentParser(
        description=(
            "Connect to a Modern Forms / WAC fan and print a redacted "
            "diagnostic report suitable for a GitHub issue."
        )
    )
    parser.add_argument("host", help="IP address or hostname of the fan")
    parser.add_argument("--port", type=int, default=80, help="default: 80")
    parser.add_argument("--tls", action="store_true", help="use HTTPS")
    parser.add_argument("--username", default="")
    parser.add_argument("--password", default="")
    parser.add_argument(
        "--active",
        action="store_true",
        help=(
            "also exercise light/fan/breeze/away controls (reversible; "
            "original state is restored afterward). Never runs reboot, "
            "factory_reset, decommission, clear_paired_devices, "
            "enable_pairing_mode, set_schedule, or adaptive_learning."
        ),
    )
    args = parser.parse_args()

    if args.active:
        print(
            "WARNING: --active will change this fan's light/fan/breeze/away "
            "state while testing. Original state is restored afterward.",
            file=sys.stderr,
        )

    report = asyncio.run(
        gather_report(
            args.host,
            args.port,
            args.tls,
            args.username,
            args.password,
            args.active,
        )
    )
    print(report)


if __name__ == "__main__":
    main()
