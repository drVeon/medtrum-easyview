"""Provide Medtrum EasyView API clients."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import socket
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import aiohttp
from homeassistant.helpers.aiohttp_client import (
    async_create_clientsession,
    async_get_clientsession,
)

from .const import (
    ACCOUNT_TYPE_FOLLOWER,
    API_TIME_OUT_SECONDS,
    APP_TYPE_FOLLOW,
    CONTENT_TYPE,
    CONTENT_TYPE_FORM,
    FOLLOWER_APP_TAG,
    FOLLOWER_DEV_INFO,
    FOLLOWER_LOGIN_URL,
    FOLLOWER_LOGINDATA_URL,
    FOLLOWER_MONITOR_URL,
    FOLLOWER_USER_AGENT,
    LOGIN_PLATFORM,
    PATIENT_APP_TAG,
    PATIENT_LOGIN_URL,
    PATIENT_STATUS_URL,
    USER_TYPE_FOLLOWER,
    USER_TYPE_PATIENT,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

_UNAUTHORIZED_STATUS = (401, 403)


class MedtrumEasyViewApiError(Exception):
    """Exception to indicate a general API error."""


class MedtrumEasyViewCommunicationError(MedtrumEasyViewApiError):
    """Exception to indicate a communication error."""


class MedtrumEasyViewApiAuthenticationError(MedtrumEasyViewApiError):
    """Exception to indicate an authentication error."""


class _SessionRejectedError(MedtrumEasyViewApiError):
    """Internal: the server refused the session, so it should be renewed."""


class MedtrumEasyViewApiClientBase:
    """
    Shared plumbing for the patient and follower clients.

    Attributes:
        username: of the Medtrum account
        password: of the Medtrum account
        base_url: for API calls depending on your location
        session: aiohttp object for the open session

    """

    def __init__(
        self,
        username: str,
        password: str,
        base_url: str,
        session: aiohttp.ClientSession,
    ) -> None:
        """Initialize the API client."""
        self._username = username
        self._password = password
        self._base_url = base_url
        self._session = session

    async def async_login(self) -> str | None:
        """Authenticate and return the account's uid."""
        raise NotImplementedError

    async def async_get_patients(self) -> dict[str, str]:
        """Return {patient uid: display name} for every visible patient."""
        raise NotImplementedError

    async def async_get_data(self) -> dict[str, dict[str, Any]]:
        """Return {patient uid: status blocks} for every visible patient."""
        raise NotImplementedError

    async def _send(  # noqa: PLR0913
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        json_body: dict[str, Any] | None = None,
        data: dict[str, str] | None = None,
        capture_cookie: bool = False,
    ) -> Any:
        """Issue one request, mapping transport failures onto our exceptions."""
        try:
            _LOGGER.debug("API request - Method: %s, URL: %s", method.upper(), url)

            async with asyncio.timeout(API_TIME_OUT_SECONDS):
                response = await self._session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=json_body,
                    data=data,
                )
                _LOGGER.debug("response.status: %s", response.status)

                if capture_cookie:
                    self._store_cookie(response.headers.get("Set-Cookie"))

                if response.status in _UNAUTHORIZED_STATUS:
                    raise MedtrumEasyViewApiAuthenticationError(  # noqa: TRY003,TRY301
                        "Invalid credentials",  # noqa: EM101
                    )

                response.raise_for_status()
                return await response.json(content_type=None)

        # Our own exceptions are already the right shape; re-raising them here
        # keeps an authentication failure from being re-wrapped as a generic
        # error by the broad handler below, which would stop Home Assistant
        # from asking for new credentials.
        except MedtrumEasyViewApiError:
            raise
        except TimeoutError as exception:
            _LOGGER.debug("Exception: timeout fetching %s", url)
            raise MedtrumEasyViewCommunicationError(  # noqa: TRY003
                "Timeout error fetching information",  # noqa: EM101
            ) from exception
        except (aiohttp.ClientError, socket.gaierror) as exception:
            _LOGGER.debug("Exception: communication error for %s", url)
            raise MedtrumEasyViewCommunicationError(  # noqa: TRY003
                "Error fetching information",  # noqa: EM101
            ) from exception
        except Exception as exception:  # pylint: disable=broad-except
            _LOGGER.debug("Exception: general API error for %s", url)
            raise MedtrumEasyViewApiError(  # noqa: TRY003
                "Something really wrong happened!",  # noqa: EM101
            ) from exception

    def _store_cookie(self, set_cookie: str | None) -> None:
        """Remember a session cookie. Only the follower client needs this."""


