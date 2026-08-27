"""Constants for Medtrum EasyView."""

from enum import IntEnum, StrEnum
from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

NAME = "Medtrum EasyView"
DOMAIN = "medtrum_easyview"
VERSION = "1.0.2"
ATTRIBUTION = "Data provided by https://easyview.medtrum.eu"
# Patient ("EasyView") endpoints. JSON bodies, authenticated by the cookie the
# login response sets, and answering with error=0 on success.
PATIENT_LOGIN_URL = "/v3/api/v2.0/login"
PATIENT_STATUS_URL = "/api/v2.1/monitor/$userid/status"
PATIENT_APP_TAG = "v=3.0.2(15);n=eyvw"
USER_TYPE_PATIENT = "P"

# Follower ("EasyFollow") endpoints. Form-encoded bodies, authenticated by the
# session cookie replayed verbatim, and answering with res="OK" on success. One
# call returns the state of every patient the account is allowed to see.
FOLLOWER_LOGIN_URL = "/mobile/ajax/login"
FOLLOWER_LOGINDATA_URL = "/mobile/ajax/logindata"
FOLLOWER_MONITOR_URL = "/mobile/ajax/monitor?flag=monitor_list"
FOLLOWER_APP_TAG = "v=1.2.70(112);n=eyfo;p=android"
FOLLOWER_DEV_INFO = "Android 11;Google generic_x86_arm;Android 11"
FOLLOWER_USER_AGENT = "okhttp/3.5.0"
# "M" = monitor/follower: a patient account cannot read the monitor list.
USER_TYPE_FOLLOWER = "M"
APP_TYPE_FOLLOW = "Follow"
LOGIN_PLATFORM = "google"

# Which of the two APIs a config entry talks to. Entries written before
# follower support existed have no such key, so patient is the default.
ACCOUNT_TYPE = "account_type"
ACCOUNT_TYPE_PATIENT = "patient"
ACCOUNT_TYPE_FOLLOWER = "follower"
ACCOUNT_TYPE_LIST = [ACCOUNT_TYPE_PATIENT, ACCOUNT_TYPE_FOLLOWER]

COUNTRY = "Country"
BASE_URL_LIST = {
    "Global": "https://easyview.medtrum.eu",
    "Europe": "https://easyview.medtrum.eu",
    "France": "https://easyview.medtrum.fr",
}
# Derived from BASE_URL_LIST so the config flow can only ever offer a country
# that resolves to a base URL.
COUNTRY_LIST = list(BASE_URL_LIST)
CONTENT_TYPE = "application/json"
CONTENT_TYPE_FORM = "application/x-www-form-urlencoded"
MMOL_L = "mmol/L"
MG_DL = "mg/dL"
MMOL_DL_TO_MG_DL = 18
REFRESH_RATE_MIN = 1
API_TIME_OUT_SECONDS = 20

# Icons
GLUCOSE_VALUE_ICON = "mdi:diabetes"
PUMP_ICON = "mdi:needle"
PUMP_ON_ICON = "mdi:water-sync"
PUMP_OFF_ICON = "mdi:water-off"
SENSOR_ICON = "mdi:diabetes"
CLOCK_ICON = "mdi:clock"
TIMELINE_ICON = "mdi:timeline-clock"
BASAL_ICON = "mdi:water-sync"
BOLUS_ICON = "mdi:water-plus"
VOLUME_ICON = "mdi:gauge"
REMAINING_TIME_ICON = "mdi:clock-end"


class DeviceType(StrEnum):
    """Device type enum."""

    PUMP = "pump"
    SENSOR = "sensor"


class PumpStatus(IntEnum):
    """Pump status enum."""

    # From state2 array in the JS code
    DELIVERING_BASAL = 32
    DELIVERING_BASAL_ALT = 33  # Second "Delivering Basal" entry

    # From state3 array (64-79 range)
    LOW_SUSPEND = 64
    PREDICTIVE_LOW_SUSPEND = 65
    AUTO_OFF = 66
    EXCEEDS_MAX_1_HOUR_DELIVERY = 67
    EXCEEDS_MAX_TDD = 68
    SUSPEND = 69

    # From state4 array (96-103 range)
    OCCLUSION_DETECTED = 96
    PATCH_EXPIRED = 97
    EMPTY_RESERVOIR = 98
    PATCH_ERROR_1 = 99
    PATCH_ERROR_2 = 100
    PUMP_BASE_ERROR = 101
    PATCH_BATTERY_DEPLETED = 102
    MAGNETIC_SENSOR_NOT_CALIBRATED = 103

    # From state1 array (0-6 range)
    TO_BE_FILLED = 1
    FILLED_WITH_INSULIN = 2
    PRIMING = 3
    PRIMING_COMPLETED = 4
    INSERTING_NEEDLE = 5
    PATCH_ACTIVATED = 6

    # Special states
    DELIVERY_STOPPED = 128
