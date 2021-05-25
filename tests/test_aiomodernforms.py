"""Tests for Async IO Modern Forms Library."""
import json
from datetime import datetime, timedelta

import pytest

import aiomodernforms
from aiomodernforms.const import (
    ADAPTIVE_LEARNING_ON,
    AWAY_MODE_ON,
    FAN_SPEED_HIGH_VALUE,
    FAN_SPEED_LOW_VALUE,
    LIGHT_BRIGHTNESS_HIGH_VALUE,
    LIGHT_BRIGHTNESS_LOW_VALUE,
    STATE_ADAPTIVE_LEARNING,
    STATE_AWAY_MODE,
    STATE_FAN_DIRECTION,
    STATE_FAN_POWER,
    STATE_FAN_SLEEP_TIMER,
    STATE_FAN_SPEED,
    STATE_LIGHT_BRIGHTNESS,
    STATE_LIGHT_POWER,
    STATE_LIGHT_SLEEP_TIMER,
)

basic_response = {
    "adaptiveLearning": False,
    "awayModeEnabled": False,
    "clientId": "MF_000000000000",
    "decommission": False,
    "factoryReset": False,
    "fanDirection": "forward",
    "fanOn": False,
    "fanSleepTimer": 0,
    "fanSpeed": 3,
    "lightBrightness": 50,
    "lightOn": False,
    "lightSleepTimer": 0,
    "resetRfPairList": False,
    "rfPairModeActive": False,
    "schedule": "",
}

basic_info = {
    "clientId": "MF_000000000000",
    "mac": "CC:CC:CC:CC:CC:CC",
    "lightType": "F6IN-120V-R1-30",
    "fanType": "1818-56",
    "fanMotorType": "DC125X25",
    "productionLotNumber": "",
    "productSku": "",
    "owner": "someone@somewhere.com",
    "federatedIdentity": "us-east-1:f3da237b-c19c-4f61-b387-0e6dde2e470b",
    "deviceName": "Fan",
    "firmwareVersion": "01.03.0025",
    "mainMcuFirmwareVersion": "01.03.3008",
    "firmwareUrl": "",
}


