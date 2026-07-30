"""Tests for Async IO Modern Forms Library."""

import json
from datetime import datetime, timedelta
from unittest.mock import patch

import aiohttp
import pytest

import aiomodernforms
from aiomodernforms import gen4
from aiomodernforms.const import (
    ADAPTIVE_LEARNING_ON,
    AWAY_MODE_ON,
    COMMAND_IDENTIFY,
    COMMAND_LIGHT_COLOR_TEMP,
    COMMAND_QUERY_STATIC_DATA,
    FAN_SPEED_HIGH_VALUE,
    FAN_SPEED_LOW_VALUE,
    INFO_DEVICE_NAME,
    INFO_FIRMWARE_VERSION,
    INFO_MAIN_MCU_FIRMWARE_VERSION,
    INFO_OWNER,
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
    STATE_LIGHT_COLOR_TEMP,
    STATE_LIGHT_FIXTURES,
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
    ModernFormsNotSupportedError,
)
from aiomodernforms.models import Device, Generation, State


def test_not_supported_error_is_an_exception():
    """Test that ModernFormsNotSupportedError exists and is a real exception."""
    with pytest.raises(ModernFormsNotSupportedError):
        raise ModernFormsNotSupportedError("not supported on this generation")


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

gen4_device_response = {
    "systemType": "fan_g4",
    "deviceName": "Fan",
    "owner": "someone@somewhere.com",
    "iotmVer": "01.00.0082",
    "scmVer": "01.00.0012",
    "awayModeEnabled": False,
    "nwkState": {
        "certificateID": "abc123certid",
        "rssi": "-42",
    },
}

gen4_fan_fixture = {
    "addr": 218103808,
    "name": "Fan",
    "type": 13,
    "state": {
        "status": False,
        "fanSpeed": 3,
        "fanDirection": False,
        "wind": False,
        "windSpeed": 2,
    },
}

gen4_light_fixture = {
    "addr": 83951616,
    "name": "Light",
    "type": 1,
    "state": {
        "status": False,
        "level": 5000,
        "mixColorTemp": 3000,
    },
    "detail": {
        "minColorTemp": 2700,
        "maxColorTemp": 5000,
    },
}

gen4_wall_station_fixture = {
    "addr": 184549376,
    "name": "Remote",
    "type": 11,
    "state": {},
}


def _mock_gen4_device(aresponses, fixtures=None):
    """Register the request sequence a Gen4 device's first update() makes.

    update() tries /mf first (so legacy fans need no special mocking) and
    only falls back to probing /device when that fails — so every Gen4 test
    must mock /mf failing first, then /device, then /fixture, in that order.
    """
    aresponses.add(
        "fan.local",
        "/mf",
        "POST",
        response=aresponses.Response(text="not found", status=404),
    )
    aresponses.add("fan.local", "/device", "POST", response=gen4_device_response)
    fixture_list = (
        fixtures if fixtures is not None else [gen4_fan_fixture, gen4_light_fixture]
    )
    aresponses.add(
        "fan.local",
        "/fixture",
        "POST",
        response={
            "action": 3,
            "result": "0",
            "count": len(fixture_list),
            "fixture": fixture_list,
        },
    )


@pytest.mark.asyncio
async def test_update_detects_gen4(aresponses):
    """Test that update() falls back to /device and detects a Gen4 fan."""
    _mock_gen4_device(aresponses)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        assert device._device.generation == Generation.GEN4
        assert device.status.fan_speed == 3
        assert device.status.light_brightness == 50
        assert len(device.status.light_fixtures) == 1
        assert device.info.device_name == "Fan"
        assert device._gen4_fan_addr == 218103808


