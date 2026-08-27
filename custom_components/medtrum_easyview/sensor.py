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
from homeassistant.const import (
    CONF_UNIT_OF_MEASUREMENT,
    PERCENTAGE,
    EntityCategory,
)

from .const import (
    BASAL_ICON,
    BATTERY_ICON,
    BOLUS_ICON,
    CLOCK_ICON,
    DOMAIN,
    GLUCOSE_CONVERSION_FACTOR,
    GLUCOSE_MMOL_MAX,
    GLUCOSE_TREND_ICONS,
    GLUCOSE_TREND_UNKNOWN,
    GLUCOSE_TRENDS,
    GLUCOSE_VALUE_ICON,
    MG_DL,
    MMOL_L,
    PUMP_ICON,
    REMAINING_TIME_ICON,
    SENSOR_ICON,
    SENSOR_STATE_NEEDS_CALIBRATION,
    SENSOR_STATE_NO_VALID_VALUE,
    SENSOR_STATE_WARMUP,
    SENSOR_WARMUP_MAX_SEQUENCE,
    TIMELINE_ICON,
    TREND_UNKNOWN_ICON,
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
    # Glucose concentration: infer the payload's unit and convert to the unit
    # chosen in the config entry.
    glucose_unit: bool = False
    # Multiply the raw value (batteryPercent arrives as a 0..1 fraction).
    scale: float | None = None
    # Map a glucoseRate code onto a human readable trend.
    trend: bool = False
    # A raw 0 means "no reading", not zero.
    zero_is_missing: bool = False
    entity_category: EntityCategory | None = None


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
        glucose_unit=True,
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
    # --- CGM transmitter ------------------------------------------------
    MedtrumSensorSpec(
        key="glucose",
        name="Glucose Value",
        device_type=DeviceType.SENSOR,
        device_class=SensorDeviceClass.BLOOD_GLUCOSE_CONCENTRATION,
        state_class=SensorStateClass.MEASUREMENT,
        icon=GLUCOSE_VALUE_ICON,
        glucose_unit=True,
        zero_is_missing=True,
    ),
    MedtrumSensorSpec(
        key="glucoseRate",
        name="Glucose Trend",
        device_type=DeviceType.SENSOR,
        device_class=SensorDeviceClass.ENUM,
        trend=True,
    ),
    MedtrumSensorSpec(
        key="updateTime",
        name="Sensor Last update",
        device_type=DeviceType.SENSOR,
        device_class=SensorDeviceClass.TIMESTAMP,
        icon=CLOCK_ICON,
    ),
    MedtrumSensorSpec(
        key="batteryPercent",
        name="Sensor Battery",
        device_type=DeviceType.SENSOR,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        icon=BATTERY_ICON,
        unit=PERCENTAGE,
        scale=100,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


def to_display_glucose(value: float, unit: str) -> float:
    """
    Convert a glucose concentration into the unit configured for the entry.

    The payload does not state its unit, so it is inferred from the value: the
    valid mg/dL and mmol/L ranges do not overlap.
    """
    source_is_mmol = abs(value) <= GLUCOSE_MMOL_MAX
    if unit == MMOL_L:
        result = value if source_is_mmol else value / GLUCOSE_CONVERSION_FACTOR
        return round(result, 1)
    result = value * GLUCOSE_CONVERSION_FACTOR if source_is_mmol else value
    return round(result)


def _trend_name(value: Any) -> str:
    """Map a glucoseRate code onto its human readable trend."""
    try:
        return GLUCOSE_TRENDS.get(int(value), GLUCOSE_TREND_UNKNOWN)
    except (TypeError, ValueError):
        return GLUCOSE_TREND_UNKNOWN


def _glucose_or_none(value: Any, unit: str, key: str) -> float | None:
    """Convert a glucose concentration, or None when it is unusable."""
    try:
        return to_display_glucose(float(value), unit)
    except (TypeError, ValueError):
        _LOGGER.debug("Unusable glucose value for %s: %r", key, value)
        return None


def _scaled(value: Any, scale: float) -> float | None:
    """Apply a fixed multiplier, or None when the value is unusable."""
    try:
        # Rounded: batteryPercent arrives as 0.8399999737739563.
        return round(float(value) * scale, 2)
    except (TypeError, ValueError):
        return None


def sensor_state_reason(status: dict[str, Any]) -> str:
    """Explain why a CGM is reporting no glucose value."""
    sequence = status.get("sequence")
    if isinstance(sequence, (int, float)):
        if sequence <= SENSOR_WARMUP_MAX_SEQUENCE:
            return SENSOR_STATE_WARMUP
        next_calibration = status.get("nextSequenceNeedCalibrate")
        if isinstance(next_calibration, (int, float)) and sequence >= next_calibration:
            return SENSOR_STATE_NEEDS_CALIBRATION
    return SENSOR_STATE_NO_VALID_VALUE


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
        self.uom = custom_unit if spec.glucose_unit else spec.unit

        self._attr_unique_id = f"{patient_uid}_{spec.device_type.value}_{spec.key}"
        self._attr_name = spec.name

        # set parent class attributes
        self._attr_device_class = spec.device_class
        self._attr_state_class = spec.state_class
        self._attr_suggested_unit_of_measurement = spec.suggested_unit
        self._attr_entity_category = spec.entity_category

        if spec.trend:
            # A closed set, so the ENUM device class can declare its options.
            self._attr_options = sorted(set(GLUCOSE_TRENDS.values()))
            self._attr_suggested_display_precision = None
        elif spec.glucose_unit:
            # mg/dL is reported whole, mmol/L to one decimal.
            self._attr_suggested_display_precision = 0 if self.uom == MG_DL else 1
        elif spec.device_class == SensorDeviceClass.BATTERY:
            self._attr_suggested_display_precision = 0
        else:
            self._attr_suggested_display_precision = 2

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        status = self.status
        value = status.get(self.key)

        # AutoMode patches publish only `state`, classic ones both and equal.
        if value is None and self.key == "status":
            value = status.get(STATUS_FALLBACK_KEY)

        # A CGM reporting 0 has no reading; see `sensor_state_reason`.
        if value is None or (self.spec.zero_is_missing and value == 0):
            return None

        return self._transform(value)

    def _transform(self, value: Any) -> Any:
        """Turn a raw payload value into the value this entity reports."""
        if self.spec.trend:
            return _trend_name(value)
        if self.spec.glucose_unit:
            return _glucose_or_none(value, self.uom or MG_DL, self.key)
        if self.spec.scale is not None:
            return _scaled(value, self.spec.scale)
        if self._attr_device_class == SensorDeviceClass.TIMESTAMP:
            return _as_datetime(value, self.key)
        if self._attr_device_class == SensorDeviceClass.ENUM:
            return _pump_status_name(value)
        return value

    @property
    def icon(self) -> str | None:
        """Return the icon for the frontend."""
        if self.spec.trend:
            code = self.status.get(self.key)
            try:
                return GLUCOSE_TREND_ICONS.get(int(code), TREND_UNKNOWN_ICON)
            except (TypeError, ValueError):
                return TREND_UNKNOWN_ICON
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
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Explain a missing glucose reading, and expose sensor wear."""
        if not self.spec.zero_is_missing:
            return None

        status = self.status
        attributes: dict[str, Any] = {}

        if status.get(self.key) == 0:
            attributes["Sensor state"] = sensor_state_reason(status)

        # sequence counts 2-minute samples since the sensor was started.
        sequence = status.get("sequence")
        total = status.get("sensorLifetimeTotalCount")
        if isinstance(sequence, (int, float)):
            attributes["Sensor age (hours)"] = round(sequence * 2 / 60, 1)
            if isinstance(total, (int, float)) and total > 0:
                attributes["Sensor remaining (hours)"] = round(
                    max(total - sequence, 0) * 2 / 60, 1
                )
        return attributes or None

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the native unit of measurement."""
        return self.uom
