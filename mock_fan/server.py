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
    GEN4_DEVICE_HARD_FACTORY_RESET,
    GEN4_FIELD_ACTION,
    GEN4_FIELD_ADDR,
    GEN4_FIELD_FIXTURE_LIST,
    GEN4_FIELD_STATE,
    GEN4_FIXTURE_ACTION_CONTROL,
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
    STATE_AWAY_MODE,
)

from .gen4 import Gen4FanState, device_data
from .generations import GenerationProfile
from .state import FanState

# Far longer than any sane client timeout, so a held connection is
# effectively dead from the client's point of view; short enough that an
# abandoned handler task doesn't linger indefinitely if never cancelled.
DISCONNECT_HOLD_SECS = 300

DEVICE_NAME = "Mock Fan"

_LOGGER = logging.getLogger(__name__)


def _unresponsive_after(
    loop: asyncio.AbstractEventLoop, resume_delay_secs: float
) -> float:
    """Return the loop-time deadline after which a fan resumes responding."""
    return loop.time() + resume_delay_secs


async def _hold_connection() -> None:
    """Hold a connection open long enough to look disconnected to any client."""
    await asyncio.sleep(DISCONNECT_HOLD_SECS)


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


class MockGen4Fan:
    """Holds a mock Gen4 fan's fixture state and its simulated-disconnect window."""

    def __init__(self, lights: int, resume_delay_secs: float) -> None:
        """Initialize Gen4 fixture state for the given light count."""
        self.state = Gen4FanState(lights=lights)
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
        await _hold_connection()

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
        fan.unresponsive_until = _unresponsive_after(loop, fan.resume_delay_secs)
        _LOGGER.info(
            "%s received — disconnecting for %.1fs", trigger, fan.resume_delay_secs
        )
        await _hold_connection()

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


async def _handle_device(request: web.Request) -> web.Response:
    """Handle POST /device: query/awayModeEnabled, reboot, hardFactoryReset."""
    fan: MockGen4Fan = request.app["gen4_fan"]
    loop = asyncio.get_running_loop()

    if loop.time() < fan.unresponsive_until:
        _LOGGER.info(
            "request received while unresponsive (simulated disconnect) —"
            " holding connection"
        )
        await _hold_connection()

    body = await request.json()

    if body.get(GEN4_DEVICE_HARD_FACTORY_RESET) or body.get(COMMAND_REBOOT):
        if body.get(GEN4_DEVICE_HARD_FACTORY_RESET):
            trigger = "hardFactoryReset"
            fan.state.reset()
        else:
            trigger = "reboot"
        fan.unresponsive_until = _unresponsive_after(loop, fan.resume_delay_secs)
        _LOGGER.info(
            "%s received — disconnecting for %.1fs", trigger, fan.resume_delay_secs
        )
        await _hold_connection()

    if isinstance(body.get(STATE_AWAY_MODE), bool):
        fan.state.away_mode_enabled = body[STATE_AWAY_MODE]

    return web.json_response(device_data(fan.state.away_mode_enabled))


async def _handle_fixture(request: web.Request) -> web.Response:
    """Handle POST /fixture: read-all, read-one, and control."""
    fan: MockGen4Fan = request.app["gen4_fan"]
    loop = asyncio.get_running_loop()

    if loop.time() < fan.unresponsive_until:
        _LOGGER.info(
            "request received while unresponsive (simulated disconnect) —"
            " holding connection"
        )
        await _hold_connection()

    body = await request.json()
    action = body.get(GEN4_FIELD_ACTION)
    addr = body.get(GEN4_FIELD_ADDR)

    # Any action value other than GEN4_FIXTURE_ACTION_CONTROL (in practice
    # always the documented "read" action, 3) falls through to the read
    # branches below — hence no read-action constant is imported here.
    if action == GEN4_FIXTURE_ACTION_CONTROL and addr is not None:
        fixture = fan.state.find(addr)
        if fixture is None:
            return web.json_response(
                {GEN4_FIELD_ACTION: action, "result": "-2"}, status=400
            )
        changed = fixture.apply_commands(body.get(GEN4_FIELD_STATE, {}))
        _LOGGER.info("fixture %s applied changes: %s", addr, changed)
        return web.json_response(
            {GEN4_FIELD_ACTION: action, "result": "0", GEN4_FIELD_STATE: changed}
        )

    if addr is not None:
        fixture = fan.state.find(addr)
        if fixture is None:
            return web.json_response(
                {GEN4_FIELD_ACTION: action, "result": "-2"}, status=400
            )
        _LOGGER.info("fixture %s read request", addr)
        return web.json_response(
            {GEN4_FIELD_ACTION: action, "result": "0", **fixture.as_wire_dict()}
        )

    fixtures = fan.state.all_fixtures()
    _LOGGER.info("fixture read-all request (%d fixtures)", len(fixtures))
    return web.json_response(
        {
            GEN4_FIELD_ACTION: action,
            "result": "0",
            "count": len(fixtures),
            GEN4_FIELD_FIXTURE_LIST: [f.as_wire_dict() for f in fixtures],
        }
    )


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


def create_gen4_app(
    lights: int = 1, resume_delay_secs: float = 5.0
) -> web.Application:
    """Build the aiohttp application for a mock Gen4 fan."""
    app = web.Application()
    app["gen4_fan"] = MockGen4Fan(lights=lights, resume_delay_secs=resume_delay_secs)
    app.router.add_post("/device", _handle_device)
    app.router.add_post("/fixture", _handle_fixture)
    return app