class MedtrumEasyViewPatientApiClient(MedtrumEasyViewApiClientBase):
    """
    API class to retrieve medtrum easyview data from a patient account.

    The account sees only itself, so one poll returns one patient. aiohttp's
    cookie jar carries the session from the login call to the status call.
    """

    def __init__(
        self,
        username: str,
        password: str,
        base_url: str,
        session: aiohttp.ClientSession,
    ) -> None:
        """Initialize the API client."""
        super().__init__(username, password, base_url, session)
        self.uid: str | None = None
        self.realname: str | None = None

    @property
    def _headers(self) -> dict[str, str]:
        """Return the headers the EasyView app sends."""
        return {
            "AppTag": PATIENT_APP_TAG,
            "Accept": CONTENT_TYPE,
            "Content-Type": CONTENT_TYPE,
        }

    async def async_login(self) -> str:
        """Get token from the API."""
        response_login = await self._send(
            "post",
            self._base_url + PATIENT_LOGIN_URL,
            headers=self._headers,
            json_body={
                "user_name": self._username,
                "password": self._password,
                "user_type": USER_TYPE_PATIENT,
            },
        )

        if response_login.get("error") != 0:
            raise MedtrumEasyViewApiAuthenticationError(  # noqa: TRY003
                "Invalid credentials",  # noqa: EM101
            )

        self.uid = str(int(response_login["uid"]))
        self.realname = response_login["realname"]

        return self.uid

    async def async_get_patients(self) -> dict[str, str]:
        """
        Return {patient uid: display name}.

        A patient account only ever sees itself, and the login response already
        carries both values, so this needs no extra request.
        """
        if self.uid is None:
            await self.async_login()
        return {str(self.uid): str(self.realname)}

    async def async_get_data(self) -> dict[str, dict[str, Any]]:
        """
        Get data from the API, keyed by patient uid.

        The status blocks are lifted out of the response and the `chart`
        history is dropped: no entity reads it, and it is by far the largest
        part of the payload.
        """
        if self.uid is None:
            await self.async_login()

        # Create param with base64 encoded timestamp data for current day
        now = datetime.now(UTC)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day.replace(
            hour=23, minute=59, second=59, microsecond=999999
        )

        param_data = {
            "ts": [int(start_of_day.timestamp()), int(end_of_day.timestamp())],
            "tz": 0,  # UTC+0
        }
        param_encoded = base64.b64encode(json.dumps(param_data).encode()).decode()

        url = (
            self._base_url
            + PATIENT_STATUS_URL.replace("$userid", str(self.uid))
            + f"?param={param_encoded}"
        )

        response = await self._send("get", url, headers=self._headers, json_body={})

        # API status return 0 if everything goes well.
        data = response["data"]

        return {
            str(self.uid): {
                "uid": str(self.uid),
                "real_name": self.realname,
                "pump_status": data.get("pump_status") or {},
                "sensor_status": data.get("sensor_status") or {},
            }
        }


