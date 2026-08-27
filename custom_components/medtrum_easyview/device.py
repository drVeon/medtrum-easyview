"""Device base class for Medtrum EasyView."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN, NAME, VERSION, DeviceType

if TYPE_CHECKING:
    from .coordinator import MedtrumEasyViewDataUpdateCoordinator

# enable logging
_LOGGER = logging.getLogger(__name__)


def format_serial(value: Any) -> str | None:
    """
    Render a device serial the way the Medtrum apps do: uppercase hex.

    The API is not consistent about the type: a serial arrives as an int for
    some patients and as a numeric string for others, so both are accepted and
    anything else is passed through untouched.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return format(value, "X")
    text = str(value)
    if text.isdigit():
        return format(int(text), "X")
    return text


# A device is created for each patient, to regroup that patient's entities.


class MedtrumEasyViewDevice(CoordinatorEntity):
    """MedtrumEasyViewEntity class, scoped to one patient."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(
        self,
        coordinator: MedtrumEasyViewDataUpdateCoordinator,
        patient_uid: str,
        device_type: DeviceType,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)

        self.patient_uid = patient_uid
        self.device_type = device_type

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, patient_uid)},
            name=self.patient_name,
            model=VERSION,
            manufacturer=NAME,
        )

    @property
    def patient(self) -> dict[str, Any]:
        """Return this patient's entry in the coordinator data."""
        return (self.coordinator.data or {}).get(self.patient_uid) or {}

    @property
    def patient_name(self) -> str:
        """Return the patient's display name."""
        patient = self.patient
        return str(
            patient.get("real_name") or patient.get("username") or self.patient_uid
        )

    @property
    def status(self) -> dict[str, Any]:
        """Return the pump_status or sensor_status block for this entity."""
        return self.patient.get(f"{self.device_type.value}_status") or {}

    @property
    def available(self) -> bool:
        """Return False when this patient is missing from the latest poll."""
        return super().available and self.patient_uid in (self.coordinator.data or {})
