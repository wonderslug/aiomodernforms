"""Unit tests for mock_fan.generations profile data."""

from aiomodernforms.const import CONFIG_HARDWARE_REVISION, CONFIG_WIFI_STRENGTH
from mock_fan.generations import GEN1_2, GEN3, PROFILES


def test_gen1_2_uses_epoch_timers():
    """Gen 1/2 profile is marked as using epoch (not relative) timers."""
    assert GEN1_2.uses_relative_timers is False


def test_gen3_uses_relative_timers():
    """Gen 3 profile is marked as using relative timers."""
    assert GEN3.uses_relative_timers is True


def test_gen1_2_has_no_brand_or_date_code():
    """Gen 1/2 profile has no brand/dateCode (Gen 3-only static fields)."""
    assert GEN1_2.brand is None
    assert GEN1_2.date_code == ""


def test_gen3_has_brand_and_date_code():
    """Gen 3 profile includes brand/dateCode."""
    assert GEN3.brand == 1
    assert GEN3.date_code == "2022-11-17"


def test_gen3_matches_real_diagnostic_static_fields():
    """Gen 3 static fields match a real fan's diagnose.py report.

    See https://github.com/wonderslug/aiomodernforms/issues/272 — a Gen 3
    fan with a light kit reports a nonempty lightType, unlike the earlier
    placeholder value which came from a fan-only unit and was easy to
    mistake for "Gen 3 fans have no light" instead of "this fixture fan
    had none."
    """
    assert GEN3.fan_type == "2006-52"
    assert GEN3.light_type == "F4IN-120V-R1-30"
    assert GEN3.fan_motor_type == "DC156X08"
    assert GEN3.firmware_version == "02.00.0043"
    assert GEN3.main_mcu_firmware_version == "03.00.0000"


def test_gen1_2_config_read_has_hardware_revision():
    """Gen 1/2 config-read data includes a hardware revision."""
    assert (
        GEN1_2.config_read_response[CONFIG_HARDWARE_REVISION] == "WAC_WINDERMIER_REV_5"
    )


def test_gen3_config_read_has_no_hardware_revision_key():
    """Gen 3 config-read data has no hardware revision key at all."""
    assert CONFIG_HARDWARE_REVISION not in GEN3.config_read_response


def test_gen1_2_wifi_strength_is_percentage_int():
    """Gen 1/2 Wi-Fi strength is reported as a percentage integer."""
    assert GEN1_2.config_read_response[CONFIG_WIFI_STRENGTH] == 100


def test_gen3_wifi_strength_is_dbm_string():
    """Gen 3 Wi-Fi strength is reported as a dBm string."""
    assert GEN3.config_read_response[CONFIG_WIFI_STRENGTH] == "-48"


def test_profiles_registry_maps_cli_names():
    """PROFILES exposes both generations under their CLI --generation names."""
    assert PROFILES["gen1_2"] is GEN1_2
    assert PROFILES["gen3"] is GEN3
