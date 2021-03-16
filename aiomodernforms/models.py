"""Models for Async IO Modern Forms."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from .const import (
    STATE_ADAPTIVE_LEARNING,
    STATE_AWAY_MODE,
    STATE_CLIENT_ID,
    STATE_FAN_DIRECTION,
    STATE_FAN_POWER,
    STATE_FAN_SLEEP_TIMER,
    STATE_FAN_SPEED,
    STATE_LIGHT_BRIGHTNESS,
    STATE_LIGHT_POWER,
    STATE_LIGHT_SLEEP_TIMER,
)


@dataclass
class Info:
    """Info about the Modern Forms device."""

    id: str

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> Info:
        """Return Info object from Modern Forms API response."""
        return Info(id=data.get(STATE_CLIENT_ID, "UNKNOWN"))


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

    def __init__(self, data: dict):
        """Initialize an empty Modern Forms device class."""
        self.update_from_dict(data)

    def update_from_dict(self, data: dict) -> "Device":
        """Update the device status with the passed dict."""
        self.state = State.from_dict(data)
        self.info = Info.from_dict(data)
        return self