@pytest.mark.asyncio
async def test_update_uses_legacy_without_probing_device(aresponses):
    """Test that update() never touches /device when /mf succeeds immediately."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        assert device._device.generation == Generation.GEN1_2
        assert device.status.fan_speed == basic_response["fanSpeed"]
        # No /device mock was registered above — if update() had probed it,
        # aresponses would raise a route-not-found error for that request.


@pytest.mark.asyncio
async def test_update_reraises_legacy_error_when_device_also_not_gen4(aresponses):
    """Test that a device failing both /mf and /device surfaces the /mf error."""
    aresponses.add(
        "fan.local",
        "/mf",
        "POST",
        response=aresponses.Response(text="not found", status=404),
    )
    aresponses.add(
        "fan.local",
        "/device",
        "POST",
        response=aresponses.Response(text="not found", status=404),
    )

    with pytest.raises(aiomodernforms.ModernFormsError):
        async with aiomodernforms.ModernFormsDevice("fan.local") as device:
            await device.update()


@pytest.mark.asyncio
async def test_update_probe_handles_non_json_response(aresponses):
    """Test that a non-JSON 200 response from /device doesn't crash update().

    Regression test: _probe_gen4() only caught ModernFormsError, but the
    `await response.json()` call in _request() sits outside the
    aiohttp.ClientError-to-ModernFormsError translation — so a device that
    answers `POST /device` with HTTP 200 and a non-JSON body (an HTML
    error page, a captive portal, any non-fan device at this host) used to
    raise a raw aiohttp.ContentTypeError straight out of update(), instead
    of falling through to the original /mf error like every other probe
    failure.
    """
    aresponses.add(
        "fan.local",
        "/mf",
        "POST",
        response=aresponses.Response(text="not found", status=404),
    )
    aresponses.add(
        "fan.local",
        "/device",
        "POST",
        response=aresponses.Response(
            text="<html>captive portal</html>", status=200, content_type="text/html"
        ),
    )

    with pytest.raises(aiomodernforms.ModernFormsError):
        async with aiomodernforms.ModernFormsDevice("fan.local") as device:
            await device.update()


@pytest.mark.asyncio
async def test_update_only_probes_gen4_once(aresponses):
    """Test that a second update() call skips straight to /device + /fixture."""
    _mock_gen4_device(aresponses)
    aresponses.add("fan.local", "/device", "POST", response=gen4_device_response)
    aresponses.add(
        "fan.local",
        "/fixture",
        "POST",
        response={
            "action": 3,
            "result": "0",
            "count": 2,
            "fixture": [gen4_fan_fixture, gen4_light_fixture],
        },
    )

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        await device.update()
        # The second update() call has no /mf mock registered and only one
        # more /device + /fixture pair above — if it had re-attempted /mf or
        # re-probed generation an extra time, aresponses would raise.


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
async def test_config_gen4(aresponses):
    """Test config() against a Gen4 device — maps /device fields into ConfigInfo."""
    _mock_gen4_device(aresponses)
    aresponses.add("fan.local", "/device", "POST", response=gen4_device_response)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        config = await device.config()
        assert config.device_name == "Fan"
        assert config.firmware_version == "01.00.0082"
        assert config.rf_version == "01.00.0012"
        assert config.certificate_id == "abc123certid"
        assert config.wifi_strength == "-42"
        assert config.hardware_revision == ""
        assert config.protocol == ""


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
        modified_response[
            STATE_LIGHT_BRIGHTNESS
        ] = aiomodernforms.LIGHT_BRIGHTNESS_HIGH_VALUE
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
        modified_response[
            STATE_LIGHT_BRIGHTNESS
        ] = aiomodernforms.LIGHT_BRIGHTNESS_HIGH_VALUE
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
async def test_light_invalid_sleep_raises_before_any_request(aresponses):
    """Test that an invalid `sleep` value raises before any request is sent.

    Regression test: light(brightness=..., on=True, sleep=<invalid>) used
    to send the brightness-only request (from the brightness/on split
    below) before the invalid `sleep` value was ever validated, leaving
    the device half-mutated. Only the update() mocks are registered here
    — if light() sent anything before raising, this test would fail with
    a route-not-found error instead of the expected
    ModernFormsInvalidSettingsError.
    """
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    invalid_sleep = datetime.now() + timedelta(hours=25)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        with pytest.raises(aiomodernforms.ModernFormsInvalidSettingsError):
            await device.light(brightness=50, on=True, sleep=invalid_sleep)


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
async def test_fan_identify_ignored_on_legacy(aresponses):
    """Test that identify is silently dropped for gen1_2/gen3, never sent.

    Regression test: identify previously had no generation gate, so
    fan(identify=True) sent {"identify": true} to /mf on legacy fans,
    contradicting the design spec's "silently ignored otherwise" — which
    means never sent at all, not sent-and-ignored-by-the-device.
    """
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async def evaluate_request(request):
        data = await request.json()
        assert aiomodernforms.COMMAND_FAN_POWER in data
        assert COMMAND_IDENTIFY not in data
        modified_response = basic_response.copy()
        modified_response[STATE_FAN_POWER] = data[aiomodernforms.COMMAND_FAN_POWER]
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(modified_response),
        )

    aresponses.add("fan.local", "/mf", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        await device.fan(on=True, identify=True)


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
async def test_generation_defaults_gen1_2(aresponses):
    """Test that a device with no relative timers is classified gen1_2."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        assert device._device.generation == Generation.GEN1_2
        assert device._device.has_adaptive_learning() is True
        assert device._device.has_sleep_timer() is True
        assert device._device.has_identify() is False


