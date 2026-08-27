"""Adds config flow for Medtrum EasyView."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_UNIT_OF_MEASUREMENT, CONF_USERNAME
from homeassistant.helpers import selector

from .api import (
    MedtrumEasyViewApiAuthenticationError,
    MedtrumEasyViewApiError,
    MedtrumEasyViewCommunicationError,
    async_create_api_client,
)
from .const import (
    ACCOUNT_TYPE,
    ACCOUNT_TYPE_LIST,
    ACCOUNT_TYPE_PATIENT,
    BASE_URL_LIST,
    COUNTRY,
    COUNTRY_LIST,
    DOMAIN,
    LOGGER,
    MG_DL,
    MMOL_L,
)


class MedtrumEasyViewFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Medtrum EasyView."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle a flow initialized by the user."""
        _errors = {}
        if user_input is not None:
            try:
                uid, patients = await self._test_credentials(
                    account_type=user_input[ACCOUNT_TYPE],
                    username=user_input[CONF_USERNAME],
                    password=user_input[CONF_PASSWORD],
                    base_url=BASE_URL_LIST.get(user_input[COUNTRY])
                    or BASE_URL_LIST["Global"],
                )
            except MedtrumEasyViewApiAuthenticationError as exception:
                LOGGER.warning(exception)
                _errors["base"] = "auth"
            except MedtrumEasyViewCommunicationError as exception:
                LOGGER.error(exception)
                _errors["base"] = "connection"
            except MedtrumEasyViewApiError as exception:
                LOGGER.exception(exception)
                _errors["base"] = "unknown"
            else:
                if not patients:
                    # A follower account linked to nobody has nothing to
                    # create entities from.
                    _errors["base"] = "no_patient"
                else:
                    if uid is not None:
                        await self.async_set_unique_id(uid)
                        self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=user_input[CONF_USERNAME],
                        data=user_input,
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USERNAME,
                        default=(user_input or {}).get(CONF_USERNAME),
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.TEXT
                        ),
                    ),
                    vol.Required(CONF_PASSWORD): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        ),
                    ),
                    vol.Required(
                        ACCOUNT_TYPE,
                        default=ACCOUNT_TYPE_PATIENT,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=ACCOUNT_TYPE_LIST,
                            translation_key=ACCOUNT_TYPE,
                        ),
                    ),
                    vol.Required(
                        COUNTRY,
                        description="Country",
                        default=(COUNTRY_LIST[0]),
                    ): vol.In(COUNTRY_LIST),
                    vol.Required(
                        CONF_UNIT_OF_MEASUREMENT,
                        default=(MG_DL),
                    ): vol.In({MG_DL, MMOL_L}),
                }
            ),
            errors=_errors,
        )

    async def _test_credentials(
        self,
        account_type: str,
        username: str,
        password: str,
        base_url: str,
    ) -> tuple[str | None, dict[str, str]]:
        """
        Validate credentials and report what the account can see.

        A follower account that is not linked to any patient authenticates
        successfully but would produce no entities, so the patients are
        enumerated here rather than at the first poll.
        """
        client = async_create_api_client(
            self.hass,
            account_type,
            username=username,
            password=password,
            base_url=base_url,
        )

        uid = await client.async_login()
        return uid, await client.async_get_patients()
