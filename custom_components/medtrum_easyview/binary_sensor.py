"""Binary sensor platform for medtrum easyview."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)

from .const import (
    DOMAIN,
    PUMP_ICON,
    PUMP_OFF_ICON,
    PUMP_ON_ICON,
    SENSOR_ICON,
    DeviceType,
)
from .device import MedtrumEasyViewDevice, format_serial

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import MedtrumEasyViewDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# AutoMode patches publish `state` where classic ones publish `status`.
STATUS_FALLBACK_KEY = "state"


@dataclass(frozen=True, kw_only=True)
class MedtrumBinarySensorSpec:
    """Description of one binary sensor entity."""

    key: str
    name: str
    device_type: DeviceType
    device_class: BinarySensorDeviceClass | None = None


BINARY_SENSOR_SPECS: tuple[MedtrumBinarySensorSpec, ...] = (
    MedtrumBinarySensorSpec(
        key="autobasalstatus",
        name="Basal Active",
        device_type=DeviceType.PUMP,
        device_class=BinarySensorDeviceClass.POWER,
    ),
    MedtrumBinarySensorSpec(
        key="status",
        name="Pump",
        device_type=DeviceType.PUMP,
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
    ),
    MedtrumBinarySensorSpec(
        key="status",
        name="Sensor",
        device_type=DeviceType.SENSOR,
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
    ),
)


def _supported(status: dict[str, Any], spec: MedtrumBinarySensorSpec) -> bool:
    """Return True when this patient publishes the key the spec needs."""
    if spec.key in status:
        return True
    return spec.key == "status" and STATUS_FALLBACK_KEY in status


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary_sensor platform for every patient."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    sensors: list[MedtrumEasyViewBinarySensor] = []
    for patient_uid, patient in (coordinator.data or {}).items():
        for spec in BINARY_SENSOR_SPECS:
            status = patient.get(f"{spec.device_type.value}_status") or {}
            if not _supported(status, spec):
                _LOGGER.debug(
                    "Patient %s does not publish %s.%r; skipping %s",
                    patient_uid,
                    spec.device_type.value,
                    spec.key,
                    spec.name,
                )
                continue
            sensors.append(MedtrumEasyViewBinarySensor(coordinator, patient_uid, spec))

    _LOGGER.debug(
        "Adding %d binary sensor(s) for %d patient(s)",
        len(sensors),
        len(coordinator.data or {}),
    )
    async_add_entities(sensors)


class MedtrumEasyViewBinarySensor(MedtrumEasyViewDevice, BinarySensorEntity):
    """medtrum easyview binary_sensor class."""

    def __init__(
        self,
        coordinator: MedtrumEasyViewDataUpdateCoordinator,
        patient_uid: str,
        spec: MedtrumBinarySensorSpec,
    ) -> None:
        """Initialize the device class."""
        super().__init__(coordinator, patient_uid, spec.device_type)

        self.key = spec.key
        self._attr_name = spec.name
        self._attr_device_class = spec.device_class
        self._attr_unique_id = f"{patient_uid}_{spec.device_type.value}_{spec.key}"

    @property
    def icon(self) -> str | None:
        """Return the icon for the frontend."""
        if self.device_type == DeviceType.PUMP:
            if self.key == "autobasalstatus":
                return PUMP_ON_ICON if self.is_on else PUMP_OFF_ICON
            return PUMP_ICON
        if self.device_type == DeviceType.SENSOR:
            return SENSOR_ICON

        return None

    # define state based on the entity_description key
    @property
    def is_on(self) -> bool:
        """Return true if the binary_sensor is on."""
        status = self.status
        value = status.get(self.key)
        if value is None and self.key == "status":
            value = status.get(STATUS_FALLBACK_KEY)
        try:
            return int(value) > 0
        except (TypeError, ValueError):
            return False

    @property
    def extra_state_attributes(self) -> Any:
        """Return the state attributes of the medtrum easyview sensor."""
        if self.key != "status" or not self.is_on:
            return None

        attributes = {
            "User ID": self.patient_uid,
            "Patient": self.patient_name,
        }
        serial = format_serial(self.status.get("serial"))
        if serial is not None:
            attributes["Serial number"] = serial
        return attributes
