"""Async IO client library for Modern Forms fans."""

from __future__ import annotations

import asyncio
import json
import socket
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any

import aiohttp
import backoff  # type: ignore
from yarl import URL

from . import gen4
from .__version__ import __version__
from .const import (
    COMMAND_ADAPTIVE_LEARNING,
    COMMAND_AWAY_MODE,
    COMMAND_DECOMMISSION,
    COMMAND_FACTORY_RESET,
    COMMAND_FAN_DIRECTION,
    COMMAND_FAN_POWER,
    COMMAND_FAN_SLEEP_TIMER,
    COMMAND_FAN_SPEED,
    COMMAND_FAN_TIMER,
    COMMAND_IDENTIFY,
    COMMAND_LIGHT_BRIGHTNESS,
    COMMAND_LIGHT_COLOR_TEMP,
    COMMAND_LIGHT_POWER,
    COMMAND_LIGHT_SLEEP_TIMER,
    COMMAND_LIGHT_TIMER,
    COMMAND_QUERY_STATIC_DATA,
    COMMAND_QUERY_STATUS,
    COMMAND_REBOOT,
    COMMAND_RESET_RF_PAIR_LIST,
    COMMAND_RF_PAIR_MODE,
    COMMAND_SCHEDULE,
    COMMAND_WIND,
    COMMAND_WIND_SPEED,
    CONFIG_READ_API_ENDPOINT,
    DEFAULT_API_ENDPOINT,
    DEFAULT_PORT,
    DEFAULT_TIMEOUT_SECS,
    FAN_DIRECTION_FORWARD,
    FAN_DIRECTION_REVERSE,
    FAN_SPEED_HIGH_VALUE,
    FAN_SPEED_LOW_VALUE,
    GEN4_DEVICE_API_ENDPOINT,
    GEN4_DEVICE_HARD_FACTORY_RESET,
    GEN4_DEVICE_IOTM_VER,
    GEN4_DEVICE_NAME,
    GEN4_DEVICE_NWK_STATE,
    GEN4_DEVICE_QUERY,
    GEN4_DEVICE_SCM_VER,
    GEN4_DEVICE_SYSTEM_TYPE,
    GEN4_FIELD_ACTION,
    GEN4_FIELD_ADDR,
    GEN4_FIELD_DETAIL,
    GEN4_FIELD_FIXTURE_LIST,
    GEN4_FIELD_STATE,
    GEN4_FIXTURE_ACTION_CONTROL,
    GEN4_FIXTURE_ACTION_READ,
    GEN4_FIXTURE_API_ENDPOINT,
    GEN4_NWK_CERTIFICATE_ID,
    GEN4_NWK_RSSI,
    LIGHT_BRIGHTNESS_HIGH_VALUE,
    LIGHT_BRIGHTNESS_LOW_VALUE,
    SLEEP_TIMER_CANCEL,
    STATE_AWAY_MODE,
    STATE_LIGHT_BRIGHTNESS,
    STATE_LIGHT_COLOR_TEMP,
    STATE_LIGHT_FIXTURES,
    STATE_LIGHT_POWER,
    WIND_SPEED_HIGH_VALUE,
    WIND_SPEED_LOW_VALUE,
)
from .exceptions import (
    ModernFormsConnectionError,
    ModernFormsConnectionTimeoutError,
    ModernFormsEmptyResponseError,
    ModernFormsError,
    ModernFormsInvalidSettingsError,
    ModernFormsNotInitializedError,
    ModernFormsNotSupportedError,
)
from .models import ConfigInfo, Device, Generation


