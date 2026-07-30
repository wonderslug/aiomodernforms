"""aiohttp server emulating the Modern Forms fan wire protocol."""

from __future__ import annotations

import asyncio
import logging

from aiohttp import web

from aiomodernforms.const import (
    COMMAND_DECOMMISSION,
    COMMAND_FACTORY_RESET,
    COMMAND_QUERY_STATIC_DATA,
    COMMAND_REBOOT,
    INFO_BRAND,
    INFO_CLIENT_ID,
    INFO_DATE_CODE,
    INFO_DEVICE_NAME,
    INFO_FAN_MOTOR_TYPE,
    INFO_FAN_TYPE,
    INFO_FEDERATED_IDENTITY,
    INFO_FIRMWARE_URL,
    INFO_FIRMWARE_VERSION,
    INFO_LIGHT_TYPE,
    INFO_MAC,
    INFO_MAIN_MCU_FIRMWARE_VERSION,
    INFO_OWNER,
    INFO_PRODUCT_SKU,
    INFO_PRODUCTION_LOT_NUMBER,
)

from .generations import GenerationProfile
from .state import FanState

# Far longer than any sane client timeout, so a held connection is
# effectively dead from the client's point of view; short enough that an
# abandoned handler task doesn't linger indefinitely if never cancelled.
DISCONNECT_HOLD_SECS = 300

DEVICE_NAME = "Mock Fan"

_LOGGER = logging.getLogger(__name__)


def _static_info(profile: GenerationProfile, light: bool) -> dict[str, object]:
    """Build the static shadow (queryStaticShadowData) response for a profile.

    lightType is omitted (reported as "") when light=False, so the static
    info and dynamic shadow always agree on whether the fan has a light —
    matching how a real fan-only unit has no light kit installed at all.
    """
    info: dict[str, object] = {
        INFO_CLIENT_ID: profile.client_id,
        INFO_MAC: profile.mac,
        INFO_LIGHT_TYPE: profile.light_type if light else "",
        INFO_FAN_TYPE: profile.fan_type,
        INFO_FAN_MOTOR_TYPE: profile.fan_motor_type,
        INFO_PRODUCTION_LOT_NUMBER: "",
        INFO_PRODUCT_SKU: "",
        INFO_OWNER: "mock@example.com",
        INFO_FEDERATED_IDENTITY: "us-east-1:00000000-0000-0000-0000-000000000000",
        INFO_DEVICE_NAME: DEVICE_NAME,
        INFO_FIRMWARE_VERSION: profile.firmware_version,
        INFO_MAIN_MCU_FIRMWARE_VERSION: profile.main_mcu_firmware_version,
        INFO_FIRMWARE_URL: "",
    }
    if profile.brand is not None:
        info[INFO_BRAND] = profile.brand
        info[INFO_DATE_CODE] = profile.date_code
    return info


class MockFan:
    """Holds a mock fan's state and its simulated-disconnect window."""

    def __init__(
        self,
        profile: GenerationProfile,
        breeze: bool,
        resume_delay_secs: float,
        light: bool = True,
    ) -> None:
        """Initialize the mock fan's state for the given profile/breeze/light."""
        self.profile = profile
        self.light = light
        self.state = FanState(profile, breeze, light)
        self.resume_delay_secs = resume_delay_secs
        self.unresponsive_until: float = 0.0


async def _handle_mf(request: web.Request) -> web.Response:
    """Handle POST /mf: static info queries, state queries, and commands."""
    fan: MockFan = request.app["fan"]
    loop = asyncio.get_running_loop()

    if loop.time() < fan.unresponsive_until:
        _LOGGER.info(
            "request received while unresponsive (simulated disconnect) —"
            " holding connection"
        )
        await asyncio.sleep(DISCONNECT_HOLD_SECS)

    commands = await request.json()

    if commands.get(COMMAND_QUERY_STATIC_DATA):
        _LOGGER.info("static info request")
        return web.json_response(_static_info(fan.profile, fan.light))

    disruptive = (
        commands.get(COMMAND_FACTORY_RESET)
        or commands.get(COMMAND_DECOMMISSION)
        or commands.get(COMMAND_REBOOT)
    )
    if disruptive:
        if commands.get(COMMAND_FACTORY_RESET):
            trigger = "factoryReset"
            fan.state.reset()
        elif commands.get(COMMAND_DECOMMISSION):
            trigger = "decommission"
            fan.state.reset()
        else:
            trigger = "reboot"
        fan.unresponsive_until = loop.time() + fan.resume_delay_secs
        _LOGGER.info(
            "%s received — disconnecting for %.1fs", trigger, fan.resume_delay_secs
        )
        await asyncio.sleep(DISCONNECT_HOLD_SECS)

    before = fan.state.snapshot()
    shadow = fan.state.apply_commands(commands)
    changed = {key: value for key, value in shadow.items() if before.get(key) != value}
    if changed:
        _LOGGER.info("applied changes: %s", changed)
    else:
        _LOGGER.info("status read (no changes)")
    return web.json_response(shadow)


async def _handle_config_read(request: web.Request) -> web.Response:
    """Handle POST /config-read: generation-specific config info."""
    fan: MockFan = request.app["fan"]
    _LOGGER.info("config-read request")
    return web.json_response(fan.profile.config_read_response)


def create_app(
    profile: GenerationProfile,
    breeze: bool,
    light: bool = True,
    resume_delay_secs: float = 5.0,
) -> web.Application:
    """Build the aiohttp application for a mock fan of the given profile."""
    app = web.Application()
    app["fan"] = MockFan(profile, breeze, resume_delay_secs, light=light)
    app.router.add_post("/mf", _handle_mf)
    app.router.add_post("/config-read", _handle_config_read)
    return app
