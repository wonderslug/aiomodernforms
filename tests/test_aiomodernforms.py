"""Tests for Async IO Modern Forms Library."""

import json
from datetime import datetime, timedelta
from unittest.mock import patch

import aiohttp
import pytest

import aiomodernforms
from aiomodernforms.const import (
    ADAPTIVE_LEARNING_ON,
    AWAY_MODE_ON,
    COMMAND_QUERY_STATIC_DATA,
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
    STATE_FAN_TIMER,
    STATE_LIGHT_BRIGHTNESS,
    STATE_LIGHT_POWER,
    STATE_LIGHT_SLEEP_TIMER,
    STATE_LIGHT_TIMER,
    STATE_RF_PAIR_MODE_ACTIVE,
    STATE_SCHEDULE,
    STATE_WIND_POWER,
    STATE_WIND_SPEED,
)
from aiomodernforms.exceptions import (
    ModernFormsConnectionTimeoutError,
    ModernFormsEmptyResponseError,
    ModernFormsNotInitializedError,
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


breeze_mode_response = {
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
    "userData": "cloud",
    "wind": False,
    "windSpeed": 2,
}


gen3_relative_timer_response = {
    "adaptiveLearning": False,
    "awayModeEnabled": False,
    "clientId": "MF_C82B9698E5AC",
    "decommission": False,
    "factoryReset": False,
    "fanDirection": "forward",
    "fanOn": False,
    "fanTimer": 0,
    "fanSpeed": 3,
    "lightBrightness": 50,
    "lightOn": False,
    "lightTimer": 0,
    "resetRfPairList": False,
    "rfPairModeActive": False,
    "schedule": "",
    "userData": "cloud",
    "wind": False,
    "windSpeed": 2,
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


gen3_info = {
    "clientId": "MF_C82B9698E5AC",
    "mac": "C8:2B:96:98:E5:AC",
    "lightType": "",
    "fanType": "2003-52",
    "fanMotorType": "DC125X12",
    "brand": 0,
    "dateCode": "20220101",
    "owner": "someone@somewhere.com",
    "federatedIdentity": "us-east-1:f3da237b-c19c-4f61-b387-0e6dde2e470b",
    "deviceName": "Fan",
    "firmwareVersion": "02.00.0003",
    "mainMcuFirmwareVersion": "02.01.0000",
    "firmwareUrl": "",
}


gen1_2_config_response = {
    "T": "Current Configuration",
    "N": "WAC Windermier Fan(83DEF0)",
    "C": [{"N": "APPLICATION", "C": []}],
    "PO": "com.modernforms.fan",
    "HD": "WAC_WINDERMIER_REV_5",
    "FW": "01.03.0021",
    "RF": "wl0: Oct  6 2016 01:32:44 version 5.90.230.15 ",
    "certificateId": "6v6amxh5vbb2qjnkrp2av8i8r1tk1svzwn4ktrr9ds2ljz65ycfq1y026r6b77pt",
    "Wi-Fi strength": 100,
}

gen3_config_response = {
    "Name": "MF_Fan_98E5AC",
    "Protocol": "com.modernforms.fan",
    "Firmware Rev": "02.00.0003",
    "RF Rev": "v3.2.2",
    "certificateId": "6v6amxh5vbb2qjnkrp2av8i8r1tk1svzwn4ktrr9ds2ljz65ycfq1y026r6b77pt",
    "Wi-Fi strength": "-48",
}

# Observed on real Gen 1/2 hardware: uses "WiFi" instead of the documented
# "Wi-Fi strength" key, and includes several undocumented extra fields.
real_gen1_2_config_response = {
    "N": "WAC Windermier Fan(860E84)",
    "PO": "com.modernforms.fan",
    "HD": "WAC_WINDERMIER_REV_5",
    "FW": "01.03.0028",
    "RF": "wl0: Sep 10 2014 11:28:46 version 5.90.230.10 ",
    "TZ": "CST6CDT",
    "NOW": "Mon Jul 27 19:09:05 2026\n",
    "certificateId": "ab3ce5c71c15bb3d2d2d2884efef0d6e7d681bb41bdbef2445fb536e220db3fd",
    "FS": "387|396KB",
    "WiFi": 100,
    "MQTTCommission": 0,
    "MQTTShadow": 11,
    "MQTTCommissionCnt": 1,
    "MQTTShadowCnt": 125,
}

# Observed on real Gen 2 hardware (see GitHub issue #272): uses "wifiSignal"
# instead of either the documented "Wi-Fi strength" or the "WiFi" fallback.
real_gen2_wifi_signal_config_response = {
    "BSSID": "0xREDACTED",
    "SSID": "REDACTED",
    "Name": "REDACTED",
    "Protocol": "com.modernforms.fan",
    "Firmware Rev": "02.00.0043",
    "RF Rev": "v4.0.4-dirty",
    "certificateId": "REDACTED",
    "timezone": "PST8PDT",
    "wifiSignal": "-62",
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
        assert device.status.fan_direction == "forward"
        assert device.info.fan_type == "1818-56"


@pytest.mark.asyncio
async def test_gen3_info_capture(aresponses):
    """Test that Gen 3's brand and dateCode info fields are captured."""
    aresponses.add("fan.local", "/mf", "POST", response=gen3_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        assert device.info.brand == gen3_info["brand"]
        assert device.info.date_code == gen3_info["dateCode"]


@pytest.mark.asyncio
async def test_gen1_2_info_defaults(aresponses):
    """Test that Gen 1/2 info responses default brand/dateCode sensibly."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        assert device.info.brand is None
        assert device.info.date_code == ""


@pytest.mark.asyncio
async def test_config_gen1_2(aresponses):
    """Test config() against a Gen 1/2-shaped /config-read response."""
    aresponses.add("fan.local", "/config-read", "POST", response=gen1_2_config_response)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        config = await device.config()
        assert config.device_name == "WAC Windermier Fan(83DEF0)"
        assert config.protocol == "com.modernforms.fan"
        assert config.hardware_revision == "WAC_WINDERMIER_REV_5"
        assert config.firmware_version == "01.03.0021"
        assert config.certificate_id.startswith("6v6amxh5vbb2qjnkrp2av8i8r1")
        assert config.wifi_strength == "100"


@pytest.mark.asyncio
async def test_config_gen3(aresponses):
    """Test config() against a Gen 3-shaped /config-read response."""
    aresponses.add("fan.local", "/config-read", "POST", response=gen3_config_response)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        config = await device.config()
        assert config.device_name == "MF_Fan_98E5AC"
        assert config.protocol == "com.modernforms.fan"
        assert config.hardware_revision == ""
        assert config.firmware_version == "02.00.0003"
        assert config.rf_version == "v3.2.2"
        assert config.wifi_strength == "-48"


@pytest.mark.asyncio
async def test_config_real_gen1_2_wifi_key(aresponses):
    """Test wifi_strength falls back to the "WiFi" key seen on real Gen 1/2 hardware."""
    aresponses.add(
        "fan.local", "/config-read", "POST", response=real_gen1_2_config_response
    )

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        config = await device.config()
        assert config.device_name == "WAC Windermier Fan(860E84)"
        assert config.hardware_revision == "WAC_WINDERMIER_REV_5"
        assert config.wifi_strength == "100"


@pytest.mark.asyncio
async def test_config_real_gen2_wifi_signal_key(aresponses):
    """Test wifi_strength falls back to "wifiSignal", seen on real Gen 2 hardware."""
    aresponses.add(
        "fan.local",
        "/config-read",
        "POST",
        response=real_gen2_wifi_signal_config_response,
    )

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        config = await device.config()
        assert config.protocol == "com.modernforms.fan"
        assert config.firmware_version == "02.00.0043"
        assert config.wifi_strength == "-62"


@pytest.mark.asyncio
async def test_config_uses_config_read_path(aresponses):
    """Test that regular /mf traffic (update()) is unaffected by config()."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)
    aresponses.add("fan.local", "/config-read", "POST", response=gen3_config_response)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        config = await device.config()
        assert device.status.fan_on == basic_response["fanOn"]
        assert config.device_name == "MF_Fan_98E5AC"


@pytest.mark.asyncio
async def test_full_state_capture(aresponses):
    """Test that all documented dynamic shadow fields are captured on State."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        assert device.status.schedule == basic_response["schedule"]
        assert device.status.rf_pair_mode_active == basic_response["rfPairModeActive"]
        assert device.status.reset_rf_pair_list == basic_response["resetRfPairList"]
        assert device.status.factory_reset == basic_response["factoryReset"]
        assert device.status.decommission == basic_response["decommission"]
        assert device.status.user_data == ""


@pytest.mark.asyncio
async def test_gen3_user_data_capture(aresponses):
    """Test that Gen 3's userData field is captured on State."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=breeze_mode_response)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        assert device.status.user_data == breeze_mode_response["userData"]


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
    """Test that turning on with a brightness sends brightness before on."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async def evaluate_brightness_request(request):
        data = await request.json()
        assert aiomodernforms.COMMAND_LIGHT_BRIGHTNESS in data
        assert aiomodernforms.COMMAND_LIGHT_POWER not in data
        assert aiomodernforms.COMMAND_LIGHT_SLEEP_TIMER not in data
        modified_response = basic_response.copy()
        modified_response[STATE_LIGHT_BRIGHTNESS] = data[
            aiomodernforms.COMMAND_LIGHT_BRIGHTNESS
        ]
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(modified_response),
        )

    async def evaluate_on_request(request):
        data = await request.json()
        assert aiomodernforms.COMMAND_LIGHT_POWER in data
        assert aiomodernforms.COMMAND_LIGHT_SLEEP_TIMER in data
        assert aiomodernforms.COMMAND_LIGHT_BRIGHTNESS not in data
        modified_response = basic_response.copy()
        modified_response[STATE_LIGHT_BRIGHTNESS] = (
            aiomodernforms.LIGHT_BRIGHTNESS_HIGH_VALUE
        )
        modified_response[STATE_LIGHT_POWER] = data[aiomodernforms.COMMAND_LIGHT_POWER]
        modified_response[STATE_LIGHT_SLEEP_TIMER] = data[
            aiomodernforms.COMMAND_LIGHT_SLEEP_TIMER
        ]
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(modified_response),
        )

    aresponses.add("fan.local", "/mf", "POST", response=evaluate_brightness_request)
    aresponses.add("fan.local", "/mf", "POST", response=evaluate_on_request)

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
async def test_light_off_with_brightness_single_request(aresponses):
    """Test that turning off with a brightness change stays a single request."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async def evaluate_request(request):
        data = await request.json()
        assert aiomodernforms.COMMAND_LIGHT_POWER in data
        assert aiomodernforms.COMMAND_LIGHT_BRIGHTNESS in data
        modified_response = basic_response.copy()
        modified_response[STATE_LIGHT_POWER] = data[aiomodernforms.COMMAND_LIGHT_POWER]
        modified_response[STATE_LIGHT_BRIGHTNESS] = data[
            aiomodernforms.COMMAND_LIGHT_BRIGHTNESS
        ]
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(modified_response),
        )

    aresponses.add("fan.local", "/mf", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        await device.light(
            on=aiomodernforms.LIGHT_POWER_OFF,
            brightness=aiomodernforms.LIGHT_BRIGHTNESS_LOW_VALUE,
        )
        assert device.status.light_on == aiomodernforms.LIGHT_POWER_OFF
        assert (
            device.status.light_brightness == aiomodernforms.LIGHT_BRIGHTNESS_LOW_VALUE
        )


@pytest.mark.asyncio
async def test_light_brightness_only_single_request(aresponses):
    """Test that changing only brightness stays a single request."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async def evaluate_request(request):
        data = await request.json()
        assert aiomodernforms.COMMAND_LIGHT_BRIGHTNESS in data
        assert aiomodernforms.COMMAND_LIGHT_POWER not in data
        modified_response = basic_response.copy()
        modified_response[STATE_LIGHT_BRIGHTNESS] = data[
            aiomodernforms.COMMAND_LIGHT_BRIGHTNESS
        ]
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(modified_response),
        )

    aresponses.add("fan.local", "/mf", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        await device.light(brightness=aiomodernforms.LIGHT_BRIGHTNESS_HIGH_VALUE)
        assert (
            device.status.light_brightness == aiomodernforms.LIGHT_BRIGHTNESS_HIGH_VALUE
        )


@pytest.mark.asyncio
async def test_light_on_only_single_request(aresponses):
    """Test that turning on without a brightness stays a single request."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async def evaluate_request(request):
        data = await request.json()
        assert aiomodernforms.COMMAND_LIGHT_POWER in data
        assert aiomodernforms.COMMAND_LIGHT_BRIGHTNESS not in data
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
        await device.light(on=aiomodernforms.LIGHT_POWER_ON)
        assert device.status.light_on == aiomodernforms.LIGHT_POWER_ON


@pytest.mark.asyncio
async def test_light_on_with_brightness_no_sleep(aresponses):
    """Test that turning on with brightness but no sleep still splits requests."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async def evaluate_brightness_request(request):
        data = await request.json()
        assert aiomodernforms.COMMAND_LIGHT_BRIGHTNESS in data
        assert aiomodernforms.COMMAND_LIGHT_POWER not in data
        assert aiomodernforms.COMMAND_LIGHT_SLEEP_TIMER not in data
        modified_response = basic_response.copy()
        modified_response[STATE_LIGHT_BRIGHTNESS] = data[
            aiomodernforms.COMMAND_LIGHT_BRIGHTNESS
        ]
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(modified_response),
        )

    async def evaluate_on_request(request):
        data = await request.json()
        assert aiomodernforms.COMMAND_LIGHT_POWER in data
        assert aiomodernforms.COMMAND_LIGHT_SLEEP_TIMER not in data
        assert aiomodernforms.COMMAND_LIGHT_BRIGHTNESS not in data
        modified_response = basic_response.copy()
        modified_response[STATE_LIGHT_BRIGHTNESS] = (
            aiomodernforms.LIGHT_BRIGHTNESS_HIGH_VALUE
        )
        modified_response[STATE_LIGHT_POWER] = data[aiomodernforms.COMMAND_LIGHT_POWER]
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(modified_response),
        )

    aresponses.add("fan.local", "/mf", "POST", response=evaluate_brightness_request)
    aresponses.add("fan.local", "/mf", "POST", response=evaluate_on_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        await device.light(
            on=aiomodernforms.LIGHT_POWER_ON,
            brightness=aiomodernforms.LIGHT_BRIGHTNESS_HIGH_VALUE,
        )
        assert device.status.light_on == aiomodernforms.LIGHT_POWER_ON
        assert (
            device.status.light_brightness == aiomodernforms.LIGHT_BRIGHTNESS_HIGH_VALUE
        )


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
        # abs=1: the library computes its own now() + 120s independently of
        # sleep_time above, so a second-boundary race can shift the
        # truncated epoch by 1.
        assert device.status.light_sleep_timer == pytest.approx(
            int(sleep_time.timestamp()), abs=1
        )


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
async def test_fan_with_breeze_mode(aresponses):
    """Test to make sure setting fan breeze mode support works."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=breeze_mode_response)

    async def evaluate_request(request):
        data = await request.json()
        assert aiomodernforms.COMMAND_WIND in data
        assert aiomodernforms.COMMAND_WIND_SPEED in data
        modified_response = breeze_mode_response.copy()
        modified_response[STATE_WIND_POWER] = data[aiomodernforms.COMMAND_WIND]
        modified_response[STATE_WIND_SPEED] = data[aiomodernforms.COMMAND_WIND_SPEED]

        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(modified_response),
        )

    aresponses.add("fan.local", "/mf", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        assert device.has_breeze_mode()
        await device.fan(
            wind_speed=aiomodernforms.WIND_SPEED_HIGH_VALUE,
            wind=aiomodernforms.WIND_ON,
        )
        assert device.status.wind == aiomodernforms.WIND_ON
        assert device.status.wind_speed == aiomodernforms.WIND_SPEED_HIGH_VALUE


@pytest.mark.asyncio
async def test_fan_without_breeze_mode(aresponses):
    """Test to make sure setting fan breeze mode support works."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        assert not device.has_breeze_mode()


@pytest.mark.asyncio
async def test_nonupdated_device_for_breeze_mode():
    """Test to make sure breeze mode only looks at initialed device."""
    with pytest.raises(ModernFormsNotInitializedError):
        async with aiomodernforms.ModernFormsDevice("fan.local") as device:
            device.has_breeze_mode()


@pytest.mark.asyncio
async def test_has_relative_timers_true_for_gen3(aresponses):
    """Test that a Gen 3-style response (fanTimer/lightTimer) is detected."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=gen3_relative_timer_response)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        assert device.status.fan_timer == gen3_relative_timer_response["fanTimer"]
        assert device.status.light_timer == gen3_relative_timer_response["lightTimer"]
        assert device.has_relative_timers() is True


@pytest.mark.asyncio
async def test_has_relative_timers_false_for_gen1_2(aresponses):
    """Test that a Gen 1/2-style response is not mistaken for relative timers."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        assert device.status.fan_timer is None
        assert device.status.light_timer is None
        assert device.has_relative_timers() is False


@pytest.mark.asyncio
async def test_nonupdated_device_for_relative_timers():
    """Test that has_relative_timers only looks at an initialized device."""
    with pytest.raises(ModernFormsNotInitializedError):
        async with aiomodernforms.ModernFormsDevice("fan.local") as device:
            device.has_relative_timers()


@pytest.mark.asyncio
async def test_light_sleep_relative_timer_int(aresponses):
    """Test that light sleep uses relative seconds on a Gen 3-style device."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=gen3_relative_timer_response)

    async def evaluate_request(request):
        data = await request.json()
        assert aiomodernforms.COMMAND_LIGHT_TIMER in data
        assert aiomodernforms.COMMAND_LIGHT_SLEEP_TIMER not in data
        assert data[aiomodernforms.COMMAND_LIGHT_TIMER] == 120
        modified_response = gen3_relative_timer_response.copy()
        modified_response[STATE_LIGHT_TIMER] = data[aiomodernforms.COMMAND_LIGHT_TIMER]
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(modified_response),
        )

    aresponses.add("fan.local", "/mf", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        await device.light(sleep=120)
        assert device.status.light_timer == 120


@pytest.mark.asyncio
async def test_light_sleep_relative_timer_without_prior_update(aresponses):
    """Test that light() self-inits via update() before deciding timer semantics.

    Calling light(sleep=...) without an explicit prior update() call must
    still detect Gen 3 relative timer support (rather than deciding epoch
    semantics before the lazy self-init update() runs) and send the
    relative COMMAND_LIGHT_TIMER command instead of the epoch one.
    """
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=gen3_relative_timer_response)

    async def evaluate_request(request):
        data = await request.json()
        assert aiomodernforms.COMMAND_LIGHT_TIMER in data
        assert aiomodernforms.COMMAND_LIGHT_SLEEP_TIMER not in data
        assert data[aiomodernforms.COMMAND_LIGHT_TIMER] == 120
        modified_response = gen3_relative_timer_response.copy()
        modified_response[STATE_LIGHT_TIMER] = data[aiomodernforms.COMMAND_LIGHT_TIMER]
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(modified_response),
        )

    aresponses.add("fan.local", "/mf", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        # deliberately no explicit `await device.update()` before this call
        await device.light(sleep=120)
        assert device.status.light_timer == 120


@pytest.mark.asyncio
async def test_fan_sleep_relative_timer_without_prior_update(aresponses):
    """Test that fan() self-inits via update() before deciding timer semantics.

    Same as test_light_sleep_relative_timer_without_prior_update but for
    fan(), confirming COMMAND_FAN_TIMER (relative) is sent rather than the
    epoch COMMAND_FAN_SLEEP_TIMER command.
    """
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=gen3_relative_timer_response)

    async def evaluate_request(request):
        data = await request.json()
        assert aiomodernforms.COMMAND_FAN_TIMER in data
        assert aiomodernforms.COMMAND_FAN_SLEEP_TIMER not in data
        assert data[aiomodernforms.COMMAND_FAN_TIMER] == 120
        modified_response = gen3_relative_timer_response.copy()
        modified_response[STATE_FAN_TIMER] = data[aiomodernforms.COMMAND_FAN_TIMER]
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(modified_response),
        )

    aresponses.add("fan.local", "/mf", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        # deliberately no explicit `await device.update()` before this call
        await device.fan(sleep=120)
        assert device.status.fan_timer == 120


@pytest.mark.asyncio
async def test_fan_sleep_relative_timer_datetime(aresponses):
    """Test that fan sleep uses relative seconds on a Gen 3-style device."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=gen3_relative_timer_response)

    async def evaluate_request(request):
        data = await request.json()
        assert aiomodernforms.COMMAND_FAN_TIMER in data
        assert aiomodernforms.COMMAND_FAN_SLEEP_TIMER not in data
        modified_response = gen3_relative_timer_response.copy()
        modified_response[STATE_FAN_TIMER] = data[aiomodernforms.COMMAND_FAN_TIMER]
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(modified_response),
        )

    aresponses.add("fan.local", "/mf", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        sleep_time = datetime.now() + timedelta(minutes=2)
        await device.fan(sleep=sleep_time)
        assert device.status.fan_timer == pytest.approx(120, abs=2)


@pytest.mark.asyncio
async def test_light_sleep_relative_timer_clear(aresponses):
    """Test that sleep=0 cancels the timer under relative-timer semantics too."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=gen3_relative_timer_response)

    async def evaluate_request(request):
        data = await request.json()
        assert data.get(aiomodernforms.COMMAND_LIGHT_TIMER) == 0
        modified_response = gen3_relative_timer_response.copy()
        modified_response[STATE_LIGHT_TIMER] = 0
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(modified_response),
        )

    aresponses.add("fan.local", "/mf", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        await device.light(sleep=0)
        assert device.status.light_timer == 0


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
        # abs=1: the library computes its own now() + 120s independently of
        # sleep_time above, so a second-boundary race can shift the
        # truncated epoch by 1.
        assert device.status.fan_sleep_timer == pytest.approx(
            int(sleep_time.timestamp()), abs=1
        )


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
async def test_enable_pairing_mode(aresponses):
    """Test enabling RF pairing mode."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async def evaluate_request(request):
        data = await request.json()
        assert aiomodernforms.COMMAND_RF_PAIR_MODE in data
        modified_response = basic_response.copy()
        modified_response[STATE_RF_PAIR_MODE_ACTIVE] = data[
            aiomodernforms.COMMAND_RF_PAIR_MODE
        ]
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(modified_response),
        )

    aresponses.add("fan.local", "/mf", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        await device.enable_pairing_mode()
        assert device.status.rf_pair_mode_active is True


@pytest.mark.asyncio
async def test_disable_pairing_mode(aresponses):
    """Test disabling RF pairing mode via enable_pairing_mode(active=False)."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async def evaluate_request(request):
        data = await request.json()
        assert data.get(aiomodernforms.COMMAND_RF_PAIR_MODE) is False
        modified_response = basic_response.copy()
        modified_response[STATE_RF_PAIR_MODE_ACTIVE] = data[
            aiomodernforms.COMMAND_RF_PAIR_MODE
        ]
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(modified_response),
        )

    aresponses.add("fan.local", "/mf", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        await device.enable_pairing_mode(False)
        assert device.status.rf_pair_mode_active is False


@pytest.mark.asyncio
async def test_clear_paired_devices(aresponses):
    """Test clearing RF-paired devices."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async def evaluate_request(request):
        data = await request.json()
        assert data.get(aiomodernforms.COMMAND_RESET_RF_PAIR_LIST) is True
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(basic_response),
        )

    aresponses.add("fan.local", "/mf", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        await device.clear_paired_devices()


@pytest.mark.asyncio
async def test_factory_reset(aresponses):
    """Test how factory reset is handled, including the resulting disconnect."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        with patch(
            "aiomodernforms.ModernFormsDevice.request",
            side_effect=ModernFormsConnectionTimeoutError,
        ):
            await device.factory_reset()


@pytest.mark.asyncio
async def test_factory_reset_sends_command(aresponses):
    """Test that factory_reset() sends the correct wire-level payload."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async def evaluate_request(request):
        data = await request.json()
        assert data == {aiomodernforms.COMMAND_FACTORY_RESET: True}
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(basic_response),
        )

    aresponses.add("fan.local", "/mf", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        await device.factory_reset()


@pytest.mark.asyncio
async def test_decommission(aresponses):
    """Test how decommission is handled, including the resulting disconnect."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        with patch(
            "aiomodernforms.ModernFormsDevice.request",
            side_effect=ModernFormsConnectionTimeoutError,
        ):
            await device.decommission()


