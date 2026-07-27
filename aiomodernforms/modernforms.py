"""Async IO client library for Modern Forms fans."""
from __future__ import annotations

import asyncio
import json
import socket
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Union

import aiohttp
import backoff  # type: ignore
from yarl import URL

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
    COMMAND_LIGHT_BRIGHTNESS,
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
    LIGHT_BRIGHTNESS_HIGH_VALUE,
    LIGHT_BRIGHTNESS_LOW_VALUE,
    SLEEP_TIMER_CANCEL,
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
)
from .models import ConfigInfo, Device


class ModernFormsDevice:
    """Modern Forms device reppresentation."""

    _device: Optional[Device] = None

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

    @backoff.on_exception(
        backoff.expo, ModernFormsEmptyResponseError, max_tries=3, logger=None
    )
    async def update(self, full_update: bool = False) -> Device:
        """Get all information about the device in a single call."""
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

    @backoff.on_exception(
        backoff.expo, ModernFormsConnectionError, max_tries=3, logger=None
    )
    async def _request(
        self, commands: Optional[dict] = None, path: str = DEFAULT_API_ENDPOINT
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
        except asyncio.TimeoutError as exception:
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

    async def request(self, commands: Optional[dict] = None):
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
        """Retrieve config-read data: hardware revision, RF library version,
        certificate ID, and current Wi-Fi signal strength."""
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

    def _sleep_command(
        self, epoch_command: str, relative_command: str, sleep: Union[int, datetime]
    ) -> Dict[str, int]:
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
                return {command: int((sleep - datetime.now()).total_seconds())}
            return {command: int(sleep.timestamp())}

        raise ModernFormsInvalidSettingsError(
            "The time to sleep till must be a datetime object that is not more"
            + " then 24 hours into the future, or an interger for number of"
            + " seconds to sleep. 0 cancels the sleep timer."
        )

    async def light(
        self,
        *,
        brightness: Optional[int] = None,
        on: Optional[bool] = None,
        sleep: Optional[Union[int, datetime]] = None,
    ):
        """Change Fans Light state."""
        commands: Dict[str, Union[bool, int]] = {}

        if brightness is not None:
            if (
                not isinstance(brightness, int)
                or int(brightness) < LIGHT_BRIGHTNESS_LOW_VALUE
                or int(brightness) > LIGHT_BRIGHTNESS_HIGH_VALUE
            ):
                raise ModernFormsInvalidSettingsError(
                    "brightness value must be between"
                    + f" {LIGHT_BRIGHTNESS_LOW_VALUE} and {LIGHT_BRIGHTNESS_HIGH_VALUE}"
                )

            commands[COMMAND_LIGHT_BRIGHTNESS] = brightness

        if on is not None:
            if not isinstance(on, bool):
                raise ModernFormsInvalidSettingsError("on must be a boolean")

            commands[COMMAND_LIGHT_POWER] = on

        if sleep is not None:
            commands.update(
                self._sleep_command(
                    COMMAND_LIGHT_SLEEP_TIMER, COMMAND_LIGHT_TIMER, sleep
                )
            )

        await self.request(commands=commands)

    async def fan(
        self,
        *,
        on: Optional[bool] = None,
        sleep: Optional[Union[int, datetime]] = None,
        speed: Optional[int] = None,
        direction: Optional[str] = None,
        wind: Optional[bool] = None,
        wind_speed: Optional[int] = None,
    ):
        """Change Fans Fan state."""
        commands: Dict[str, Union[bool, int, str]] = {}

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

        if sleep is not None:
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

        await self.request(commands=commands)

    async def away(self, away: bool):
        """Change the away state of the device."""
        await self.request(
            commands={COMMAND_AWAY_MODE: away, COMMAND_QUERY_STATUS: True}
        )

    async def adaptive_learning(self, adaptive_learning: bool):
        """Change the adaptive learning state of the device."""
        await self.request(
            commands={
                COMMAND_ADAPTIVE_LEARNING: adaptive_learning,
                COMMAND_QUERY_STATUS: True,
            }
        )

    async def enable_pairing_mode(self, active: bool = True):
        """Toggle RF pairing mode, used to pair remotes or wall controls."""
        await self.request(commands={COMMAND_RF_PAIR_MODE: active})

    async def clear_paired_devices(self):
        """Clear all RF-paired devices (remotes, wall controls) from the fan."""
        await self.request(commands={COMMAND_RESET_RF_PAIR_LIST: True})

    async def factory_reset(self):
        """Factory reset the fan.

        Clears Wi-Fi credentials, decommissions the fan from the cloud,
        clears RF pairings, and returns the fan to AP mode.
        """
        try:
            await self.request(commands={COMMAND_FACTORY_RESET: True})
        except ModernFormsConnectionTimeoutError:
            # a successful factory reset drops the connection
            pass

    async def decommission(self):
        """Decommission the fan from the cloud and return it to AP mode."""
        try:
            await self.request(commands={COMMAND_DECOMMISSION: True})
        except ModernFormsConnectionTimeoutError:
            # a successful decommission drops the connection
            pass

    async def set_schedule(self, data: str):
        """Set the fan's base64-encoded schedule blob."""
        await self.request(commands={COMMAND_SCHEDULE: data})

    async def reboot(self):
        """Send a reboot to the Fan."""
        try:
            await self.request(commands={COMMAND_REBOOT: True})
        except ModernFormsConnectionTimeoutError:
            # a successful reboot drops the connection
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