@pytest.mark.asyncio
async def test_basic_status(aresponses):
    """Test JSON response is handled correctly."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add(
        "fan.local",
        "/mf",
        "POST",
        response=basic_response,
        repeat=2,
    )
    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        response = await device.request(
            commands={aiomodernforms.COMMAND_LIGHT_POWER: False}
        )
        assert response.fan_on == basic_response["fanOn"]


@pytest.mark.asyncio
async def test_command(aresponses):
    """Test to make sure setting lights works."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async def evaluate_request(request):
        data = await request.json()
        assert aiomodernforms.COMMAND_LIGHT_POWER in data
        modified_response = basic_response.copy()
        modified_response[STATE_LIGHT_POWER] = data[aiomodernforms.COMMAND_LIGHT_POWER]
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(modified_response),
        )

    aresponses.add("fan.local", "/mf", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        response = await device.request(
            commands={aiomodernforms.COMMAND_LIGHT_POWER: aiomodernforms.LIGHT_POWER_ON}
        )
        assert response.light_on == aiomodernforms.LIGHT_POWER_ON


@pytest.mark.asyncio
async def test_light(aresponses):
    """Test to make sure setting lights works."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async def evaluate_request(request):
        data = await request.json()
        assert aiomodernforms.COMMAND_LIGHT_POWER in data
        assert aiomodernforms.COMMAND_LIGHT_BRIGHTNESS in data
        assert aiomodernforms.COMMAND_LIGHT_SLEEP_TIMER in data
        modified_response = basic_response.copy()
        modified_response[STATE_LIGHT_POWER] = data[aiomodernforms.COMMAND_LIGHT_POWER]
        modified_response[STATE_LIGHT_BRIGHTNESS] = data[
            aiomodernforms.COMMAND_LIGHT_BRIGHTNESS
        ]
        modified_response[STATE_LIGHT_SLEEP_TIMER] = data[
            aiomodernforms.COMMAND_LIGHT_SLEEP_TIMER
        ]
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(modified_response),
        )

    aresponses.add("fan.local", "/mf", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        sleep_time = datetime.now() + timedelta(minutes=2)
        await device.light(
            on=aiomodernforms.LIGHT_POWER_ON,
            brightness=aiomodernforms.LIGHT_BRIGHTNESS_HIGH_VALUE,
            sleep=sleep_time,
        )
        assert device.status.light_on == aiomodernforms.LIGHT_POWER_ON
        assert (
            device.status.light_brightness == aiomodernforms.LIGHT_BRIGHTNESS_HIGH_VALUE
        )
        assert device.status.light_sleep_timer == int(sleep_time.timestamp())


@pytest.mark.asyncio
async def test_light_sleep_datetime(aresponses):
    """Test to make sure setting light sleep works."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async def evaluate_request(request):
        data = await request.json()
        assert aiomodernforms.COMMAND_LIGHT_SLEEP_TIMER in data
        modified_response = basic_response.copy()
        modified_response[STATE_LIGHT_SLEEP_TIMER] = data[
            aiomodernforms.COMMAND_LIGHT_SLEEP_TIMER
        ]
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(modified_response),
        )

    aresponses.add("fan.local", "/mf", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        sleep_time = datetime.now() + timedelta(minutes=2)
        await device.light(
            sleep=sleep_time,
        )
        assert device.status.light_sleep_timer == int(sleep_time.timestamp())


@pytest.mark.asyncio
async def test_light_sleep_int(aresponses):
    """Test to make sure setting light sleep works."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async def evaluate_request(request):
        data = await request.json()
        assert aiomodernforms.COMMAND_LIGHT_SLEEP_TIMER in data
        modified_response = basic_response.copy()
        modified_response[STATE_LIGHT_SLEEP_TIMER] = data[
            aiomodernforms.COMMAND_LIGHT_SLEEP_TIMER
        ]
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(modified_response),
        )

    aresponses.add("fan.local", "/mf", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        sleep_time = datetime.now() + timedelta(seconds=120)
        await device.light(
            sleep=120,
        )
        assert device.status.light_sleep_timer == int(sleep_time.timestamp())


@pytest.mark.asyncio
async def test_light_sleep_clear(aresponses):
    """Test to make sure setting light sleep works."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async def evaluate_request(request):
        data = await request.json()
        assert aiomodernforms.COMMAND_LIGHT_SLEEP_TIMER in data
        modified_response = basic_response.copy()
        modified_response[STATE_LIGHT_SLEEP_TIMER] = data[
            aiomodernforms.COMMAND_LIGHT_SLEEP_TIMER
        ]
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(modified_response),
        )

    aresponses.add("fan.local", "/mf", "POST", response=evaluate_request)

    # check to clear timer
    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.light(
            sleep=0,
        )
        assert device.status.light_sleep_timer == 0


