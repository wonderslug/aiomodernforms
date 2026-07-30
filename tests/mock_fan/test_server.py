"""Integration tests: drive the mock fan server with the real aiomodernforms client."""

import asyncio
import logging

import pytest
from aiohttp.test_utils import TestClient, TestServer

import aiomodernforms
from aiomodernforms.const import FAN_DIRECTION_REVERSE
from mock_fan.generations import GEN1_2, GEN3
from mock_fan.server import create_app, create_gen4_app


@pytest.mark.asyncio
async def test_update_populates_info_and_state_gen1_2():
    """update() against a Gen 1/2 mock fan populates Info and State correctly."""
    app = create_app(GEN1_2, breeze=False)
    async with TestClient(TestServer(app)) as client:
        async with aiomodernforms.ModernFormsDevice(
            client.host, port=client.port, session=client.session
        ) as device:
            await device.update()
            assert device.info.fan_type == GEN1_2.fan_type
            assert device.info.light_type == GEN1_2.light_type
            assert device.status.fan_on is False
            assert device.status.fan_speed == 3
            assert device.has_breeze_mode() is False
            assert device.has_relative_timers() is False


@pytest.mark.asyncio
async def test_update_populates_info_and_state_gen3():
    """update() against a Gen 3 mock fan reports gen3 info/capabilities."""
    app = create_app(GEN3, breeze=True)
    async with TestClient(TestServer(app)) as client:
        async with aiomodernforms.ModernFormsDevice(
            client.host, port=client.port, session=client.session
        ) as device:
            await device.update()
            assert device.info.fan_type == GEN3.fan_type
            assert device.info.brand == GEN3.brand
            assert device.info.light_type == GEN3.light_type
            assert device.has_breeze_mode() is True
            assert device.has_relative_timers() is True


@pytest.mark.asyncio
async def test_light_type_empty_when_light_disabled():
    """A light=False fan reports an empty lightType, not the profile's value.

    Keeps static info and the dynamic shadow in agreement about whether
    the fan has a light, mirroring how a real fan-only unit has no light
    kit installed at all (see GEN3's docstring reference for context).
    """
    app = create_app(GEN3, breeze=False, light=False)
    async with TestClient(TestServer(app)) as client:
        async with aiomodernforms.ModernFormsDevice(
            client.host, port=client.port, session=client.session
        ) as device:
            await device.update()
            assert device.info.light_type == ""


@pytest.mark.asyncio
async def test_activity_logging_static_info_status_and_config(caplog):
    """update() and config() log a static info, status read, and config-read line."""
    caplog.set_level(logging.INFO)
    app = create_app(GEN1_2, breeze=False)
    async with TestClient(TestServer(app)) as client:
        async with aiomodernforms.ModernFormsDevice(
            client.host, port=client.port, session=client.session
        ) as device:
            await device.update()
            await device.config()

    assert "static info request" in caplog.text
    assert "status read (no changes)" in caplog.text
    assert "config-read request" in caplog.text


@pytest.mark.asyncio
async def test_activity_logging_applied_changes(caplog):
    """A command that changes state logs the changed fields."""
    caplog.set_level(logging.INFO)
    app = create_app(GEN1_2, breeze=False)
    async with TestClient(TestServer(app)) as client:
        async with aiomodernforms.ModernFormsDevice(
            client.host, port=client.port, session=client.session
        ) as device:
            await device.update()
            await device.fan(on=True, speed=5)

    assert "applied changes:" in caplog.text
    assert "'fanOn': True" in caplog.text
    assert "'fanSpeed': 5" in caplog.text


@pytest.mark.asyncio
async def test_activity_logging_disruptive_command_and_hold(caplog):
    """A reboot logs the trigger, then a follow-up request logs the held connection."""
    caplog.set_level(logging.INFO)
    # Long enough that the two backoff-retry sequences below (reboot's own,
    # then the follow-up update()'s) can't outrun the disconnect window —
    # neither actually waits this long, they just need the window still
    # open when the second one fires.
    app = create_app(GEN1_2, breeze=False, resume_delay_secs=20.0)
    async with TestClient(TestServer(app)) as client:
        async with aiomodernforms.ModernFormsDevice(
            client.host,
            port=client.port,
            session=client.session,
            request_timeout=0.2,
        ) as device:
            await device.update()
            await device.reboot()  # must not raise; timeout is swallowed

            with pytest.raises(aiomodernforms.ModernFormsConnectionTimeoutError):
                await device.update()  # still inside the disconnect window

    assert "reboot received — disconnecting for 20.0s" in caplog.text
    assert "holding connection" in caplog.text


