"""Modern Forms Constants."""

DEFAULT_TIMEOUT_SECS = 5
DEFAULT_PORT = 80
DEFAULT_API_ENDPOINT = "mf"

COMMAND_QUERY_STATUS = "queryDynamicShadowData"
COMMAND_QUERY_STATIC_DATA = "queryStaticShadowData"
COMMAND_FAN_POWER = "fanOn"
COMMAND_LIGHT_POWER = "lightOn"
COMMAND_LIGHT_BRIGHTNESS = "lightBrightness"
COMMAND_FAN_SPEED = "fanSpeed"
COMMAND_FAN_DIRECTION = "fanDirection"
COMMAND_AWAY_MODE = "awayModeEnabled"
COMMAND_FAN_SLEEP_TIMER = "fanSleepTimer"
COMMAND_LIGHT_SLEEP_TIMER = "lightSleepTimer"
COMMAND_ADAPTIVE_LEARNING = "adaptiveLearning"
COMMAND_REBOOT = "reboot"
COMMAND_WIND = "wind"
COMMAND_WIND_SPEED = "windSpeed"

AWAY_MODE_OFF = False
AWAY_MODE_ON = True

ADAPTIVE_LEARNING_OFF = False
ADAPTIVE_LEARNING_ON = True

FAN_DIRECTION_FORWARD = "forward"
FAN_DIRECTION_REVERSE = "reverse"

FAN_POWER_OFF = False
FAN_POWER_ON = True

LIGHT_POWER_OFF = False
LIGHT_POWER_ON = True

LIGHT_BRIGHTNESS_LOW_VALUE = 1
LIGHT_BRIGHTNESS_HIGH_VALUE = 100

FAN_SPEED_LOW_VALUE = 1
FAN_SPEED_HIGH_VALUE = 6

WIND_SPEED_LOW_VALUE = 1
WIND_SPEED_HIGH_VALUE = 3

DEFAULT_WIND_SPEED = 2

WIND_OFF = False
WIND_ON = True

STATE_FAN_POWER = "fanOn"
STATE_LIGHT_POWER = "lightOn"
STATE_LIGHT_BRIGHTNESS = "lightBrightness"
STATE_FAN_SPEED = "fanSpeed"
STATE_FAN_DIRECTION = "fanDirection"
STATE_AWAY_MODE = "awayModeEnabled"
STATE_FAN_SLEEP_TIMER = "fanSleepTimer"
STATE_LIGHT_SLEEP_TIMER = "lightSleepTimer"
STATE_ADAPTIVE_LEARNING = "adaptiveLearning"
STATE_WIND_POWER = "wind"
STATE_WIND_SPEED = "windSpeed"


INFO_CLIENT_ID = "clientId"
INFO_MAC = "mac"
INFO_LIGHT_TYPE = "lightType"
INFO_FAN_TYPE = "fanType"
INFO_FAN_MOTOR_TYPE = "fanMotorType"
INFO_PRODUCTION_LOT_NUMBER = "productionLotNumber"
INFO_PRODUCT_SKU = "productSku"
INFO_OWNER = "owner"
INFO_FEDERATED_IDENTITY = "federatedIdentity"
INFO_DEVICE_NAME = "deviceName"
INFO_FIRMWARE_VERSION = "firmwareVersion"
INFO_MAIN_MCU_FIRMWARE_VERSION = "mainMcuFirmwareVersion"
INFO_FIRMWARE_URL = "firmwareUrl"

SLEEP_TIMER_CANCEL = 0

STATE_RF_PAIR_MODE_ACTIVE = "rfPairModeActive"
STATE_RESET_RF_PAIR_LIST = "resetRfPairList"
STATE_FACTORY_RESET = "factoryReset"
STATE_DECOMMISSION = "decommission"
STATE_SCHEDULE = "schedule"
STATE_USER_DATA = "userData"

INFO_BRAND = "brand"
INFO_DATE_CODE = "dateCode"

STATE_FAN_TIMER = "fanTimer"
STATE_LIGHT_TIMER = "lightTimer"
STATE_LIGHT_COLOR_TEMP = "lightColorTemp"