@pytest.mark.asyncio
async def test_fan(aresponses):
    """Test to make sure setting fan works."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async def evaluate_request(request):
        data = await request.json()
        assert aiomodernforms.COMMAND_FAN_POWER in data
        assert aiomodernforms.COMMAND_FAN_SPEED in data
        assert aiomodernforms.COMMAND_FAN_DIRECTION in data
        assert aiomodernforms.COMMAND_FAN_SLEEP_TIMER in data
        modified_response = basic_response.copy()
        modified_response[STATE_FAN_POWER] = data[aiomodernforms.COMMAND_FAN_POWER]
        modified_response[STATE_FAN_SPEED] = data[aiomodernforms.COMMAND_FAN_SPEED]
        modified_response[STATE_FAN_DIRECTION] = data[
            aiomodernforms.COMMAND_FAN_DIRECTION
        ]
        modified_response[STATE_FAN_SLEEP_TIMER] = data[
            aiomodernforms.COMMAND_FAN_SLEEP_TIMER
        ]
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(modified_response),
        )

    aresponses.add("fan.local", "/mf", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        sleep_time = datetime.now() + timedelta(minutes=2)
        await device.fan(
            on=aiomodernforms.FAN_POWER_ON,
            speed=aiomodernforms.FAN_SPEED_HIGH_VALUE,
            direction=aiomodernforms.FAN_DIRECTION_FORWARD,
            sleep=sleep_time,
        )
        assert device.status.fan_on == aiomodernforms.FAN_POWER_ON
        assert device.status.fan_speed == aiomodernforms.FAN_SPEED_HIGH_VALUE
        assert device.status.fan_direction == aiomodernforms.FAN_DIRECTION_FORWARD
        assert device.status.fan_sleep_timer == int(sleep_time.timestamp())


@pytest.mark.asyncio
async def test_fan_sleep_datetime(aresponses):
    """Test to make sure setting light sleep works."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async def evaluate_request(request):
        data = await request.json()
        assert aiomodernforms.COMMAND_FAN_SLEEP_TIMER in data
        modified_response = basic_response.copy()
        modified_response[STATE_FAN_SLEEP_TIMER] = data[
            aiomodernforms.COMMAND_FAN_SLEEP_TIMER
        ]
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(modified_response),
        )

    aresponses.add("fan.local", "/mf", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        sleep_time = datetime.now() + timedelta(minutes=2)
        await device.fan(
            sleep=sleep_time,
        )
        assert device.status.fan_sleep_timer == int(sleep_time.timestamp())


@pytest.mark.asyncio
async def test_fan_sleep_int(aresponses):
    """Test to make sure setting light sleep works."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async def evaluate_request(request):
        data = await request.json()
        assert aiomodernforms.COMMAND_FAN_SLEEP_TIMER in data
        modified_response = basic_response.copy()
        modified_response[STATE_FAN_SLEEP_TIMER] = data[
            aiomodernforms.COMMAND_FAN_SLEEP_TIMER
        ]
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(modified_response),
        )

    aresponses.add("fan.local", "/mf", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        sleep_time = datetime.now() + timedelta(seconds=120)
        await device.fan(
            sleep=120,
        )
        assert device.status.fan_sleep_timer == int(sleep_time.timestamp())


@pytest.mark.asyncio
async def test_fan_sleep_clear(aresponses):
    """Test to make sure setting light sleep works."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async def evaluate_request(request):
        data = await request.json()
        assert aiomodernforms.COMMAND_FAN_SLEEP_TIMER in data
        modified_response = basic_response.copy()
        modified_response[STATE_FAN_SLEEP_TIMER] = data[
            aiomodernforms.COMMAND_FAN_SLEEP_TIMER
        ]
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(modified_response),
        )

    aresponses.add("fan.local", "/mf", "POST", response=evaluate_request)

    # check to clear timer
    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.fan(
            sleep=0,
        )
        assert device.status.fan_sleep_timer == 0