class MedtrumEasyViewFollowerApiClient(MedtrumEasyViewApiClientBase):
    """
    API class to retrieve Medtrum EasyView data through a follower account.

    The follower ("EasyFollow") endpoints are authenticated by the session
    cookie handed out by the login call, and every response carries res="OK"
    on success. One poll of the monitor list returns the full state of every
    patient the account may see, so there is no per patient request and no
    user id in the URL.
    """

    def __init__(
        self,
        username: str,
        password: str,
        base_url: str,
        session: aiohttp.ClientSession,
    ) -> None:
        """Initialize the API client."""
        super().__init__(username, password, base_url, session)
        self._cookie: str | None = None
        self.follower_uid: str | None = None

    def _store_cookie(self, set_cookie: str | None) -> None:
        """Keep the raw cookie so it can be replayed the way the app does."""
        if set_cookie:
            self._cookie = set_cookie.split(";")[0]

    def _build_headers(self, *, form: bool = False) -> dict[str, str]:
        """Return the headers the EasyFollow app sends."""
        headers = {
            "AppTag": FOLLOWER_APP_TAG,
            "DevInfo": FOLLOWER_DEV_INFO,
            "User-Agent": FOLLOWER_USER_AGENT,
            "Accept": CONTENT_TYPE,
        }
        if form:
            headers["Content-Type"] = CONTENT_TYPE_FORM
        if self._cookie:
            headers["Cookie"] = self._cookie
        return headers

    async def async_login(self) -> str | None:
        """Exchange the credentials for a session cookie."""
        self._cookie = None

        response = await self._send(
            "post",
            self._base_url + FOLLOWER_LOGIN_URL,
            headers=self._build_headers(form=True),
            data={
                "apptype": APP_TYPE_FOLLOW,
                "user_type": USER_TYPE_FOLLOWER,
                "platform": LOGIN_PLATFORM,
                "user_name": self._username,
                "password": self._password,
            },
            capture_cookie=True,
        )

        result = response.get("res")
        if result != "OK":
            message = response.get("msg") or f"Login rejected with res={result!r}"
            raise MedtrumEasyViewApiAuthenticationError(message)

        if not self._cookie:
            raise MedtrumEasyViewApiAuthenticationError(  # noqa: TRY003
                "Login succeeded but no session cookie was returned",  # noqa: EM101
            )

        uid = response.get("uid")
        self.follower_uid = None if uid is None else str(uid)
        return self.follower_uid

    async def async_get_patients(self) -> dict[str, str]:
        """
        Return {patient uid: display name} for every followed patient.

        Used by the config flow to prove the account can actually see patients.
        The polling call returns the same entries, so this is not needed at
        runtime.
        """
        response = await self._request_authenticated("get", FOLLOWER_LOGINDATA_URL)
        patients = self._extract_patients(response)
        return {uid: _display_name(entry) for uid, entry in patients.items()}

    async def async_get_data(self) -> dict[str, dict[str, Any]]:
        """Get the current state of every followed patient."""
        response = await self._request_authenticated("get", FOLLOWER_MONITOR_URL)
        return self._extract_patients(response)

    @staticmethod
    def _extract_patients(response: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Turn a monitorlist response into a mapping keyed by patient uid."""
        entries = response.get("monitorlist") or []
        patients: dict[str, dict[str, Any]] = {}
        for entry in entries:
            uid = entry.get("uid")
            if uid is None:
                _LOGGER.debug("Skipping monitor list entry without a uid")
                continue
            patients[str(uid)] = entry
        return patients

    async def _request_authenticated(self, method: str, path: str) -> dict[str, Any]:
        """
        Call an endpoint that needs a session, re-authenticating once if needed.

        The follower endpoints signal an expired session with HTTP 200 and
        res != "OK", not with 401/403, so a rejected session is only visible in
        the body.
        """
        if not self._cookie:
            await self.async_login()

        try:
            return await self._get_checked(method, path)
        except _SessionRejectedError as exception:
            _LOGGER.debug(
                "Session rejected (%s); re-authenticating and retrying once",
                exception,
            )
            await self.async_login()

        try:
            return await self._get_checked(method, path)
        except _SessionRejectedError as exception:
            raise MedtrumEasyViewApiAuthenticationError(str(exception)) from exception

    async def _get_checked(self, method: str, path: str) -> dict[str, Any]:
        """Send a session-authenticated request and validate the envelope."""
        body = await self._send(
            method,
            self._base_url + path,
            headers=self._build_headers(),
            capture_cookie=True,
        )

        if not isinstance(body, dict):
            raise MedtrumEasyViewApiError(  # noqa: TRY003
                f"Unexpected response type: {type(body).__name__}",  # noqa: EM102
            )

        if body.get("res") != "OK":
            message = body.get("msg") or f"res={body.get('res')!r}"
            raise _SessionRejectedError(message)

        return body


def _display_name(entry: dict[str, Any]) -> str:
    """Return the best available display name for a patient entry."""
    return str(entry.get("real_name") or entry.get("username") or entry.get("uid"))


def async_create_api_client(
    hass: HomeAssistant,
    account_type: str,
    username: str,
    password: str,
    base_url: str,
) -> MedtrumEasyViewApiClientBase:
    """
    Build the client for an account type, with the session it needs.

    The two APIs need different cookie handling. The patient endpoints rely on
    aiohttp's cookie jar to carry the session from login to the status call, so
    they use the shared Home Assistant session. The follower endpoints expect
    the raw cookie to be replayed verbatim the way the EasyFollow app does, so
    they get a private session with no jar of its own.
    """
    if account_type == ACCOUNT_TYPE_FOLLOWER:
        return MedtrumEasyViewFollowerApiClient(
            username=username,
            password=password,
            base_url=base_url,
            session=async_create_clientsession(
                hass, cookie_jar=aiohttp.DummyCookieJar()
            ),
        )

    return MedtrumEasyViewPatientApiClient(
        username=username,
        password=password,
        base_url=base_url,
        session=async_get_clientsession(hass),
    )
