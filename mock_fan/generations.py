"""Static per-generation profile data for the mock fan."""

from __future__ import annotations

from dataclasses import dataclass

from aiomodernforms.const import (
    CONFIG_CERTIFICATE_ID,
    CONFIG_FIRMWARE_VERSION,
    CONFIG_FIRMWARE_VERSION_LEGACY,
    CONFIG_HARDWARE_REVISION,
    CONFIG_NAME,
    CONFIG_NAME_LEGACY,
    CONFIG_PROTOCOL,
    CONFIG_PROTOCOL_LEGACY,
    CONFIG_RF_VERSION,
    CONFIG_RF_VERSION_LEGACY,
    CONFIG_WIFI_STRENGTH,
)

# Shared placeholder certificate ID served by both generation profiles.
_MOCK_CERTIFICATE_ID = "mockcertificateid0000000000000000000000000000000000000000"


@dataclass(frozen=True)
class GenerationProfile:
    """Static, generation-specific data the mock fan serves."""

    name: str
    client_id: str
    mac: str
    fan_type: str
    light_type: str
    fan_motor_type: str
    firmware_version: str
    main_mcu_firmware_version: str
    brand: int | None
    date_code: str
    uses_relative_timers: bool
    config_read_response: dict[str, str | int]


GEN1_2 = GenerationProfile(
    name="gen1_2",
    client_id="MF_000000000000",
    mac="CC:CC:CC:CC:CC:CC",
    fan_type="1818-56",
    light_type="F6IN-120V-R1-30",
    fan_motor_type="DC125X25",
    firmware_version="01.03.0025",
    main_mcu_firmware_version="01.03.3008",
    brand=None,
    date_code="",
    uses_relative_timers=False,
    config_read_response={
        CONFIG_NAME_LEGACY: "Mock Fan",
        CONFIG_PROTOCOL_LEGACY: "com.modernforms.fan",
        CONFIG_HARDWARE_REVISION: "WAC_WINDERMIER_REV_5",
        CONFIG_FIRMWARE_VERSION_LEGACY: "01.03.0025",
        CONFIG_RF_VERSION_LEGACY: "wl0: Oct  6 2016 01:32:44 version 5.90.230.15 ",
        CONFIG_CERTIFICATE_ID: _MOCK_CERTIFICATE_ID,
        CONFIG_WIFI_STRENGTH: 100,
    },
)

# Field values below (fan_type, light_type, fan_motor_type, firmware_version,
# main_mcu_firmware_version, brand, date_code) are taken from a real Gen 3
# fan's diagnose.py report: https://github.com/wonderslug/aiomodernforms/issues/272
GEN3 = GenerationProfile(
    name="gen3",
    client_id="MF_C82B9698E5AC",
    mac="C8:2B:96:98:E5:AC",
    fan_type="2006-52",
    light_type="F4IN-120V-R1-30",
    fan_motor_type="DC156X08",
    firmware_version="02.00.0043",
    main_mcu_firmware_version="03.00.0000",
    brand=1,
    date_code="2022-11-17",
    uses_relative_timers=True,
    config_read_response={
        CONFIG_NAME: "Mock Fan",
        CONFIG_PROTOCOL: "com.modernforms.fan",
        CONFIG_FIRMWARE_VERSION: "02.00.0043",
        CONFIG_RF_VERSION: "v3.2.2",
        CONFIG_CERTIFICATE_ID: _MOCK_CERTIFICATE_ID,
        CONFIG_WIFI_STRENGTH: "-48",
    },
)

PROFILES: dict[str, GenerationProfile] = {"gen1_2": GEN1_2, "gen3": GEN3}