@pytest.mark.asyncio
async def test_away(aresponses):
    """Test to make sure setting away mode works."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async def evaluate_request(request):
        data = await request.json()
        assert aiomodernforms.COMMAND_AWAY_MODE in data
        modified_response = basic_response.copy()
        modified_response[STATE_AWAY_MODE] = data[aiomodernforms.COMMAND_AWAY_MODE]
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(modified_response),
        )

    aresponses.add("fan.local", "/mf", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        await device.away(AWAY_MODE_ON)
        assert device.status.away_mode_enabled


@pytest.mark.asyncio
async def test_adaptive_learning(aresponses):
    """Test to make sure setting adaptive learning mode works."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async def evaluate_request(request):
        data = await request.json()
        assert aiomodernforms.COMMAND_ADAPTIVE_LEARNING in data
        modified_response = basic_response.copy()
        modified_response[STATE_ADAPTIVE_LEARNING] = data[
            aiomodernforms.COMMAND_ADAPTIVE_LEARNING
        ]
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(modified_response),
        )

    aresponses.add("fan.local", "/mf", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        await device.adaptive_learning(ADAPTIVE_LEARNING_ON)
        assert device.status.adaptive_learning_enabled


@pytest.mark.asyncio
async def test_invalid_setting(aresponses):
    """Test to make sure setting invalid settings are rejected."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        # light on non boolean
        with pytest.raises(aiomodernforms.ModernFormsInvalidSettingsError):
            await device.light(on="foo")

        # light brightness not integer
        with pytest.raises(aiomodernforms.ModernFormsInvalidSettingsError):
            await device.light(brightness="foo")

        # light brightess out of range
        with pytest.raises(aiomodernforms.ModernFormsInvalidSettingsError):
            await device.light(brightness=LIGHT_BRIGHTNESS_HIGH_VALUE + 1)

        with pytest.raises(aiomodernforms.ModernFormsInvalidSettingsError):
            await device.light(brightness=LIGHT_BRIGHTNESS_LOW_VALUE - 1)

        # light sleep non boolean
        with pytest.raises(aiomodernforms.ModernFormsInvalidSettingsError):
            await device.light(sleep="foo")

        # light sleep out of range
        with pytest.raises(aiomodernforms.ModernFormsInvalidSettingsError):
            await device.light(sleep=datetime.now() + timedelta(hours=25))

        with pytest.raises(aiomodernforms.ModernFormsInvalidSettingsError):
            await device.light(sleep=datetime.now() - timedelta(minutes=1))

        # fan on non boolean
        with pytest.raises(aiomodernforms.ModernFormsInvalidSettingsError):
            await device.fan(on="foo")

        # fan speed not integer
        with pytest.raises(aiomodernforms.ModernFormsInvalidSettingsError):
            await device.fan(speed="foo")

        # fan speed out of range
        with pytest.raises(aiomodernforms.ModernFormsInvalidSettingsError):
            await device.fan(speed=FAN_SPEED_HIGH_VALUE + 1)

        with pytest.raises(aiomodernforms.ModernFormsInvalidSettingsError):
            await device.fan(speed=FAN_SPEED_LOW_VALUE - 1)

        # fan sleep non boolean
        with pytest.raises(aiomodernforms.ModernFormsInvalidSettingsError):
            await device.fan(sleep="foo")

        # fan sleep out of range
        with pytest.raises(aiomodernforms.ModernFormsInvalidSettingsError):
            await device.fan(sleep=datetime.now() + timedelta(hours=25))

        with pytest.raises(aiomodernforms.ModernFormsInvalidSettingsError):
            await device.fan(sleep=datetime.now() - timedelta(minutes=1))

        # fan direction non string
        with pytest.raises(aiomodernforms.ModernFormsInvalidSettingsError):
            await device.fan(direction=1)

        # fan direction invlaid value
        with pytest.raises(aiomodernforms.ModernFormsInvalidSettingsError):
            await device.fan(direction="upwards")


@pytest.mark.asyncio
async def test_connection_error(aresponses):
    """Test to make validate proper connection error handling."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    with pytest.raises(aiomodernforms.ModernFormsConnectionError):
        async with aiomodernforms.ModernFormsDevice("fan.local") as device:
            await device.update()


@pytest.mark.asyncio
async def test_server_error(aresponses):
    """Test to make validate proper server error handling."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add(
        "fan.local",
        "/mf",
        "POST",
        response=aresponses.Response(text="error", status=500),
    )

    with pytest.raises(aiomodernforms.ModernFormsError):
        async with aiomodernforms.ModernFormsDevice("fan.local") as device:
            await device.update()
