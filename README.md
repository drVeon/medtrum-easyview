[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://img.shields.io/badge/HACS-Repository-41BDF5.svg)](https://my.home-assistant.io/redirect/hacs_repository/?category=integration&repository=medtrum-easyview&owner=sapk)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Validate with Hassfest/HACS](https://github.com/sapk/medtrum-easyview/actions/workflows/validate.yml/badge.svg)](https://github.com/sapk/medtrum-easyview/actions/workflows/validate.yml)

# Medtrum EasyView Integration for Home Assistant

[integration_medtrum-easyview]: https://github.com/drVeon/medtrum-easyview.git

**This integration will set up the following platforms for each patient linked to the Medtrum EasyView or EasyFollow account.**

Platform | Description
-- | --

`sensor` | Show info from Medtrum EasyView API.
- Pump Status
- Pump Remaining time
- Pump Remaining dose
- Pump Last update
- Blood Glucose Target
- Basal Daily Volume
- Bolus Daily Volume
- Basal Rate
- Last Bolus Delivered Time
- Last Bolus Delivered Volume
- Active Insulin
- Glucose Value (the current CGM reading, in the unit you select)
- Glucose Trend
- Sensor Last update
- Sensor Battery (diagnostic)

Entities are created per patient and only for the values that patient's
devices actually publish, so an AutoMode patch gets a smaller set than a
classic one.

`binary_sensor` | Show binary states from Medtrum EasyView API.
- Basal Active
- Pump (connectivity status)
    - Serial number: The serial number of the device (in hexadecimal, uppercase)
    - User ID: The Medtrum EasyView user ID
    - Patient: The patient name associated with the account
- Sensor (connectivity status)

## Installation

1. Add this repository URL as a custom repository in HACS
2. Restart Home Assistant
3. In the HA UI go to "Configuration" -> "Integrations" click "+" and search for "Medtrum EasyView"

## Configuration is done in the UI

You need a Medtrum account to use this integration. Two kinds work, and you
pick which one you are using when you add the integration:

- **Patient (EasyView)** — the account of the person wearing the pump. It sees
  that one patient.
- **Follower (EasyFollow)** — a monitor account that has been invited to follow
  one or more patients. A single config entry then covers **every** patient the
  account follows, each with its own device.

In both cases:

- Use the username (mail) and password of that account.
- A session is retrieved for the duration of the HA session and renewed
  automatically when the server rejects it.

Existing installations keep working unchanged: entries created before follower
support existed are treated as patient accounts.

## API reference

The endpoints and payloads both account types use are documented in
[docs/API.md](docs/API.md).


## Contributions are welcome!

If you want to contribute to this please read the [Contribution guidelines](CONTRIBUTING.md)

This project was forked from [Medtrum EasyView Integration](https://github.com/sapk/medtrum-easyview.git)

Used EasyFollow API request flow from [GlucoDataHandler](https://github.com/pachi81/GlucoDataHandler.git)

EasyFollow integration has been added using AI-assisted development.
***