@pytest.mark.asyncio
async def test_generation_gen3_from_relative_timers(aresponses):
    """Test that a device with relative timers is classified gen3."""
    aresponses.add("fan.local", "/mf", "POST", response=gen3_info)
    aresponses.add("fan.local", "/mf", "POST", response=gen3_relative_timer_response)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        assert device._device.generation == Generation.GEN3


def test_light_fixtures_synthetic_entry_for_legacy():
    """Test that gen1_2/gen3 responses get a single synthetic Light entry."""
    device = Device(state_data=basic_response, info_data=basic_info)
    assert len(device.state.light_fixtures) == 1
    light = device.state.light_fixtures[0]
    assert light.address is None
    assert light.fixture_type is None
    assert light.on == basic_response["lightOn"]
    assert light.brightness == basic_response["lightBrightness"]
    assert light.color_temp_kelvin is None
    assert light.min_color_temp_kelvin is None
    assert light.max_color_temp_kelvin is None
    assert device.state.light_color_temp_kelvin is None


def test_state_to_dict_round_trips_through_from_dict():
    """Test that State.to_dict() is the inverse of State.from_dict()."""
    device = Device(state_data=gen3_relative_timer_response, info_data=gen3_info)
    round_tripped = State.from_dict(device.state.to_dict())
    assert round_tripped == device.state