COMMAND_FAN_TIMER = "fanTimer"
COMMAND_LIGHT_TIMER = "lightTimer"
COMMAND_LIGHT_COLOR_TEMP = "lightColorTemp"

# Internal-only canonical key: never a real wire field on any generation.
# Gen4's translation layer sets this to a pre-built list[Light]; absent for
# gen1_2/gen3, where State.from_dict synthesizes a single-entry list itself.
STATE_LIGHT_FIXTURES = "__lightFixtures__"

COMMAND_IDENTIFY = "identify"

COMMAND_RF_PAIR_MODE = "rfPairModeActive"
COMMAND_RESET_RF_PAIR_LIST = "resetRfPairList"
COMMAND_FACTORY_RESET = "factoryReset"
COMMAND_DECOMMISSION = "decommission"
COMMAND_SCHEDULE = "schedule"

CONFIG_READ_API_ENDPOINT = "config-read"

CONFIG_NAME_LEGACY = "N"
CONFIG_NAME = "Name"
CONFIG_PROTOCOL_LEGACY = "PO"
CONFIG_PROTOCOL = "Protocol"
CONFIG_HARDWARE_REVISION = "HD"
CONFIG_FIRMWARE_VERSION_LEGACY = "FW"
CONFIG_FIRMWARE_VERSION = "Firmware Rev"
CONFIG_RF_VERSION_LEGACY = "RF"
CONFIG_RF_VERSION = "RF Rev"
CONFIG_CERTIFICATE_ID = "certificateId"
CONFIG_WIFI_STRENGTH = "Wi-Fi strength"
CONFIG_WIFI_STRENGTH_ALT = "WiFi"
CONFIG_WIFI_STRENGTH_ALT2 = "wifiSignal"

# --- Gen4 (WAC IoT /device + /fixture) ---

GEN4_DEVICE_API_ENDPOINT = "device"
GEN4_FIXTURE_API_ENDPOINT = "fixture"

# Matched as a case-insensitive substring of a /device response's
# "systemType" value.
GEN4_SYSTEM_TYPE_MARKERS = ("fan_g4",)

GEN4_FIXTURE_ACTION_READ = 3
GEN4_FIXTURE_ACTION_CONTROL = 4

GEN4_FIXTURE_TYPE_FAN = 13
GEN4_LIGHT_FIXTURE_TYPES = frozenset({0, 1, 2, 14, 15})

# Gen4 reports light brightness as 1-10000; this library's public API uses
# 1-100 everywhere (matching gen1_2/gen3) — multiply/divide by this scale.
GEN4_BRIGHTNESS_SCALE = 100

GEN4_FIELD_ACTION = "action"
GEN4_FIELD_ADDR = "addr"
GEN4_FIELD_TYPE = "type"
GEN4_FIELD_NAME = "name"
GEN4_FIELD_STATE = "state"
GEN4_FIELD_DETAIL = "detail"
GEN4_FIELD_FIXTURE_LIST = "fixture"
GEN4_FIELD_STATUS = "status"
GEN4_FIELD_LEVEL = "level"
GEN4_FIELD_MIX_COLOR_TEMP = "mixColorTemp"
GEN4_FIELD_MIN_COLOR_TEMP = "minColorTemp"
GEN4_FIELD_MAX_COLOR_TEMP = "maxColorTemp"
GEN4_FIELD_FINDME = "findme"

GEN4_DEVICE_QUERY = "query"
GEN4_DEVICE_SYSTEM_TYPE = "systemType"
GEN4_DEVICE_NAME = "deviceName"
GEN4_DEVICE_IOTM_VER = "iotmVer"
GEN4_DEVICE_SCM_VER = "scmVer"
GEN4_DEVICE_OWNER = "owner"
GEN4_DEVICE_NWK_STATE = "nwkState"
GEN4_DEVICE_HARD_FACTORY_RESET = "hardFactoryReset"

GEN4_NWK_CERTIFICATE_ID = "certificateID"
GEN4_NWK_RSSI = "rssi"