@pytest.mark.asyncio
async def test_light_and_fan_round_trip():
    """light()/fan() commands round-trip through the mock fan."""
    app = create_app(GEN1_2, breeze=False)
    async with TestClient(TestServer(app)) as client:
        async with aiomodernforms.ModernFormsDevice(
            client.host, port=client.port, session=client.session
        ) as device:
            await device.update()
            await device.light(on=True, brightness=75)
            assert device.status.light_on is True
            assert device.status.light_brightness == 75

            await device.fan(on=True, speed=5, direction=FAN_DIRECTION_REVERSE)
            assert device.status.fan_on is True
            assert device.status.fan_speed == 5
            assert device.status.fan_direction == FAN_DIRECTION_REVERSE


@pytest.mark.asyncio
async def test_away_and_adaptive_learning_round_trip():
    """away()/adaptive_learning() commands round-trip through the mock fan."""
    app = create_app(GEN1_2, breeze=False)
    async with TestClient(TestServer(app)) as client:
        async with aiomodernforms.ModernFormsDevice(
            client.host, port=client.port, session=client.session
        ) as device:
            await device.update()
            await device.away(True)
            assert device.status.away_mode_enabled is True

            await device.adaptive_learning(True)
            assert device.status.adaptive_learning_enabled is True


@pytest.mark.asyncio
async def test_config_read_gen1_2():
    """config() against a Gen 1/2 mock fan returns gen1/2-shaped fields."""
    app = create_app(GEN1_2, breeze=False)
    async with TestClient(TestServer(app)) as client:
        async with aiomodernforms.ModernFormsDevice(
            client.host, port=client.port, session=client.session
        ) as device:
            config = await device.config()
            assert config.protocol == "com.modernforms.fan"
            assert config.hardware_revision == "WAC_WINDERMIER_REV_5"
            assert config.wifi_strength == "100"


@pytest.mark.asyncio
async def test_config_read_gen3():
    """config() against a Gen 3 mock fan returns gen3-shaped fields."""
    app = create_app(GEN3, breeze=False)
    async with TestClient(TestServer(app)) as client:
        async with aiomodernforms.ModernFormsDevice(
            client.host, port=client.port, session=client.session
        ) as device:
            config = await device.config()
            assert config.protocol == "com.modernforms.fan"
            assert config.hardware_revision == ""
            assert config.firmware_version == "02.00.0043"
            assert config.wifi_strength == "-48"


@pytest.mark.asyncio
async def test_reboot_disconnects_then_resumes():
    """reboot() times out (swallowed) then the fan resumes responding."""
    app = create_app(GEN1_2, breeze=False, resume_delay_secs=0.05)
    async with TestClient(TestServer(app)) as client:
        async with aiomodernforms.ModernFormsDevice(
            client.host,
            port=client.port,
            session=client.session,
            request_timeout=0.2,
        ) as device:
            await device.update()
            await device.reboot()  # must not raise; timeout is swallowed

            await asyncio.sleep(0.1)
            await device.update()  # must succeed again after resume delay
            assert device.status.fan_on is False


@pytest.mark.asyncio
async def test_factory_reset_resets_state():
    """factory_reset() resets dynamic shadow state to startup defaults."""
    app = create_app(GEN1_2, breeze=False, resume_delay_secs=0.05)
    async with TestClient(TestServer(app)) as client:
        async with aiomodernforms.ModernFormsDevice(
            client.host,
            port=client.port,
            session=client.session,
            request_timeout=0.2,
        ) as device:
            await device.update()
            await device.fan(on=True, speed=6)
            assert device.status.fan_on is True

            await device.factory_reset()  # must not raise

            await asyncio.sleep(0.1)
            await device.update()
            assert device.status.fan_on is False
            assert device.status.fan_speed == 3


@pytest.mark.asyncio
async def test_light_disabled_ignores_light_commands():
    """A light=False fan silently ignores light() commands end-to-end."""
    app = create_app(GEN1_2, breeze=False, light=False)
    async with TestClient(TestServer(app)) as client:
        async with aiomodernforms.ModernFormsDevice(
            client.host, port=client.port, session=client.session
        ) as device:
            await device.update()
            await device.light(on=True, brightness=75)
            assert device.status.light_on is False
            assert device.status.light_brightness == 100


@pytest.mark.asyncio
async def test_gen4_update_populates_info_and_state():
    """update() against a mock Gen4 fan populates State/Info/generation correctly."""
    app = create_gen4_app(lights=1)
    async with TestClient(TestServer(app)) as client:
        async with aiomodernforms.ModernFormsDevice(
            client.host, port=client.port, session=client.session
        ) as device:
            await device.update()
            assert device.status.fan_on is False
            assert device.status.fan_speed == 3
            assert len(device.status.light_fixtures) == 1
            assert device.has_adaptive_learning() is False
            assert device.has_sleep_timer() is False
            assert device.has_identify() is True