def test_device_accepts_explicit_generation():
    """Test that Device.__init__ honors an explicitly passed generation."""
    device = Device(
        state_data=basic_response,
        info_data=basic_info,
        generation=Generation.GEN4,
    )
    assert device.generation == Generation.GEN4
    assert device.has_adaptive_learning() is False
    assert device.has_sleep_timer() is False
    assert device.has_identify() is True


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
async def test_fan_gen4_sends_to_fixture_endpoint(aresponses):
    """Test that fan() on a Gen4 device posts to /fixture with the real addr."""
    _mock_gen4_device(aresponses)

    async def evaluate_request(request):
        data = await request.json()
        assert data["action"] == 4
        assert data["addr"] == 218103808
        assert data["state"] == {"status": True, "fanSpeed": 5}
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(
                {
                    "action": 4,
                    "result": "0",
                    "state": {"status": True, "fanSpeed": 5},
                }
            ),
        )

    aresponses.add("fan.local", "/fixture", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        await device.fan(on=True, speed=5)
        assert device.status.fan_on is True
        assert device.status.fan_speed == 5
        # Fields not touched by this call stay at their pre-call values.
        assert device.status.light_brightness == 50


@pytest.mark.asyncio
async def test_fan_gen4_identify(aresponses):
    """Test that fan(identify=True) sends findme to the fixture."""
    _mock_gen4_device(aresponses)

    async def evaluate_request(request):
        data = await request.json()
        assert data["state"] == {"findme": True}
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps({"action": 4, "result": "0", "state": {}}),
        )

    aresponses.add("fan.local", "/fixture", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        await device.fan(identify=True)


@pytest.mark.asyncio
async def test_fan_gen4_sleep_is_a_silent_noop(aresponses):
    """Test that fan(sleep=...) on Gen4 sends no timer field at all."""
    _mock_gen4_device(aresponses)

    async def evaluate_request(request):
        data = await request.json()
        assert data["state"] == {"status": True}
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps({"action": 4, "result": "0", "state": {"status": True}}),
        )

    aresponses.add("fan.local", "/fixture", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        await device.fan(on=True, sleep=90)


@pytest.mark.asyncio
async def test_light_gen4_sends_to_primary_fixture(aresponses):
    """Test that light() on Gen4 controls light_fixtures[0]'s real address."""
    _mock_gen4_device(aresponses)

    async def evaluate_request(request):
        data = await request.json()
        assert data["addr"] == 83951616
        assert data["state"] == {"status": True, "level": 8000}
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(
                {"action": 4, "result": "0", "state": {"status": True, "level": 8000}}
            ),
        )

    aresponses.add("fan.local", "/fixture", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        await device.light(on=True, brightness=80)
        assert device.status.light_on is True
        assert device.status.light_brightness == 80
        assert device.status.light_fixtures[0].on is True
        assert device.status.light_fixtures[0].brightness == 80


@pytest.mark.asyncio
async def test_light_gen4_color_temp(aresponses):
    """Test that light(color_temp_kelvin=...) sends mixColorTemp."""
    _mock_gen4_device(aresponses)

    async def evaluate_request(request):
        data = await request.json()
        assert data["state"] == {"mixColorTemp": 4500}
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(
                {"action": 4, "result": "0", "state": {"mixColorTemp": 4500}}
            ),
        )

    aresponses.add("fan.local", "/fixture", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        await device.light(color_temp_kelvin=4500)
        assert device.status.light_color_temp_kelvin == 4500


@pytest.mark.asyncio
async def test_light_color_temp_ignored_on_legacy(aresponses):
    """Test that color_temp_kelvin is silently dropped for gen1_2/gen3."""
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async def evaluate_request(request):
        data = await request.json()
        assert aiomodernforms.COMMAND_LIGHT_POWER in data
        assert COMMAND_LIGHT_COLOR_TEMP not in data
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
        await device.light(on=True, color_temp_kelvin=4500)


@pytest.mark.asyncio
async def test_light_identify_ignored_on_legacy(aresponses):
    """Test that identify is silently dropped for gen1_2/gen3, never sent.

    Regression test: identify previously had no generation gate, so
    light(identify=True) sent {"identify": true} to /mf on legacy fans,
    contradicting the design spec's "silently ignored otherwise" — which
    means never sent at all, not sent-and-ignored-by-the-device.
    """
    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async def evaluate_request(request):
        data = await request.json()
        assert aiomodernforms.COMMAND_LIGHT_POWER in data
        assert COMMAND_IDENTIFY not in data
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
        await device.light(on=True, identify=True)


@pytest.mark.asyncio
async def test_light_fixture_controls_a_specific_address(aresponses):
    """Test that light_fixture() addresses a light directly, not via index 0."""
    second_light = {**gen4_light_fixture, "addr": 83951617, "name": "Uplight"}
    _mock_gen4_device(
        aresponses, fixtures=[gen4_fan_fixture, gen4_light_fixture, second_light]
    )

    async def evaluate_request(request):
        data = await request.json()
        assert data["addr"] == 83951617
        assert data["state"] == {"status": True}
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps({"action": 4, "result": "0", "state": {"status": True}}),
        )

    aresponses.add("fan.local", "/fixture", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        assert len(device.status.light_fixtures) == 2
        await device.light_fixture(83951617, on=True)
        assert device.status.light_fixtures[1].on is True
        # The primary light (index 0) and its flat mirror fields are untouched.
        assert device.status.light_fixtures[0].on is False
        assert device.status.light_on is False


@pytest.mark.asyncio
async def test_light_fixture_none_address_routes_through_legacy(aresponses):
    """Test that light_fixture(None, ...) works on gen1_2/gen3 like light()."""
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
        await device.light_fixture(None, on=True)
        assert device.status.light_on is True


def test_has_identify_true_only_for_gen4():
    """Test has_identify() reflects generation."""
    legacy_device = Device(state_data=basic_response, info_data=basic_info)
    gen4_device = Device(
        state_data=basic_response, info_data=basic_info, generation=Generation.GEN4
    )
    assert legacy_device.has_identify() is False
    assert gen4_device.has_identify() is True


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
async def test_away_gen4_sends_to_device_endpoint(aresponses):
    """Test that away() on Gen4 posts to /device, not /fixture or /mf."""
    _mock_gen4_device(aresponses)

    async def evaluate_request(request):
        data = await request.json()
        assert data == {aiomodernforms.COMMAND_AWAY_MODE: True}
        return aresponses.Response(
            status=200,
            content_type="application/json",
            text=json.dumps({"awayModeEnabled": True}),
        )

    aresponses.add("fan.local", "/device", "POST", response=evaluate_request)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        await device.away(True)
        assert device.status.away_mode_enabled is True


@pytest.mark.asyncio
async def test_adaptive_learning_gen4_is_a_silent_noop(aresponses):
    """Test that adaptive_learning() on Gen4 sends nothing and doesn't error."""
    _mock_gen4_device(aresponses)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        await device.adaptive_learning(True)
        # No aresponses mock was registered for a follow-up /device or /mf
        # request — if adaptive_learning() sent anything, this test would
        # fail with a route-not-found error.
        assert device.status.adaptive_learning_enabled is False


@pytest.mark.asyncio
async def test_has_adaptive_learning_and_has_sleep_timer(aresponses):
    """Test the two new capability wrapper methods."""
    _mock_gen4_device(aresponses)

    async with aiomodernforms.ModernFormsDevice("fan.local") as gen4_device:
        await gen4_device.update()
        assert gen4_device.has_adaptive_learning() is False
        assert gen4_device.has_sleep_timer() is False

    aresponses.add("fan.local", "/mf", "POST", response=basic_info)
    aresponses.add("fan.local", "/mf", "POST", response=basic_response)

    async with aiomodernforms.ModernFormsDevice("fan.local") as legacy_device:
        await legacy_device.update()
        assert legacy_device.has_adaptive_learning() is True
        assert legacy_device.has_sleep_timer() is True


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
async def test_factory_reset_never_updated_swallows_timeout():
    """Test factory_reset() swallows a timeout from its implicit update().

    Regression test: the implicit `if self._device is None: await
    self.update()` used to sit outside the try/except that swallows
    ModernFormsConnectionTimeoutError (matching "a successful factory
    reset drops the connection"), so this exact scenario used to raise
    uncaught. No aresponses mocks are registered — update() is patched
    directly, so no HTTP request is made at all.
    """
    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        with patch(
            "aiomodernforms.ModernFormsDevice.update",
            side_effect=ModernFormsConnectionTimeoutError,
        ):
            await device.factory_reset()
        assert device._device is None


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
async def test_decommission_never_updated_swallows_timeout():
    """Test decommission() swallows a timeout from its implicit update().

    See test_factory_reset_never_updated_swallows_timeout for the full
    regression rationale — same class of bug, same fix, same convention.
    """
    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        with patch(
            "aiomodernforms.ModernFormsDevice.update",
            side_effect=ModernFormsConnectionTimeoutError,
        ):
            await device.decommission()
        assert device._device is None


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
async def test_reboot_never_updated_swallows_timeout():
    """Test reboot() swallows a timeout from its implicit update().

    See test_factory_reset_never_updated_swallows_timeout for the full
    regression rationale — same class of bug, same fix, same convention.
    """
    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        with patch(
            "aiomodernforms.ModernFormsDevice.update",
            side_effect=ModernFormsConnectionTimeoutError,
        ):
            await device.reboot()
        assert device._device is None


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


def test_is_gen4_system_type_matches():
    """Test that the fan_g4 systemType marker is recognized."""
    assert gen4.is_gen4_system_type("fan_g4") is True
    assert gen4.is_gen4_system_type("FAN_G4") is True
    assert gen4.is_gen4_system_type("gen3fan") is False
    assert gen4.is_gen4_system_type("strut") is False


def test_classify_fixtures_splits_fan_and_lights():
    """Test that classify_fixtures finds the fan, the light, and ignores others."""
    fan, lights = gen4.classify_fixtures(
        [gen4_fan_fixture, gen4_light_fixture, gen4_wall_station_fixture]
    )
    assert fan == gen4_fan_fixture
    assert lights == [gen4_light_fixture]


def test_classify_fixtures_handles_no_lights():
    """Test that classify_fixtures returns an empty light list when none exist."""
    fan, lights = gen4.classify_fixtures([gen4_fan_fixture])
    assert fan == gen4_fan_fixture
    assert lights == []


def test_build_state_data_maps_fan_and_light_fields():
    """Test build_state_data's fan+light field mapping."""
    state_data = gen4.build_state_data(
        gen4_device_response, gen4_fan_fixture, [gen4_light_fixture]
    )
    assert state_data[STATE_FAN_POWER] is False
    assert state_data[STATE_FAN_SPEED] == 3
    assert state_data[STATE_FAN_DIRECTION] == "forward"
    assert state_data[STATE_WIND_POWER] is False
    assert state_data[STATE_WIND_SPEED] == 2
    assert state_data[STATE_AWAY_MODE] is False
    assert state_data[STATE_LIGHT_POWER] is False
    assert state_data[STATE_LIGHT_BRIGHTNESS] == 50
    assert state_data[STATE_LIGHT_COLOR_TEMP] == 3000

    light_fixtures = state_data[STATE_LIGHT_FIXTURES]
    assert len(light_fixtures) == 1
    light = light_fixtures[0]
    assert light.address == 83951616
    assert light.fixture_type == 1
    assert light.name == "Light"
    assert light.min_color_temp_kelvin == 2700
    assert light.max_color_temp_kelvin == 5000


def test_build_state_data_reverse_direction():
    """Test that a True fanDirection (gen4 boolean) maps to the reverse string."""
    reversed_fan = {
        **gen4_fan_fixture,
        "state": {**gen4_fan_fixture["state"], "fanDirection": True},
    }
    state_data = gen4.build_state_data(gen4_device_response, reversed_fan, [])
    assert state_data[STATE_FAN_DIRECTION] == "reverse"


def test_build_state_data_no_lights_uses_synthetic_default():
    """Test that a fan with zero light fixtures gets a sensible default light."""
    state_data = gen4.build_state_data(gen4_device_response, gen4_fan_fixture, [])
    assert state_data[STATE_LIGHT_FIXTURES] == []
    assert state_data[STATE_LIGHT_POWER] is False
    assert state_data[STATE_LIGHT_BRIGHTNESS] == 100


def test_build_info_data_maps_device_fields():
    """Test that build_info_data maps /device fields into canonical INFO_* keys."""
    info_data = gen4.build_info_data(gen4_device_response)
    assert info_data[INFO_DEVICE_NAME] == "Fan"
    assert info_data[INFO_FIRMWARE_VERSION] == "01.00.0082"
    assert info_data[INFO_MAIN_MCU_FIRMWARE_VERSION] == "01.00.0012"
    assert info_data[INFO_OWNER] == "someone@somewhere.com"


def test_build_fan_control_state_translates_all_fields():
    """Test that a canonical fan commands dict becomes a gen4 fixture state."""
    commands = {
        aiomodernforms.COMMAND_FAN_POWER: True,
        aiomodernforms.COMMAND_FAN_SPEED: 4,
        aiomodernforms.COMMAND_FAN_DIRECTION: aiomodernforms.FAN_DIRECTION_REVERSE,
        aiomodernforms.COMMAND_WIND: True,
        aiomodernforms.COMMAND_WIND_SPEED: 2,
        COMMAND_IDENTIFY: True,
    }
    state = gen4.build_fan_control_state(commands)
    assert state == {
        "status": True,
        "fanSpeed": 4,
        "fanDirection": True,
        "wind": True,
        "windSpeed": 2,
        "findme": True,
    }


def test_build_fan_control_state_only_includes_given_fields():
    """Test that fields not present in commands are omitted, not defaulted."""
    state = gen4.build_fan_control_state({aiomodernforms.COMMAND_FAN_POWER: False})
    assert state == {"status": False}


def test_build_light_control_state_scales_brightness():
    """Test that a canonical light commands dict becomes a gen4 fixture state."""
    commands = {
        aiomodernforms.COMMAND_LIGHT_POWER: True,
        aiomodernforms.COMMAND_LIGHT_BRIGHTNESS: 75,
        COMMAND_LIGHT_COLOR_TEMP: 3000,
        COMMAND_IDENTIFY: False,
    }
    state = gen4.build_light_control_state(commands)
    assert state == {
        "status": True,
        "level": 7500,
        "mixColorTemp": 3000,
        "findme": False,
    }


def test_parse_fan_control_response_translates_back():
    """Test that an echoed gen4 fan state maps back to canonical STATE_* keys."""
    result = gen4.parse_fan_control_response(
        {"status": True, "fanSpeed": 4, "fanDirection": True, "wind": False}
    )
    assert result == {
        STATE_FAN_POWER: True,
        STATE_FAN_SPEED: 4,
        STATE_FAN_DIRECTION: "reverse",
        STATE_WIND_POWER: False,
    }


def test_parse_light_control_response_scales_brightness_back():
    """Test that an echoed gen4 light state maps back to canonical STATE_* keys."""
    result = gen4.parse_light_control_response(
        {"status": True, "level": 2500, "mixColorTemp": 4000}
    )
    assert result == {
        STATE_LIGHT_POWER: True,
        STATE_LIGHT_BRIGHTNESS: 25,
        STATE_LIGHT_COLOR_TEMP: 4000,
    }


@pytest.mark.asyncio
async def test_reboot_gen4(aresponses):
    """Test reboot() on Gen4 posts {"reboot": True} to /device."""
    _mock_gen4_device(aresponses)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        with patch(
            "aiomodernforms.ModernFormsDevice._request",
            side_effect=ModernFormsConnectionTimeoutError,
        ):
            await device.reboot()


@pytest.mark.asyncio
async def test_factory_reset_gen4_sends_hard_factory_reset(aresponses):
    """Test that factory_reset() on Gen4 sends hardFactoryReset, not factoryReset."""
    _mock_gen4_device(aresponses)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        with patch(
            "aiomodernforms.ModernFormsDevice._request",
            side_effect=ModernFormsConnectionTimeoutError,
        ) as mock_request:
            await device.factory_reset()
            mock_request.assert_called_once_with(
                {"hardFactoryReset": True}, path="device"
            )


@pytest.mark.asyncio
async def test_gen4_unsupported_methods_raise(aresponses):
    """Test that decommission/pairing/schedule raise on Gen4."""
    _mock_gen4_device(aresponses)

    async with aiomodernforms.ModernFormsDevice("fan.local") as device:
        await device.update()
        with pytest.raises(ModernFormsNotSupportedError):
            await device.decommission()
        with pytest.raises(ModernFormsNotSupportedError):
            await device.enable_pairing_mode()
        with pytest.raises(ModernFormsNotSupportedError):
            await device.clear_paired_devices()
        with pytest.raises(ModernFormsNotSupportedError):
            await device.set_schedule("AAAA")
