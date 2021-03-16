"""Async IO client library for Modern Forms fans."""
from __future__ import annotations

import asyncio
import json
import socket
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Union

import aiohttp
import async_timeout
import backoff  # type: ignore
from yarl import URL

from .__version__ import __version__
from .const import (
    COMMAND_ADAPTIVE_LEARNING,
    COMMAND_AWAY_MODE,
    COMMAND_FAN_DIRECTION,
    COMMAND_FAN_POWER,
    COMMAND_FAN_SLEEP_TIMER,
    COMMAND_FAN_SPEED,
    COMMAND_LIGHT_BRIGHTNESS,
    COMMAND_LIGHT_POWER,
    COMMAND_LIGHT_SLEEP_TIMER,
    COMMAND_QUERY_STATIC_DATA,
    COMMAND_QUERY_STATUS,
    DEFAULT_API_ENDPOINT,
    DEFAULT_PORT,
    DEFAULT_TIMEOUT_SECS,
    FAN_DIRECTION_FORWARD,
    FAN_DIRECTION_REVERSE,
    FAN_SPEED_HIGH_VALUE,
    FAN_SPEED_LOW_VALUE,
    LIGHT_BRIGHTNESS_HIGH_VALUE,
    LIGHT_BRIGHTNESS_LOW_VALUE,
)
from .exceptions import (
    ModernFormsConnectionError,
    ModernFormsConnectionTimeoutError,
    ModernFormsEmptyResponseError,
    ModernFormsError,
    ModernFormsInvalidSettingsError,
    ModernFormsNotInitializedError,
)
from .models import Device


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
        session: aiohttp.client.ClientSession = None,
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

        self._base_path += DEFAULT_API_ENDPOINT

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
    async def _request(self, commands: Optional[dict] = None) -> Any:
        """Handle a request to a Modern Forms Fan device."""
        scheme = "https" if self._tls else "http"
        url = URL.build(
            scheme=scheme,
            host=self._host,
            port=self._port,
            path=self._base_path,
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
            with async_timeout.timeout(self._request_timeout):
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

    async def light(
        self,
        *,
        brightness: Optional[int] = None,
        on: Optional[bool] = None,
        sleep: Optional[datetime] = None,
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
            if (
                not isinstance(sleep, datetime)
                or sleep < datetime.now()
                or sleep > (datetime.now() + timedelta(hours=24))
            ):
                raise ModernFormsInvalidSettingsError(
                    "The time to sleep till must be a datetime object that is more"
                    + " then 24 hours into the future."
                )
            commands[COMMAND_LIGHT_SLEEP_TIMER] = int(sleep.timestamp())
        await self.request(commands=commands)

    async def fan(
        self,
        *,
        on: Optional[bool] = None,
        sleep: Optional[datetime] = None,
        speed: Optional[int] = None,
        direction: Optional[str] = None,
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
            if (
                not isinstance(sleep, datetime)
                or sleep < datetime.now()
                or sleep > (datetime.now() + timedelta(hours=24))
            ):
                raise ModernFormsInvalidSettingsError(
                    "The time to sleep till must be a datetime object that is more"
                    + " then 24 hours into the future."
                )
            commands[COMMAND_FAN_SLEEP_TIMER] = int(sleep.timestamp())

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

        await self.request(commands=commands)

    async def away(self, away=bool):
        """Change the away state of the device."""
        await self.request(commands={COMMAND_AWAY_MODE: away})

    async def adaptive_learning(self, adaptive_learning=bool):
        """Change the adaptive learning state of the device."""
        await self.request(commands={COMMAND_ADAPTIVE_LEARNING: adaptive_learning})

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