@pytest.mark.asyncio
async def test_gen4_zero_lights():
    """A Gen4 mock fan with lights=0 reports no light fixtures."""
    app = create_gen4_app(lights=0)
    async with TestClient(TestServer(app)) as client:
        async with aiomodernforms.ModernFormsDevice(
            client.host, port=client.port, session=client.session
        ) as device:
            await device.update()
            assert device.status.light_fixtures == []


@pytest.mark.asyncio
async def test_gen4_multiple_lights():
    """A Gen4 mock fan with lights=3 exposes three independently addressable lights."""
    app = create_gen4_app(lights=3)
    async with TestClient(TestServer(app)) as client:
        async with aiomodernforms.ModernFormsDevice(
            client.host, port=client.port, session=client.session
        ) as device:
            await device.update()
            assert len(device.status.light_fixtures) == 3

            second_light_addr = device.status.light_fixtures[1].address
            await device.light_fixture(second_light_addr, on=True, brightness=80)
            assert device.status.light_fixtures[1].on is True
            assert device.status.light_fixtures[1].brightness == 80
            # The other lights are untouched.
            assert device.status.light_fixtures[0].on is False
            assert device.status.light_fixtures[2].on is False


@pytest.mark.asyncio
async def test_gen4_fan_and_light_round_trip():
    """fan()/light() commands round-trip through the mock Gen4 fan."""
    app = create_gen4_app(lights=1)
    async with TestClient(TestServer(app)) as client:
        async with aiomodernforms.ModernFormsDevice(
            client.host, port=client.port, session=client.session
        ) as device:
            await device.update()
            await device.fan(on=True, speed=5, direction=FAN_DIRECTION_REVERSE)
            assert device.status.fan_on is True
            assert device.status.fan_speed == 5
            assert device.status.fan_direction == FAN_DIRECTION_REVERSE

            await device.light(on=True, brightness=75)
            assert device.status.light_on is True
            assert device.status.light_brightness == 75


@pytest.mark.asyncio
async def test_gen4_away_round_trip():
    """away() round-trips through the mock Gen4 fan's /device endpoint."""
    app = create_gen4_app(lights=0)
    async with TestClient(TestServer(app)) as client:
        async with aiomodernforms.ModernFormsDevice(
            client.host, port=client.port, session=client.session
        ) as device:
            await device.update()
            await device.away(True)
            assert device.status.away_mode_enabled is True


@pytest.mark.asyncio
async def test_gen4_unsupported_methods_raise():
    """decommission/pairing/schedule raise ModernFormsNotSupportedError on mock Gen4."""
    app = create_gen4_app(lights=0)
    async with TestClient(TestServer(app)) as client:
        async with aiomodernforms.ModernFormsDevice(
            client.host, port=client.port, session=client.session
        ) as device:
            await device.update()
            with pytest.raises(aiomodernforms.ModernFormsNotSupportedError):
                await device.decommission()


@pytest.mark.asyncio
async def test_gen4_reboot_disconnects_then_resumes():
    """reboot() against a mock Gen4 fan times out (swallowed), then resumes."""
    app = create_gen4_app(lights=0, resume_delay_secs=0.05)
    async with TestClient(TestServer(app)) as client:
        async with aiomodernforms.ModernFormsDevice(
            client.host,
            port=client.port,
            session=client.session,
            request_timeout=0.2,
        ) as device:
            await device.update()
            await device.reboot()  # must not raise; timeout is swallowed

            await asyncio.sleep(0.1)
            await device.update()  # must succeed again after resume delay
            assert device.status.fan_on is False


@pytest.mark.asyncio
async def test_gen4_factory_reset_resets_state():
    """factory_reset() resets the mock Gen4 fan's fixtures to startup defaults."""
    app = create_gen4_app(lights=0, resume_delay_secs=0.05)
    async with TestClient(TestServer(app)) as client:
        async with aiomodernforms.ModernFormsDevice(
            client.host,
            port=client.port,
            session=client.session,
            request_timeout=0.2,
        ) as device:
            await device.update()
            await device.fan(on=True, speed=6)
            assert device.status.fan_on is True

            await device.factory_reset()  # must not raise

            await asyncio.sleep(0.1)
            await device.update()
            assert device.status.fan_on is False
            assert device.status.fan_speed == 3
