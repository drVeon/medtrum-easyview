# Medtrum EasyView API

Reference for the two APIs this integration talks to. Both are undocumented
and were reconstructed from traffic; nothing here is an official contract and
Medtrum can change it at any time.

Sample responses are real captures with identifiers, names and serials
replaced.

| | Patient ("EasyView") | Follower ("EasyFollow") |
| --- | --- | --- |
| Login | `POST /v3/api/v2.0/login` | `POST /mobile/ajax/login` |
| Request body | JSON | form-urlencoded |
| Success marker | `error: 0` | `res: "OK"` |
| Poll | `GET /api/v2.1/monitor/{uid}/status?param=…` | `GET /mobile/ajax/monitor?flag=monitor_list` |
| Patients returned | one (the account itself) | every patient the account follows |
| Session | cookie jar | `Set-Cookie` replayed verbatim |
| Expired session | HTTP 401 / 403 | HTTP 200 with `res != "OK"` |
| `AppTag` | `v=3.0.2(15);n=eyvw` | `v=1.2.70(112);n=eyfo;p=android` |

Base URL is `https://easyview.medtrum.eu`, or `https://easyview.medtrum.fr`
for accounts served by the French endpoint.

## Why both are supported

The two APIs publish the **same status blocks under the same field names**.
Compared over one classic patch, `pump_status` matched on all 40 fields and
`sensor_status` on all 15, with the follower payload adding one extra field
(`S9StartTime`). So both clients normalise to the same shape and the entity
layer does not care which one produced it:

```python
{patient_uid: {"uid": …, "real_name": …, "pump_status": {…}, "sensor_status": {…}}}
```

## Patient API

### Login

```http
POST /v3/api/v2.0/login
AppTag: v=3.0.2(15);n=eyvw
Content-Type: application/json

{"user_name": "user@example.com", "password": "…", "user_type": "P"}
```

```json
{"error": 0, "uid": "100000", "realname": "Jane Doe"}
```

`error` is non-zero for bad credentials. The response sets a session cookie
which aiohttp's cookie jar carries to the poll call.

### Poll

`param` is base64-encoded JSON naming the window to fetch:

```json
{"ts": [1787443200, 1787529599], "tz": 0}
```

```http
GET /api/v2.1/monitor/100000/status?param=eyJ0cyI6…
AppTag: v=3.0.2(15);n=eyvw
```

```json
{"error": 0, "data": {"uid": "100000", "realname": "Jane Doe",
  "data_source": "daopapp", "event_no": 0,
  "pump_status": {…}, "sensor_status": {…}, "chart": {…}}}
```

`chart` holds the day's history — around 470 `sg` rows plus `basal`, `bolus`,
`calibRecord`, `pump_alarm` and `sensor_alarm` — and is by far the largest part
of the response. No entity reads it, so the client discards it.

An account with no pump paired returns `pump_status` and `sensor_status` as
**empty objects**, not objects full of nulls.

## Follower API

### Login

```http
POST /mobile/ajax/login
AppTag: v=1.2.70(112);n=eyfo;p=android
DevInfo: Android 11;Google generic_x86_arm;Android 11
User-Agent: okhttp/3.5.0
Content-Type: application/x-www-form-urlencoded

apptype=Follow&user_type=M&platform=google&user_name=…&password=…
```

```json
{"res": "OK", "uid": 90000, "usertype": "M"}
```

`user_type=M` is what makes this a monitor/follower login; a patient account
cannot read the monitor list. The `Set-Cookie` value must be replayed verbatim
on every later request, so the client keeps it itself rather than letting
aiohttp manage a jar.

### Poll

```http
GET /mobile/ajax/monitor?flag=monitor_list
Cookie: <the cookie from login>
```

```json
{"res": "OK", "monitorlist": [
  {"uid": 100000, "real_name": "Jane Doe", "username": "…",
   "pump_status": {…}, "sensor_status": {…}, "monitor_setting": {…}}
]}
```

`GET /mobile/ajax/logindata` returns the same `monitorlist` shape and is used
at config time to check the account actually follows somebody.

An expired session comes back as **HTTP 200** with `res` set to something
other than `"OK"`, so it can only be detected in the body. The client logs in
again and retries once before giving up with an authentication error.

## Status blocks

### `pump_status`

