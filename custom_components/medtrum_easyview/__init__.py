"""Custom integration to integrate Medtrum EasyView with Home Assistant."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

from .api import async_create_api_client
from .const import (
    ACCOUNT_TYPE,
    ACCOUNT_TYPE_PATIENT,
    BASE_URL_LIST,
    COUNTRY,
    DOMAIN,
)
from .coordinator import MedtrumEasyViewDataUpdateCoordinator

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
]


_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up this integration using UI."""
    # Entries created before follower support existed carry no account type.
    account_type = entry.data.get(ACCOUNT_TYPE, ACCOUNT_TYPE_PATIENT)

    _LOGGER.debug(
        "async_setup_entry entry: entry_id= %s, user= %s BaseUrl= %s account= %s",
        entry.entry_id,
        entry.data[CONF_USERNAME],
        BASE_URL_LIST.get(entry.data[COUNTRY]),
        account_type,
    )
    hass.data.setdefault(DOMAIN, {})

    my_medtrum_easyview = async_create_api_client(
        hass,
        account_type,
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        base_url=BASE_URL_LIST.get(entry.data[COUNTRY]) or BASE_URL_LIST["Global"],
    )

    # Validate credentials
    await my_medtrum_easyview.async_login()

    hass.data[DOMAIN][entry.entry_id] = coordinator = (
        MedtrumEasyViewDataUpdateCoordinator(
            hass=hass,
            client=my_medtrum_easyview,
        )
    )

    # First poll of the data to be ready for entities initialization
    await coordinator.async_config_entry_first_refresh()

    # Then launch async_setup_entry for our entities in sensor.py and binary_sensor.py
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Reload entry when its updated.
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle removal of an entry."""
    if unloaded := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry  when it changed."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