@pytest.mark.asyncio
async def test_decommission_sends_command(aresponses):
    """Test that decommission() sends the correct wire-level payload."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async def evaluate_request(request):
        data = await request.json()
        assert data == {aiomodernforms.COMMAND_DECOMMISSION: True}
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(basic_response),
        )

    aresponses.add("fan.local", "/mf", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        await device.decommission()


@pytest.mark.asyncio
async def test_set_schedule(aresponses):
    """Test setting the schedule blob."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async def evaluate_request(request):
        data = await request.json()
        assert aiomodernforms.COMMAND_SCHEDULE in data
        modified_response = basic_response.copy()
        modified_response[STATE_SCHEDULE] = data[aiomodernforms.COMMAND_SCHEDULE]
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(modified_response),
        )

    aresponses.add("fan.local", "/mf", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        await device.set_schedule("AAAAAPwDAGSgBQAAnAkAZEAL")
        assert device.status.schedule == "AAAAAPwDAGSgBQAAnAkAZEAL"


@pytest.mark.asyncio
async def test_away_requires_argument():
    """Test that away() requires an explicit boolean argument."""
    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        with pytest.raises(TypeError):
            await device.away()  # type: ignore[call-arg]


@pytest.mark.asyncio
async def test_adaptive_learning_requires_argument():
    """Test that adaptive_learning() requires an explicit boolean argument."""
    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        with pytest.raises(TypeError):
            await device.adaptive_learning()  # type: ignore[call-arg]


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
async def test_invalid_setting_breeze_mode(aresponses):
    """Test to make sure setting invalid settings are rejected."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=breeze_mode_response)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        # fan wind speed invlaid value
        with pytest.raises(aiomodernforms.ModernFormsInvalidSettingsError):
            await device.fan(wind_speed="foo")

        # fan wind invlaid value
        with pytest.raises(aiomodernforms.ModernFormsInvalidSettingsError):
            await device.fan(wind="foo")


@pytest.mark.asyncio
async def test_connection_error():
    """Test to make validate proper connection error handling."""
    with pytest.raises(aiomodernforms.ModernFormsConnectionError):
        async with aiomodernforms.ModernFormsDevice("fan.local") as device:
            with patch(
                "aiohttp.ClientSession.request",
                side_effect=aiohttp.ClientConnectionError,
            ):
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


@pytest.mark.asyncio
async def test_reboot(aresponses):
    """Test how reboot is handled."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        with patch(
            "aiomodernforms.ModernFormsDevice.request",
            side_effect=ModernFormsConnectionTimeoutError,
        ):
            await device.reboot()


@pytest.mark.asyncio
async def test_status_not_initialized_response():
    """Test status when not initialized."""
    with pytest.raises(ModernFormsNotInitializedError):
        async with aiomodernforms.ModernFormsDevice("fan.local") as device:
            device.status()


@pytest.mark.asyncio
async def test_info_not_initialized_response():
    """Test info when not initialized."""
    with pytest.raises(ModernFormsNotInitializedError):
        async with aiomodernforms.ModernFormsDevice("fan.local") as device:
            device.info()


@pytest.mark.asyncio
async def test_empty_response():
    """Test for an Empty Response."""

    async def fake_request(_self, commands=None):
        if commands and commands.get(COMMAND_QUERY_STATIC_DATA):
            return basic_info
        return {}

    with pytest.raises(ModernFormsEmptyResponseError):
        async with aiomodernforms.ModernFormsDevice("fan.local") as device:
            with patch(
                "aiomodernforms.ModernFormsDevice._request",
                side_effect=fake_request,
                autospec=True,
            ):
                await device.update()