```json
{
  "status": 33, "state": 33, "updateTime": 1787499452,
  "remainingTime": 3223, "remainingDose": 151.9499969482422,
  "bGTarget": 100, "AutoModeSGTarget": 100, "AutoModeEnabledNew": 0,
  "basalRate": 1, "basalSum": 0, "basalDeliveried": 2.6,
  "basalDeliveriedTime": 1787489917, "basalPatternTotal": 23.8,
  "basalType": 0, "basalDuration": 0, "basalPercent": 0,
  "autobasalstatus": 1, "autobasalicon": 0,
  "bolusSum": 0, "bolusDeliveried": 6.399999618530273,
  "bolusDeliveriedTime": 1787491440, "bolusSet": 0, "bolusType": 0,
  "lastBolusType": 1, "extendBolusSet": 0, "extendBolusDeliveried": 0,
  "extendBolusDuration": 0, "iob": 1.1,
  "exerciseStatus": 0, "exerciseDuration": 30, "exerciseRemainTime": 30,
  "suspendTime": 1787487868, "suspendRemainingTime": -177,
  "serial": 3900000000, "pumpId": 129, "deviceType": 88,
  "runningMins": 1096, "appName": "EasyPatch", "platform": "google"
}
```

Not all patches publish the same fields. A **classic** patch reports the 40
fields above. An **AutoMode** patch omits `status`, `basalRate`, `basalSum`
and `bolusSum`, and adds around 25 of its own — `singleAutoModeCurrentBasal`,
`autoBasalState`, `connectState`, `TempTarget`, `rssi`, and the `wizard*` /
`another*` bolus families. Entities are therefore created per patient and only
for the keys that patient actually publishes.

`status` and `state` carry the same code and only one of the two may be
present, so the integration reads `status` and falls back to `state`. Codes
are decoded by `PumpStatus` in `const.py`; anything unrecognised is reported
as `Unknown Status (n)` rather than hidden.

`bGTarget` is always **mg/dL**, unlike `glucose` below.

### `sensor_status`

```json
{
  "glucose": 9.6, "glucoseRate": 0, "status": 3,
  "updateTime": 1787499388, "batteryPercent": 0.52,
  "sequence": 9666, "sensorLifetimeTotalCount": 10079,
  "nextSequenceNeedCalibrate": 21600, "sensorId": 5,
  "serial": 2600000000, "deviceType": "TG158", "current": 2855,
  "rssi": -82, "appName": "EasyPatch", "platform": "google"
}
```

- **`glucose`** is in the *account's display unit*, which the payload never
  states. It is inferred from the value: valid mg/dL is 36–600 and valid
  mmol/L is 2–33.3, and those ranges do not overlap, so anything at or below
  33.3 can only be mmol/L. The conversion factor is 18.0182.
- **`glucose: 0.0`** is not a reading of zero — the sensor has no value. The
  reason is inferred from `sequence`, which counts 2-minute samples since the
  sensor was started: at or below 15 the sensor is warming up; at or past
  `nextSequenceNeedCalibrate` it needs calibrating; otherwise there is simply
  no valid value.
- **`glucoseRate`** is a trend code: 0 and 8 flat, 1–3 rising with increasing
  steepness, 4–6 falling with increasing steepness, 7 unknown.
- **`batteryPercent`** is a 0..1 fraction, not a percentage.
- `sequence` against `sensorLifetimeTotalCount` gives sensor age and remaining
  wear, both exposed as attributes of the glucose entity.

### Not mapped

`singleAutoModeCurrentBasal` is not published as Basal Rate: its meaning has
not been confirmed, and presenting an unverified dosing figure would be a
guess on medical data. `rssi` is not published either — it read −82 for one
transmitter but 127 and 0 for others, which are not plausible dBm values.

## Errors

| Condition | Raised | Coordinator result |
| --- | --- | --- |
| HTTP 401 / 403 | `MedtrumEasyViewApiAuthenticationError` | `ConfigEntryAuthFailed` |
| Patient login `error != 0` | `MedtrumEasyViewApiAuthenticationError` | `ConfigEntryAuthFailed` |
| Follower `res != "OK"` twice | `MedtrumEasyViewApiAuthenticationError` | `ConfigEntryAuthFailed` |
| Timeout over 20 s | `MedtrumEasyViewCommunicationError` | `UpdateFailed` |
| DNS / connection failure | `MedtrumEasyViewCommunicationError` | `UpdateFailed` |
| Other 4xx / 5xx, anything else | `MedtrumEasyViewApiError` | `UpdateFailed` |
