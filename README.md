[![version](https://img.shields.io/github/v/release/ankohanse/hass-studer-xcom?style=for-the-badge)](https://github.com/ankohanse/hass-studer-xcom)
[![maintained](https://img.shields.io/maintenance/yes/2024?style=for-the-badge)](https://github.com/ankohanse/hass-dab-pumpsstuder-xcom)
[![license](https://img.shields.io/github/license/toreamun/amshan-homeassistant?style=for-the-badge)](LICENSE)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://github.com/custom-components/hacs)<br/>
[![buy_me_a_coffee](https://img.shields.io/badge/If%20you%20like%20it-Buy%20me%20a%20coffee-yellow.svg?style=for-the-badge)](https://www.buymeacoffee.com/ankohanse)


# Hass-Studer-Xcom

[Home Assistant](https://home-assistant.io/) custom component for retrieving sensor information from Studer-Innotec devices.
This component connects directly over the local network using the Studer xcom protocol.

The custom component was tested with:
- Xtender XTH 8000-48 (but should also work for other XTH, XTS and XTM)
- Xcom-CAN (BSP connection to a third party BMS)
- Xcom-LAN (which actually is a Xcom232i with a Moxy NPort 5110A)
- RCC-03

It should also be able to detect and handle
- Studer BMS
- VarioTrack
- VarioString
- RCC-02

This custom component provides a more reliable alternative to polling data from the Studer Portal via http as described in [Read Studer Parameters via Xcom-LAN and Rest Sensor](https://community.home-assistant.io/t/read-studer-parameters-via-xcom-lan-and-rest-sensor/597933).


# Prerequisites

This device depends on having a Studer Xcom-LAN (i.e. an Xcom-232i and a Moxa ethernet gateway) acting as a Xcom client and connecting to this integration. For older systems this will be a separate component, for future systems Studer have indicated that LAN connection will become part of the Xtender range.

The Studer Xcom-LAN will be able to simultaneously send data to the Studer online portal as well as sending data to this integration.

Configuration steps:

1. Download and install the Moxa DSU tool (Device Search Utility)
    - Open [www.moxa.com](https://www.moxa.com) in a browser
    - Select Support -> Software and Documentation
    - Choose NPort 5100A series (or whatever specific device you have)
    - Scroll down under 'Related Software, Firmware and Drivers' to find 'Device Search Utility'
    - Download and install the utility

2. Locate the Moxa NPort device on the local network
    - Run the Moxa Device Search Utility
    - Press the 'Search' button and wait until the search finishes
    - The utility should display the found NPort device
    - Double click on the found device to open its configuration page

      ![dsu_search_results](documentation/DSU_results.png)

3. Configure the Moxa NPort device
    - In the Main Menu, select 'Operating Settings' -> Port 1
    - Verify that 'Operation Mode' is set to 'TCP Client'
    - Add the ip-address or network name of your HomeAssistant as 'Destination IP address'
    - Press the 'Submit' button
    - Press 'Save/Restart'

      ![moxa_operating_settings](documentation/Moxa_operating_settings.png)


# Installation

## HACS

This custom integration is waiting to be included into the HACS default integrations.
Until that time, you can add it as a HACS custom repository:
1. In the HACS page, press the three dots at the top right corner.
2. Select 'Custom Repositories'
3. Enter repository "https://github.com/ankohanse/hass-studer-xcom" (with the quotes seems to work better)
4. select category 'integration' and press 'Add'
2. Restart Home Assistant.
3. Follow the UI based [Configuration](#configuration)


## Manual install

1. Under the `<config directory>/custom_components/` directory create a directory called `studer_xcom`. 
Copying all files in `/custom_components/studer_xcom/` folder from this repo into the new `<config directory>/custom_components/studer_xcom/` directory you just created.

    This is how your custom_components directory should look like:

    ```bash
    custom_components
    ├── studer_xcom
    │   ├── translations
    │   │   └── en.json
    │   ├── __init__.py
    │   ├── binary_sensor.py
    │   ├── config_flow.py
    │   ├── const.py
    │   ├── coordinator.py
    │   ├── diagnostics.py
    │   ├── entity_base.py
    │   ├── manifest.json
    │   ├── number.py
    │   ├── select.py
    │   ├── sensor.py
    │   ├── strings.json
    │   ├── switch.py
    │   ├── xcom_api.py
    │   ├── xcom_const.py
    │   ├── xcom_datapoints.json
    │   ├── xcom_datapoints.py
    │   ├── xcom_families.py
    │   └── xcom_protocol.py  
    ```

2. Restart Home Assistant.
3. Follow the UI based [Configuration](#configuration)


# Configuration

To start the setup of this custom integration:
- go to Home Assistant's Integration Dashboard
- Press 'Add Integration'
- Search for 'Studer-Innotec'
- Follow the prompts in the configuration steps

## Step 1 - Client details

The following properties are required to connect to Xcom client on the local network
- Port: specify the port as set in the Moxa NPort confuguration. Default 4001
  
![setup_step_1](documentation/setup_client.png)

## Step 2 - Xcom discovery

The integration will wait until the Xcom client connects to it. Next, it will try to detect any connected Studer devices.
This is a fully automatic step, no user input needed.

![setup_step_2](documentation/setup_discovery.png)

## Step 3 - Params and infos numbers

Choose the params and info numbers you want for each detected device.

A full list of available numbers can be found in the files of this integration: 
- custom_components/studer_xcom/xcom_datapoints.json

Or it can be downloaded from Studer-Innotec:
- Open [www.studer-innotec.com](https://www.studer-innotec.com) in a browser
- Go to Downloads -> Openstuder -> communication protocol xcom 232i
- In the downloaded zip open file 'Technical specification - Xtender serial protocol appendix - 1.6.38.pdf'

Restrict yourself to only those parameters you actually use and try to keep the time needed for fetching Studer Xcom data below 20 seconds. While in debug mode (see below), keep an eye on the log (Settings -> System -> Log -> Load Full Logs ),
and search for a like looking like:

`2024-08-26 09:57:46.383 DEBUG (MainThread) [custom_components.studer_xcom.coordinator] Finished fetching Studer Xcom data in 1.450 seconds (success: True)`
  
![setup_step_3](documentation/setup_numbers.png)

## Step 4 - Finish

Press submit to create all entities (sensors, switches, numbers, etc) for the configured params and infos numbers
  
![setup_step_4](documentation/setup_finish.png)

## Step 5 - Success

After succcessful setup, all devices from the Studer installation should show up.

![setup_step_5](documentation/setup_success.png)

On the individual device pages, the hardware related device information is displayed, together with sensors typically grouped into main entity sensors, controls and diagnostics.

Any sensors that you do not need can be manually disabled using the HASS GUI.

![controller_detail](documentation/integration_xt1.png)


# Re-configuration

In case you want to add or remove Studer params or infos into the integration, this can be done via a Reconfigure.
This can also be used to discover new Studer devices added to the installation.

To reconfigure:
- Go to Home Assistant's Integration Dashboard
- Click to open the 'Studer-Innotec' integration
- Click on the hamburger icon to open the menu and select 'Reconfigure'
- The same steps as for 'Configuration' will appear

![controller_detail](documentation/integration_reconfigure.png)


# Options configuration

A limited set of parameters can be set via the 'Options' page.

To reconfigure:
- Go to Home Assistant's Integration Dashboard
- Click to open the 'Studer-Innotec' integration
- Click on 'Configure'

![controller_detail](documentation/integration_options.png)


# Entity writes to device

When the value of a Studer param is changed via this integration (via a Number, Select or Switch entity), these are written via Xcom to the affected device. 
Changes are stored in the device's RAM memory, not in its flash memory as you can only write to flash a limited number of time over its lifetime.

However, reading back the value from the entity will be from flash (querying RAM gives unreliable responses). As a result, the change to the entity value is not visible. You can only tell from the behavior of the PV system that the Studer param was indeed changed. After a restart/reboot of the PV system the system will revert to the value from Flash. So you may want to periodically repeat the write of changed param values via an automation.

**IMPORTANT**:

I will not take responsibility for damage to your PV system resulting from you choosing to change Studer params you are not supposed to change. Or setting a combination of param values that cause an invalid status.  
Be very carefull in changing params marked as having level Expert, Installer or even Qualified Service Person. If you do not know what the effect of a Studer param change is, then do not change it.


# Troubleshooting

Please set your logging for the this custom component to debug during initial setup phase. If everything works well, you are safe to remove the debug logging.

```yaml
logger:
  default: warn
  logs:
    custom_components.studer_xcom: debug
```


# Credits

Special thanks to the following people for providing the information this custom integration is based on:
- [Michael Jeffers](https://community.home-assistant.io/u/JeffersM)