class ModernFormsDevice:
    """Modern Forms device reppresentation."""

    _device: Device | None = None

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        base_path: str = "/",
        username: str = "",
        password: str = "",
        request_timeout: float = DEFAULT_TIMEOUT_SECS,
        session: aiohttp.client.ClientSession | None = None,
        tls: bool = False,
        verify_ssl: bool = True,
        user_agent: str = None,  # type: ignore
    ) -> None:
        """Initialize connection with Modern Forms Fan."""
        self._session = session
        self._close_session = False
        self._base_path = base_path
        self._host = host
        self._password = password
        self._port = port
        self._socketaddr = None
        self._request_timeout = request_timeout
        self._tls = tls
        self._username = username
        self._verify_ssl = verify_ssl
        self._user_agent = user_agent

        if self._user_agent is None:
            self._user_agent = f"AIOModernForms/{__version__}"

        if self._base_path[-1] != "/":
            self._base_path += "/"

        self._is_gen4: bool | None = None
        self._gen4_fan_addr: int | None = None

    @backoff.on_exception(
        backoff.expo, ModernFormsEmptyResponseError, max_tries=3, logger=None
    )
    async def update(self, full_update: bool = False) -> Device:
        """Get all information about the device in a single call."""
        if self._is_gen4:
            await self._update_gen4(full_update=full_update)
            return self._device  # type: ignore[return-value]
        if self._is_gen4 is False:
            return await self._update_legacy(full_update=full_update)

        # Generation not yet known: try the long-supported /mf endpoint
        # first (so every existing legacy fan keeps working exactly as
        # before, with no extra request), and only probe /device for Gen4
        # if that fails.
        try:
            result = await self._update_legacy(full_update=full_update)
        except ModernFormsError:
            device_data = await self._probe_gen4()
            if device_data is not None:
                self._is_gen4 = True
                await self._update_gen4(
                    full_update=full_update, device_data=device_data
                )
                return self._device  # type: ignore[return-value]
            raise
        self._is_gen4 = False
        return result

    async def _update_legacy(self, full_update: bool = False) -> Device:
        """Gen 1/2/3 update() body — the flat /mf shadow protocol."""
        info_data = await self._request({COMMAND_QUERY_STATIC_DATA: True})
        state_data = await self._request()
        if not state_data:
            raise ModernFormsEmptyResponseError(
                f"Modern Forms device at {self._host}"
                + " returned an empty API response on full update"
            )
        if self._device is None or full_update:
            self._device = Device(state_data=state_data, info_data=info_data)
        self._device.update_from_dict(state_data=state_data)
        return self._device

    async def _probe_gen4(self) -> dict[str, Any] | None:
        """Fetch /device, returning its data if it identifies a Gen4 fan.

        Returns the fetched device data (rather than a plain bool) so a
        successful probe's response can be reused by _update_gen4() as
        part of the same first-detection pass, instead of fetching /device
        a second time.
        """
        try:
            device_data = await self._request(
                {GEN4_DEVICE_QUERY: True}, path=GEN4_DEVICE_API_ENDPOINT
            )
        except (ModernFormsError, aiohttp.ClientError):
            # Best-effort probe: a non-JSON body (HTML error page, captive
            # portal, any non-fan device on this host) raises aiohttp's own
            # exception from response.json() rather than a library one,
            # since that call sits outside _request()'s normal
            # aiohttp.ClientError-to-ModernFormsError translation. Either
            # failure just means "not confirmed Gen4" here.
            return None
        system_type = device_data.get(GEN4_DEVICE_SYSTEM_TYPE, "")
        if gen4.is_gen4_system_type(system_type):
            return device_data  # type: ignore[no-any-return]
        return None

    async def _update_gen4(
        self,
        full_update: bool = False,
        device_data: dict[str, Any] | None = None,
    ) -> None:
        """Gen4 equivalent of _update_legacy() — the /device + /fixture protocol.

        `device_data` lets a caller that already fetched /device (i.e.
        `_probe_gen4()`, on first detection) pass it straight through
        instead of this method fetching /device a second time.
        """
        if device_data is None:
            device_data = await self._request(
                {GEN4_DEVICE_QUERY: True}, path=GEN4_DEVICE_API_ENDPOINT
            )
        fixture_response = await self._request(
            {GEN4_FIELD_ACTION: GEN4_FIXTURE_ACTION_READ},
            path=GEN4_FIXTURE_API_ENDPOINT,
        )
        fixtures = fixture_response.get(GEN4_FIELD_FIXTURE_LIST, [])
        fixtures = await self._fill_gen4_fixture_state(fixtures)
        fan_fixture, light_fixtures = gen4.classify_fixtures(fixtures)
        self._gen4_fan_addr = (fan_fixture or {}).get(GEN4_FIELD_ADDR)

        state_data = gen4.build_state_data(device_data, fan_fixture, light_fixtures)
        info_data = gen4.build_info_data(device_data, fan_fixture, light_fixtures)

        if self._device is None or full_update:
            self._device = Device(
                state_data=state_data, info_data=info_data, generation=Generation.GEN4
            )
        else:
            self._device.update_from_dict(
                state_data=state_data, generation=Generation.GEN4
            )

    async def _fill_gen4_fixture_state(
        self, fixtures: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Fill in each fixture's `state`/`detail` via an individual read.

        The PDF documents `/fixture` read-all (`action: 3`, no `addr`) as
        returning each fixture's current `state` alongside its identity.
        Real Gen4 hardware doesn't: read-all there returns only
        `addr`/`type`/`name`/`model`/`online`, leaving `state` absent
        (confirmed against a real Radiant fan, see GitHub issue #287).
        Fixtures that already carry a `state` key are left as-is, so this
        costs no extra requests against a device that does follow the PDF.
        """
        filled: list[dict[str, Any]] = []
        for fixture in fixtures:
            if GEN4_FIELD_STATE in fixture:
                filled.append(fixture)
                continue
            addr = fixture.get(GEN4_FIELD_ADDR)
            if addr is None:
                filled.append(fixture)
                continue
            single = await self._request(
                {GEN4_FIELD_ACTION: GEN4_FIXTURE_ACTION_READ, GEN4_FIELD_ADDR: addr},
                path=GEN4_FIXTURE_API_ENDPOINT,
            )
            merged = dict(fixture)
            if GEN4_FIELD_STATE in single:
                merged[GEN4_FIELD_STATE] = single[GEN4_FIELD_STATE]
            if GEN4_FIELD_DETAIL in single:
                merged[GEN4_FIELD_DETAIL] = single[GEN4_FIELD_DETAIL]
            filled.append(merged)
        return filled

    @backoff.on_exception(
        backoff.expo, ModernFormsConnectionError, max_tries=3, logger=None
    )
    async def _request(
        self, commands: dict | None = None, path: str = DEFAULT_API_ENDPOINT
    ) -> Any:
        """Handle a request to a Modern Forms Fan device."""
        scheme = "https" if self._tls else "http"
        url = URL.build(
            scheme=scheme,
            host=self._host,
            port=self._port,
            path=self._base_path + path,
        )

        auth = None
        if self._username and self._password:
            auth = aiohttp.BasicAuth(self._username, self._password)

        headers = {
            "User-Agent": self._user_agent,
            "Accept": "application/json",
        }

        if self._session is None:
            self._session = aiohttp.ClientSession()
            self._close_session = True

        # If updating the state, always request for a state response
        if commands is None:
            commands = {COMMAND_QUERY_STATUS: True}

        try:
            async with asyncio.timeout(self._request_timeout):
                response = await self._session.request(
                    "POST",
                    url,
                    auth=auth,
                    json=commands,
                    headers=headers,
                    ssl=self._verify_ssl,
                )
        except TimeoutError as exception:
            raise ModernFormsConnectionTimeoutError(
                "Timeout occurred while connecting to Modern Forms device at"
                + f" {self._host}"
            ) from exception
        except (aiohttp.ClientError, socket.gaierror) as exception:
            raise ModernFormsConnectionError(
                "Error occurred while communicating with Modern Forms device at"
                + f" {self._host}"
            ) from exception

        content_type = response.headers.get("Content-Type", "")
        if (response.status // 100) in [4, 5]:
            contents = await response.read()
            response.close()

            if content_type == "application/json":
                raise ModernFormsError(
                    response.status, json.loads(contents.decode("utf8"))
                )
            raise ModernFormsError(
                response.status, {"message": contents.decode("utf8")}
            )

        data = await response.json()
        return data

    async def request(self, commands: dict | None = None):
        """Issue one or more commands to the Modern Forms fan."""
        if self._device is None:
            await self.update()
        data = await self._request(commands=commands)
        self._device.update_from_dict(state_data=data)  # type: ignore
        return self._device.state  # type: ignore

    @property
    def status(self):
        """Fan get status."""
        if self._device is None:
            raise ModernFormsNotInitializedError(
                "The device has not been initialized.  "
                + "Please run update on the device before getting state"
            )
        return self._device.state

    @property
    def info(self):
        """Fan get info."""
        if self._device is None:
            raise ModernFormsNotInitializedError(
                "The device has not been initialized.  "
                + "Please run update on the device before getting info"
            )
        return self._device.info

    async def config(self) -> ConfigInfo:
        """Retrieve config-read data.

        Includes hardware revision, RF library version, certificate ID,
        and current Wi-Fi signal strength.
        """
        if self._device is not None and self._device.generation == Generation.GEN4:
            device_data = await self._request(
                {GEN4_DEVICE_QUERY: True}, path=GEN4_DEVICE_API_ENDPOINT
            )
            nwk_state = device_data.get(GEN4_DEVICE_NWK_STATE) or {}
            return ConfigInfo(
                device_name=device_data.get(GEN4_DEVICE_NAME, ""),
                protocol="",
                hardware_revision="",
                firmware_version=device_data.get(GEN4_DEVICE_IOTM_VER, ""),
                rf_version=device_data.get(GEN4_DEVICE_SCM_VER, ""),
                certificate_id=nwk_state.get(GEN4_NWK_CERTIFICATE_ID, ""),
                wifi_strength=str(nwk_state.get(GEN4_NWK_RSSI, "")),
            )

        config_data = await self._request(commands={}, path=CONFIG_READ_API_ENDPOINT)
        return ConfigInfo.from_dict(config_data)

    def has_breeze_mode(self):
        """See if the Fan has Breeze Mode."""
        if self._device is None:
            raise ModernFormsNotInitializedError(
                "The device has not been initialized.  "
                + "Please run update on the device before getting state"
            )
        return self._device.has_wind()

    def has_relative_timers(self):
        """See if the Fan uses relative (seconds-until-off) sleep timers."""
        if self._device is None:
            raise ModernFormsNotInitializedError(
                "The device has not been initialized.  "
                + "Please run update on the device before getting state"
            )
        return self._device.has_relative_timers()

    def has_identify(self):
        """See if the Fan supports the identify/findme function (Gen4 only)."""
        if self._device is None:
            raise ModernFormsNotInitializedError(
                "The device has not been initialized.  "
                + "Please run update on the device before getting state"
            )
        return self._device.has_identify()

    def has_adaptive_learning(self):
        """See if the Fan supports adaptive learning (not available on Gen4)."""
        if self._device is None:
            raise ModernFormsNotInitializedError(
                "The device has not been initialized.  "
                + "Please run update on the device before getting state"
            )
        return self._device.has_adaptive_learning()

    def has_sleep_timer(self):
        """See if the Fan supports sleep timers at all (not available on Gen4)."""
        if self._device is None:
            raise ModernFormsNotInitializedError(
                "The device has not been initialized.  "
                + "Please run update on the device before getting state"
            )
        return self._device.has_sleep_timer()

    def _sleep_command(
        self, epoch_command: str, relative_command: str, sleep: int | datetime
    ) -> dict[str, int]:
        """Build the timer command for `sleep`.

        Gen 1/2 fans store sleep timers as an epoch timestamp under
        `epoch_command`. Gen 3 fans store them as seconds-until-off under
        `relative_command`. Which one a given device uses is only knowable
        after `update()` has populated `has_relative_timers()`; before that,
        epoch semantics (the historical default) are used.
        """
        use_relative = self._device is not None and self._device.has_relative_timers()
        command = relative_command if use_relative else epoch_command

        if isinstance(sleep, int):
            if sleep <= 0:
                return {command: SLEEP_TIMER_CANCEL}
            if use_relative:
                return {command: sleep}
            sleep_till = datetime.now() + timedelta(seconds=sleep)
            return {command: int(sleep_till.timestamp())}

        if isinstance(sleep, datetime) and not (
            sleep < datetime.now() or sleep > (datetime.now() + timedelta(hours=24))
        ):
            if use_relative:
                return {command: max(1, int((sleep - datetime.now()).total_seconds()))}
            return {command: int(sleep.timestamp())}

        raise ModernFormsInvalidSettingsError(
            "The time to sleep till must be a datetime object that is not more"
            + " then 24 hours into the future, or an interger for number of"
            + " seconds to sleep. 0 cancels the sleep timer."
        )

    def _apply_gen4_state_change(self, changes: dict[str, Any]) -> None:
        """Merge a partial canonical state change onto the cached State (Gen4)."""
        full = self._device.state.to_dict()  # type: ignore[union-attr]
        full.update(changes)
        self._device.update_from_dict(  # type: ignore[union-attr]
            state_data=full, generation=Generation.GEN4
        )

    def _apply_gen4_light_change(
        self, address: int | None, changes: dict[str, Any]
    ) -> None:
        """Merge a partial light-fixture state change onto the cached State (Gen4)."""
        lights = list(self._device.state.light_fixtures)  # type: ignore[union-attr]
        for i, light in enumerate(lights):
            if light.address == address:
                lights[i] = replace(
                    light,
                    on=changes.get(STATE_LIGHT_POWER, light.on),
                    brightness=changes.get(STATE_LIGHT_BRIGHTNESS, light.brightness),
                    color_temp_kelvin=changes.get(
                        STATE_LIGHT_COLOR_TEMP, light.color_temp_kelvin
                    ),
                )
                break

        full = self._device.state.to_dict()  # type: ignore[union-attr]
        full[STATE_LIGHT_FIXTURES] = lights
        if lights and lights[0].address == address:
            full[STATE_LIGHT_POWER] = lights[0].on
            full[STATE_LIGHT_BRIGHTNESS] = lights[0].brightness
            full[STATE_LIGHT_COLOR_TEMP] = lights[0].color_temp_kelvin
        self._device.update_from_dict(  # type: ignore[union-attr]
            state_data=full, generation=Generation.GEN4
        )

    async def light(
        self,
        *,
        brightness: int | None = None,
        on: bool | None = None,
        sleep: int | datetime | None = None,
        color_temp_kelvin: int | None = None,
        identify: bool | None = None,
    ):
        """Change Fans Light state — always controls the primary light.

        When both brightness and on=True are given on gen1_2/gen3, brightness
        is sent in its own request first to avoid the fan briefly flashing at
        the previous brightness. See issue #99. Gen4's /fixture endpoint
        applies a control request's state atomically, so this split is only
        needed for the legacy /mf protocol.
        """
        if self._device is None:
            await self.update()
        assert self._device is not None

        if not self._device.state.light_fixtures:
            raise ModernFormsNotSupportedError(
                "light() is not supported — this fan has no light fixtures"
            )

        address = self._device.state.light_fixtures[0].address

        if brightness is not None and (
            not isinstance(brightness, int)
            or int(brightness) < LIGHT_BRIGHTNESS_LOW_VALUE
            or int(brightness) > LIGHT_BRIGHTNESS_HIGH_VALUE
        ):
            raise ModernFormsInvalidSettingsError(
                "brightness value must be between"
                + f" {LIGHT_BRIGHTNESS_LOW_VALUE} and {LIGHT_BRIGHTNESS_HIGH_VALUE}"
            )

        if on is not None and not isinstance(on, bool):
            raise ModernFormsInvalidSettingsError("on must be a boolean")

        if sleep is not None and self._device.generation != Generation.GEN4:
            # Validate up front, before any request is sent below — the
            # brightness+on branch just below can send a brightness-only
            # request before ever reaching light_fixture()'s own sleep
            # validation, which would otherwise leave the device
            # half-mutated if `sleep` turns out to be invalid.
            self._sleep_command(COMMAND_LIGHT_SLEEP_TIMER, COMMAND_LIGHT_TIMER, sleep)

        if (
            brightness is not None
            and on is True
            and self._device.generation != Generation.GEN4
        ):
            # Setting brightness and turning on in a single request makes the
            # fan briefly show the previous brightness before jumping to the
            # new one. Sending brightness first avoids the flash.
            await self.light_fixture(address, brightness=brightness)
            await self.light_fixture(address, on=on, sleep=sleep, identify=identify)
            return

        await self.light_fixture(
            address,
            brightness=brightness,
            on=on,
            sleep=sleep,
            color_temp_kelvin=color_temp_kelvin,
            identify=identify,
        )

    async def light_fixture(
        self,
        address: int | None,
        *,
        brightness: int | None = None,
        on: bool | None = None,
        sleep: int | datetime | None = None,
        color_temp_kelvin: int | None = None,
        identify: bool | None = None,
    ):
        """Change one light fixture's state.

        `address` is a value from `status.light_fixtures[*].address` — pass
        `None` to target the gen1_2/gen3 synthetic entry (routes through the
        legacy /mf endpoint); pass a real address to control a specific
        Gen4 light fixture via /fixture.
        """
        if self._device is None:
            await self.update()
        assert self._device is not None

        if address is None and self._device.generation == Generation.GEN4:
            # None only ever means "the gen1_2/gen3 synthetic entry" — a
            # Gen4 device has no such thing, and sending {"addr": null} to
            # /fixture would silently no-op rather than erroring cleanly
            # (mock_fan's read-all branch, and likely real hardware too,
            # doesn't recognize it as a control request at all).
            raise ModernFormsInvalidSettingsError(
                "address must be a real fixture address on Gen4 — None"
                " only targets the gen1_2/gen3 synthetic light"
            )

        if address is not None and (
            not isinstance(address, int) or isinstance(address, bool)
        ):
            raise ModernFormsInvalidSettingsError("address must be an int or None")

        if brightness is not None and (
            not isinstance(brightness, int)
            or int(brightness) < LIGHT_BRIGHTNESS_LOW_VALUE
            or int(brightness) > LIGHT_BRIGHTNESS_HIGH_VALUE
        ):
            raise ModernFormsInvalidSettingsError(
                "brightness value must be between"
                + f" {LIGHT_BRIGHTNESS_LOW_VALUE} and {LIGHT_BRIGHTNESS_HIGH_VALUE}"
            )

        if on is not None and not isinstance(on, bool):
            raise ModernFormsInvalidSettingsError("on must be a boolean")

        if color_temp_kelvin is not None and (
            not isinstance(color_temp_kelvin, int)
            or isinstance(color_temp_kelvin, bool)
        ):
            raise ModernFormsInvalidSettingsError("color_temp_kelvin must be an int")

        if identify is not None and not isinstance(identify, bool):
            raise ModernFormsInvalidSettingsError("identify must be a boolean")

        sleep_commands: dict[str, int] = {}
        if sleep is not None and self._device.generation != Generation.GEN4:
            sleep_commands = self._sleep_command(
                COMMAND_LIGHT_SLEEP_TIMER, COMMAND_LIGHT_TIMER, sleep
            )

        commands: dict[str, bool | int] = {}
        if brightness is not None:
            commands[COMMAND_LIGHT_BRIGHTNESS] = brightness
        if on is not None:
            commands[COMMAND_LIGHT_POWER] = on
        if color_temp_kelvin is not None and self._device.generation == Generation.GEN4:
            # Color temperature control is Gen4-only; silently drop it for
            # gen1_2/gen3 rather than sending an unsupported /mf field.
            commands[COMMAND_LIGHT_COLOR_TEMP] = color_temp_kelvin
        if identify is not None and self._device.generation == Generation.GEN4:
            commands[COMMAND_IDENTIFY] = identify
        commands.update(sleep_commands)

        if self._device.generation == Generation.GEN4:
            wire_state = gen4.build_light_control_state(commands)
            if wire_state:
                response = await self._request(
                    {
                        "action": GEN4_FIXTURE_ACTION_CONTROL,
                        "addr": address,
                        "state": wire_state,
                    },
                    path=GEN4_FIXTURE_API_ENDPOINT,
                )
                changes = gen4.parse_light_control_response(response.get("state", {}))
                self._apply_gen4_light_change(address, changes)
            return

        await self.request(commands=commands)

    async def fan(
        self,
        *,
        on: bool | None = None,
        sleep: int | datetime | None = None,
        speed: int | None = None,
        direction: str | None = None,
        wind: bool | None = None,
        wind_speed: int | None = None,
        identify: bool | None = None,
    ):
        """Change Fans Fan state."""
        if self._device is None:
            await self.update()
        commands: dict[str, bool | int | str] = {}

        if speed is not None:
            if (
                not isinstance(speed, int)
                or int(speed) < FAN_SPEED_LOW_VALUE
                or int(speed) > FAN_SPEED_HIGH_VALUE
            ):
                raise ModernFormsInvalidSettingsError(
                    "speed value must be between"
                    + f" {FAN_SPEED_LOW_VALUE} and {FAN_SPEED_HIGH_VALUE}"
                )

            commands[COMMAND_FAN_SPEED] = speed

        if on is not None:
            if not isinstance(on, bool):
                raise ModernFormsInvalidSettingsError("on must be a boolean")

            commands[COMMAND_FAN_POWER] = on

        if identify is not None and not isinstance(identify, bool):
            raise ModernFormsInvalidSettingsError("identify must be a boolean")

        if (
            sleep is not None
            and self._device is not None
            and self._device.generation != Generation.GEN4
        ):
            commands.update(
                self._sleep_command(COMMAND_FAN_SLEEP_TIMER, COMMAND_FAN_TIMER, sleep)
            )

        if direction is not None:
            if not isinstance(direction, str) or direction not in [
                FAN_DIRECTION_FORWARD,
                FAN_DIRECTION_REVERSE,
            ]:
                raise ModernFormsInvalidSettingsError(
                    f"fan direction must be {FAN_DIRECTION_FORWARD}"
                    + f" or {FAN_DIRECTION_REVERSE}"
                )
            commands[COMMAND_FAN_DIRECTION] = direction

        if self._device is not None and self._device.has_wind():
            if wind_speed is not None:
                if (
                    not isinstance(wind_speed, int)
                    or int(wind_speed) < WIND_SPEED_LOW_VALUE
                    or int(wind_speed) > WIND_SPEED_HIGH_VALUE
                ):
                    raise ModernFormsInvalidSettingsError(
                        "wind_speed value must be between"
                        + f" {WIND_SPEED_LOW_VALUE} and {WIND_SPEED_HIGH_VALUE}"
                    )
                commands[COMMAND_WIND_SPEED] = wind_speed

            if wind is not None:
                if not isinstance(wind, bool):
                    raise ModernFormsInvalidSettingsError("wind must be a boolean")
                commands[COMMAND_WIND] = wind

        if (
            identify is not None
            and self._device is not None
            and self._device.generation == Generation.GEN4
        ):
            commands[COMMAND_IDENTIFY] = identify

        if self._device is not None and self._device.generation == Generation.GEN4:
            wire_state = gen4.build_fan_control_state(commands)
            if wire_state:
                if self._gen4_fan_addr is None:
                    # No fixture typed GEN4_FIXTURE_TYPE_FAN was found in
                    # the last /fixture read-all — sending {"addr": null}
                    # would silently no-op or confuse the device rather
                    # than erroring cleanly (same class of issue as
                    # light_fixture()'s address=None guard above).
                    raise ModernFormsNotSupportedError(
                        "fan() is not supported — no fan fixture was found"
                        " on this Gen4 device"
                    )
                response = await self._request(
                    {
                        "action": GEN4_FIXTURE_ACTION_CONTROL,
                        "addr": self._gen4_fan_addr,
                        "state": wire_state,
                    },
                    path=GEN4_FIXTURE_API_ENDPOINT,
                )
                changes = gen4.parse_fan_control_response(response.get("state", {}))
                self._apply_gen4_state_change(changes)
            return

        await self.request(commands=commands)

    async def away(self, away: bool):
        """Change the away state of the device."""
        if self._device is None:
            await self.update()

        if self._device is not None and self._device.generation == Generation.GEN4:
            response = await self._request(
                {COMMAND_AWAY_MODE: away}, path=GEN4_DEVICE_API_ENDPOINT
            )
            self._apply_gen4_state_change(
                {STATE_AWAY_MODE: response.get(STATE_AWAY_MODE, away)}
            )
            return

        await self.request(
            commands={COMMAND_AWAY_MODE: away, COMMAND_QUERY_STATUS: True}
        )

    async def adaptive_learning(self, adaptive_learning: bool):
        """Change the adaptive learning state of the device (no-op on Gen4)."""
        if self._device is None:
            await self.update()

        if self._device is not None and self._device.generation == Generation.GEN4:
            return

        await self.request(
            commands={
                COMMAND_ADAPTIVE_LEARNING: adaptive_learning,
                COMMAND_QUERY_STATUS: True,
            }
        )

    async def enable_pairing_mode(self, active: bool = True):
        """Toggle RF pairing mode, used to pair remotes or wall controls."""
        if self._device is None:
            await self.update()
        assert self._device is not None
        if self._device.generation == Generation.GEN4:
            raise ModernFormsNotSupportedError(
                "enable_pairing_mode() is not supported on Gen4 fans"
            )
        await self.request(commands={COMMAND_RF_PAIR_MODE: active})

    async def clear_paired_devices(self):
        """Clear all RF-paired devices (remotes, wall controls) from the fan."""
        if self._device is None:
            await self.update()
        assert self._device is not None
        if self._device.generation == Generation.GEN4:
            raise ModernFormsNotSupportedError(
                "clear_paired_devices() is not supported on Gen4 fans"
            )
        await self.request(commands={COMMAND_RESET_RF_PAIR_LIST: True})

    async def factory_reset(self):
        """Reset the fan to factory defaults.

        Clears Wi-Fi credentials, decommissions the fan from the cloud,
        clears RF pairings, and returns the fan to AP mode. On Gen4, sends
        the immediate/no-response hardFactoryReset variant, matching the
        same connection-drop behavior as Gen 1/2/3.
        """
        try:
            if self._device is None:
                await self.update()
            assert self._device is not None
            if self._device.generation == Generation.GEN4:
                await self._request(
                    {GEN4_DEVICE_HARD_FACTORY_RESET: True},
                    path=GEN4_DEVICE_API_ENDPOINT,
                )
            else:
                await self.request(commands={COMMAND_FACTORY_RESET: True})
        except ModernFormsConnectionTimeoutError:
            # a successful factory reset drops the connection (this also
            # covers a timeout during the implicit update() above, on a
            # device that has never been reached before)
            pass

    async def decommission(self):
        """Decommission the fan from the cloud and return it to AP mode."""
        try:
            if self._device is None:
                await self.update()
            assert self._device is not None
            if self._device.generation == Generation.GEN4:
                raise ModernFormsNotSupportedError(
                    "decommission() is not supported on Gen4 fans"
                )
            await self.request(commands={COMMAND_DECOMMISSION: True})
        except ModernFormsConnectionTimeoutError:
            # a successful decommission drops the connection (this also
            # covers a timeout during the implicit update() above, on a
            # device that has never been reached before)
            pass

    async def set_schedule(self, data: str):
        """Set the fan's base64-encoded schedule blob."""
        if self._device is None:
            await self.update()
        assert self._device is not None
        if self._device.generation == Generation.GEN4:
            raise ModernFormsNotSupportedError(
                "set_schedule() is not supported on Gen4 fans"
            )
        await self.request(commands={COMMAND_SCHEDULE: data})

    async def reboot(self):
        """Send a reboot to the Fan."""
        try:
            if self._device is None:
                await self.update()
            assert self._device is not None
            if self._device.generation == Generation.GEN4:
                await self._request(
                    {COMMAND_REBOOT: True}, path=GEN4_DEVICE_API_ENDPOINT
                )
            else:
                await self.request(commands={COMMAND_REBOOT: True})
        except ModernFormsConnectionTimeoutError:
            # a successful reboot drops the connection (this also covers a
            # timeout during the implicit update() above, on a device that
            # has never been reached before)
            pass

    async def close(self) -> None:
        """Close open client session."""
        if self._session and self._close_session:
            await self._session.close()

    async def __aenter__(self) -> ModernFormsDevice:
        """Async enter."""
        return self

    async def __aexit__(self, *exc_info) -> None:
        """Async exit."""
        await self.close()
