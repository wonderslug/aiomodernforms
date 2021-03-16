"""Models for Async IO Modern Forms."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from .const import (
    INFO_CLIENT_ID,
    STATE_ADAPTIVE_LEARNING,
    STATE_AWAY_MODE,
    STATE_FAN_DIRECTION,
    STATE_FAN_POWER,
    STATE_FAN_SLEEP_TIMER,
    STATE_FAN_SPEED,
    STATE_LIGHT_BRIGHTNESS,
    STATE_LIGHT_POWER,
    STATE_LIGHT_SLEEP_TIMER,
    INFO_FIRMWARE_VERSION,
    INFO_DEVICE_NAME,
    INFO_FAN_MOTOR_TYPE,
    INFO_FAN_TYPE,
    INFO_FEDERATED_IDENTITY,
    INFO_FIRMWARE_URL,
    INFO_LIGHT_TYPE,
    INFO_MAC,
    INFO_MAIN_MCU_FIRMWARE_VERSION,
    INFO_OWNER,
    INFO_PRODUCT_SKU,
    INFO_PRODUCTION_LOT_NUMBER,
)


@dataclass
class Info:
    """Info about the Modern Forms device."""

    client_id: str
    mac: str
    light_type: str
    fan_type: str
    fan_motor_type: str
    production_lot_number: str
    product_sku: str
    owner: str
    federated_identity: str
    device_name: str
    firmware_version: str
    main_mcu_firmware_version: str
    firmware_url: str

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> Info:
        """Return Info object from Modern Forms API response."""
        return Info(
            client_id=data.get(INFO_CLIENT_ID, ""),
            mac=data.get(INFO_MAC, ""),
            light_type=data.get(INFO_LIGHT_TYPE, ""),
            fan_type=data.get(INFO_FAN_TYPE, ""),
            fan_motor_type=data.get(INFO_FAN_MOTOR_TYPE, ""),
            production_lot_number=data.get(INFO_PRODUCTION_LOT_NUMBER, ""),
            product_sku=data.get(INFO_PRODUCT_SKU, ""),
            owner=data.get(INFO_OWNER, ""),
            federated_identity=data.get(INFO_FEDERATED_IDENTITY, ""),
            device_name=data.get(INFO_DEVICE_NAME, ""),
            firmware_version=data.get(INFO_FIRMWARE_VERSION, ""),
            main_mcu_firmware_version=data.get(INFO_MAIN_MCU_FIRMWARE_VERSION, ""),
            firmware_url=data.get(INFO_FIRMWARE_URL, ""),
        )


@dataclass
class State:
    """Object holding the state of Modern Forms Device."""

    fan_on: bool
    fan_speed: int
    fan_direction: str
    fan_sleep_timer: int
    light_on: bool
    light_brightness: int
    light_sleep_timer: int
    away_mode_enabled: bool
    adaptive_learning_enabled: bool

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> State:
        """Return State object from Modern Forms API response."""
        return State(
            fan_on=data.get(STATE_FAN_POWER, False),
            fan_speed=data.get(STATE_FAN_SPEED, 6),
            fan_direction=data.get(STATE_FAN_DIRECTION, "forward"),
            fan_sleep_timer=data.get(STATE_FAN_SLEEP_TIMER, 0),
            light_on=data.get(STATE_LIGHT_POWER, False),
            light_brightness=data.get(STATE_LIGHT_BRIGHTNESS, 100),
            light_sleep_timer=data.get(STATE_LIGHT_SLEEP_TIMER, 0),
            away_mode_enabled=data.get(STATE_AWAY_MODE, False),
            adaptive_learning_enabled=data.get(STATE_ADAPTIVE_LEARNING, False),
        )


class Device:
    """Object holding all information of Modern Forms Device."""

    info: Info
    state: State

    def __init__(self, state_data: dict, info_data: dict):
        """Initialize an empty Modern Forms device class."""
        self.update_from_dict(state_data=state_data, info_data=info_data)

    def update_from_dict(
        self, state_data: dict = None, info_data: dict = None
    ) -> "Device":
        """Update the device status with the passed dict."""
        if state_data is not None:
            self.state = State.from_dict(state_data)
        if info_data is not None:
            self.info = Info.from_dict(info_data)
        return self
