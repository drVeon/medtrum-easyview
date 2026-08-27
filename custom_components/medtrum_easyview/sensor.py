"""Sensor platform for Medtrum EasyView."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import CONF_UNIT_OF_MEASUREMENT

from .const import (
    BASAL_ICON,
    BOLUS_ICON,
    CLOCK_ICON,
    DOMAIN,
    GLUCOSE_VALUE_ICON,
    MG_DL,
    PUMP_ICON,
    REMAINING_TIME_ICON,
    SENSOR_ICON,
    TIMELINE_ICON,
    VOLUME_ICON,
    DeviceType,
    PumpStatus,
)
from .device import MedtrumEasyViewDevice

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import MedtrumEasyViewDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# The API serves more than one pump schema. A "classic" patch reports `status`,
# `basalRate`, `basalSum` and `bolusSum`; an AutoMode patch reports neither the
# totals nor `basalRate`, and only `state` instead of `status`. Entities are
# therefore created per patient, and only for the keys that patient publishes.
STATUS_FALLBACK_KEY = "state"


@dataclass(frozen=True, kw_only=True)
class MedtrumSensorSpec:
    """Description of one sensor entity."""

    key: str
    name: str
    device_type: DeviceType = DeviceType.PUMP
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = None
    icon: str | None = None
    unit: str | None = None
    suggested_unit: str | None = None
    # Report in the unit chosen in the config entry rather than a fixed one.
    configured_unit: bool = False


SENSOR_SPECS: tuple[MedtrumSensorSpec, ...] = (
    MedtrumSensorSpec(
        key="status",
        name="Pump Status",
        device_class=SensorDeviceClass.ENUM,
        icon=PUMP_ICON,
    ),
    MedtrumSensorSpec(
        key="remainingTime",
        name="Pump Remaining time",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        icon=REMAINING_TIME_ICON,
        unit="min",
        suggested_unit="d",
    ),
    MedtrumSensorSpec(
        key="remainingDose",
        name="Pump Remaining dose",
        state_class=SensorStateClass.MEASUREMENT,
        icon=VOLUME_ICON,
        unit="U",
    ),
    MedtrumSensorSpec(
        key="updateTime",
        name="Pump Last update",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon=CLOCK_ICON,
    ),
    MedtrumSensorSpec(
        key="bGTarget",
        name="Blood Glucose Target",
        device_class=SensorDeviceClass.BLOOD_GLUCOSE_CONCENTRATION,
        icon=GLUCOSE_VALUE_ICON,
        configured_unit=True,
    ),
    MedtrumSensorSpec(
        key="basalSum",
        name="Basal Daily Volume",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon=BASAL_ICON,
        unit="U",
    ),
    MedtrumSensorSpec(
        key="bolusSum",
        name="Bolus Daily Volume",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon=BOLUS_ICON,
        unit="U",
    ),
    MedtrumSensorSpec(
        key="basalRate",
        name="Basal Rate",
        state_class=SensorStateClass.MEASUREMENT,
        icon=BASAL_ICON,
        unit="U/h",
    ),
    MedtrumSensorSpec(
        key="bolusDeliveriedTime",
        name="Last Bolus Delivered Time",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon=TIMELINE_ICON,
    ),
    MedtrumSensorSpec(
        key="bolusDeliveried",
        name="Last Bolus Delivered Volume",
        state_class=SensorStateClass.MEASUREMENT,
        icon=BOLUS_ICON,
        unit="U",
    ),
    MedtrumSensorSpec(
        key="iob",
        name="Active Insulin",
        state_class=SensorStateClass.MEASUREMENT,
        icon=VOLUME_ICON,
        unit="U",
    ),
)


def _as_datetime(value: Any, key: str) -> datetime | None:
    """Turn an epoch value into an aware datetime, or None."""
    try:
        return datetime.fromtimestamp(float(value), tz=UTC)
    except (OSError, OverflowError, TypeError, ValueError):
        _LOGGER.debug("Unusable timestamp for %s: %r", key, value)
        return None


def _pump_status_name(value: Any) -> str:
    """Render a pump status code as text."""
    try:
        return PumpStatus(int(value)).name.replace("_", " ").title()
    except (TypeError, ValueError):
        return f"Unknown Status ({value})"


def _supported(status: dict[str, Any], spec: MedtrumSensorSpec) -> bool:
    """Return True when this patient publishes the key the spec needs."""
    if spec.key in status:
        return True
    return spec.key == "status" and STATUS_FALLBACK_KEY in status


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform for every patient."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    # If custom unit of measurement is selected, otherwise MG/DL is used
    custom_unit = config_entry.data.get(CONF_UNIT_OF_MEASUREMENT, MG_DL)

    sensors: list[MedtrumEasyViewSensor] = []
    for patient_uid, patient in (coordinator.data or {}).items():
        for spec in SENSOR_SPECS:
            status = patient.get(f"{spec.device_type.value}_status") or {}
            if not _supported(status, spec):
                _LOGGER.debug(
                    "Patient %s does not publish %r; skipping %s",
                    patient_uid,
                    spec.key,
                    spec.name,
                )
                continue
            sensors.append(
                MedtrumEasyViewSensor(coordinator, patient_uid, spec, custom_unit)
            )

    _LOGGER.debug(
        "Adding %d sensor(s) for %d patient(s)",
        len(sensors),
        len(coordinator.data or {}),
    )
    async_add_entities(sensors)


class MedtrumEasyViewSensor(MedtrumEasyViewDevice, SensorEntity):
    """MedtrumEasyView Sensor class."""

    def __init__(
        self,
        coordinator: MedtrumEasyViewDataUpdateCoordinator,
        patient_uid: str,
        spec: MedtrumSensorSpec,
        custom_unit: str,
    ) -> None:
        """Initialize the device class."""
        super().__init__(coordinator, patient_uid, spec.device_type)

        self.spec = spec
        self.key = spec.key
        self._icon = spec.icon
        self.uom = custom_unit if spec.configured_unit else spec.unit

        self._attr_unique_id = f"{patient_uid}_{spec.device_type.value}_{spec.key}"
        self._attr_name = spec.name

        # set parent class attributes
        self._attr_device_class = spec.device_class
        self._attr_state_class = spec.state_class
        self._attr_suggested_unit_of_measurement = spec.suggested_unit
        self._attr_suggested_display_precision = 2

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        status = self.status
        value = status.get(self.key)

        # AutoMode patches publish only `state`, classic ones both and equal.
        if value is None and self.key == "status":
            value = status.get(STATUS_FALLBACK_KEY)

        if value is None:
            return None

        return self._transform(value)

    def _transform(self, value: Any) -> Any:
        """Turn a raw payload value into the value this entity reports."""
        if self._attr_device_class == SensorDeviceClass.TIMESTAMP:
            return _as_datetime(value, self.key)
        if self._attr_device_class == SensorDeviceClass.ENUM:
            return _pump_status_name(value)
        return value

    @property
    def icon(self) -> str | None:
        """Return the icon for the frontend."""
        if self._icon:
            return self._icon

        # Pump sensors
        if self.device_type == DeviceType.PUMP:
            return PUMP_ICON

        # Sensor sensors
        if self.device_type == DeviceType.SENSOR:
            return SENSOR_ICON

        return None

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the native unit of measurement."""
        return self.uom
