[![version](https://img.shields.io/github/v/release/ankohanse/hass-studer-xcom?style=for-the-badge)](https://github.com/ankohanse/hass-studer-xcom)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://github.com/custom-components/hacs)
[![maintained](https://img.shields.io/maintenance/yes/2025?style=for-the-badge)](https://github.com/ankohanse/hass-studer-xcom)<br/>
[![license](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](https://github.com/ankohanse/hass-studer-xcom/blob/main/LICENSE)
[![buy_me_a_coffee](https://img.shields.io/badge/If%20you%20like%20it-Buy%20me%20a%20coffee-yellow.svg?style=for-the-badge)](https://www.buymeacoffee.com/ankohanse)


# Hass-Studer-Xcom

[Home Assistant](https://home-assistant.io/) custom component for retrieving sensor information from Studer-Innotec devices.
This component connects directly over the local network using the Studer xcom protocol.

The custom component is comfirmed to be compatible with:
- Xtender XTH 8000-48, XTM 4000-48
- Xcom-CAN (BSP connection to a third party BMS)
- Xcom-LAN (which actually is a Xcom232i with a Moxy NPort 5110A)
- BMS
- RCC-03
- VarioTrack

It should also be able to detect and handle
- Xtender (any other XTH, XTS and XTM models)
- VarioString
- RCC-02

This custom component provides a more reliable alternative to polling data from the Studer Portal via http as described in [Read Studer Parameters via Xcom-LAN and Rest Sensor](https://community.home-assistant.io/t/read-studer-parameters-via-xcom-lan-and-rest-sensor/597933).


# Prerequisites

This device depends on having a Studer Xcom-LAN (i.e. an Xcom-232i and a Moxa ethernet gateway) acting as a Xcom client and connecting to this integration. For older systems this will be a separate component, for future systems Studer have indicated that LAN connection will become part of the Xtender range.

The Studer Xcom-LAN is able to simultaneously send data to the Studer online portal as well as sending data to this integration.


# Installation

## HACS

This custom integration is waiting to be included into the HACS default integrations.
Until that time, you can add it as a HACS custom repository:
1. In the HACS page, press the three dots at the top right corner.
2. Select 'Custom Repositories'
3. Enter repository "https://github.com/ankohanse/hass-studer-xcom" (with the quotes seems to work better)
4. select category 'integration' and press 'Add'
2. Restart Home Assistant.
3. Follow the UI based [Initial Configuration](#initial-configuration)


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
    │   ├── button.py
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
    │   └── switch.py
    ```

2. Restart Home Assistant.
3. Follow the UI based [Initial Configuration](#initial-configuration)


# Initial Configuration

To start the setup of this custom integration:
- go to Home Assistant's Integration Dashboard
- Press 'Add Integration'
- Search for 'Studer-Innotec'
- Follow the prompts in the configuration steps

## Step 1 - Moxa discovery

The integration will try to detect the url to the Moxa Web Config in the local network.
This is a fully automatic step, no user input needed.

Do not run Configuration via a Nabu Casa cloud connection, as that will lead to the process getting stuck at the end of this step (known issue). Running Configuration from within the local network does not have this issue. See section [Knowledge base](#knowledge-base) for more information.

![setup_step_1](documentation/setup_discovery_moxa.png)

## Step 2 - Client details

The following properties are required to connect to Xcom client on the local network
- AC voltage: choose between 120 Vac or 240 Vac; used to select the correct Xcom params min and max values
- Port: specify the port as set in the Moxa NPort configuration. Default 4001
  
![setup_step_2](documentation/setup_client.png)

If the discovery of Studer devices in step 3 fails then the configuration returns to the screen of step 2.
In that case, check the configuration of the Xcom-LAN device as described in document [Xcom-LAN config.md](Xcom-LAN%20config.md)

## Step 3 - Xcom discovery

The integration will wait until the Xcom client connects to it. Next, it will try to detect any connected Studer devices.
This is a fully automatic step, no user input needed.

![setup_step_3](documentation/setup_discovery_xcom.png)

## Step 4 - Finish

After succcessful setup, all dicovered devices from the Studer installation should show up.

![setup_step_4](documentation/setup_success.png)

On the individual device pages, the hardware related device information is presented. Also displayed here are all default created entities, typically grouped into main entity sensors, controls and diagnostics.

Any entities that you do not need can be manually disabled using the HASS GUI. Or use the steps described under [Custom Configuration](#custom-configuration) to add or remove entities.

![controller_detail](documentation/integration_xt1.png)


# Custom configuration

The initial configuration will add default info and params entities for the detected Studer devices. Via the custom configuraton, other info and param entities can be added or removed for each device.

To configure:
- Go to Home Assistant's Integration Dashboard
- Click to open the 'Studer-Innotec' integration
- Click on 'Configure'

## Step 1 - Xcom discovery

The integration will wait until the Xcom client connects to it. Next, it will try to detect any newly connected Studer devices.
This is a fully automatic step, no user input needed.

## Step 2 - Params and infos numbers

An overview is shown of (default selected) params and info numbers for each detected device.
In this screen, the actions dropdown box allows you to:
- Add a param or info number to a device via a menu structure
- Add param or info numbers to a device by directly entering the numbers
- Remove param or info numbers from a device by entering the numbers
- Set advanced options

Once you are satisfied with the presented info and params numbers, select action 'Done' and press submit to create all entities (sensors, switches, numbers, etc).

![setup_step_2](documentation/setup_numbers.png)

A full list of available numbers can be found in the library used by this integration: 
- [aioxcom/xcom_datapoints_240v.json](https://github.com/ankohanse/aioxcom/blob/master/src/aioxcom/xcom_datapoints_240v.json)

Or it can be downloaded from Studer-Innotec:
- Open [www.studer-innotec.com](https://www.studer-innotec.com) in a browser
- Go to Downloads -> Openstuder -> communication protocol xcom 232i
- In the downloaded zip open file 'Technical specification - Xtender serial protocol appendix - 1.6.38.pdf'

# Entity retrieval limits

Restrict yourself to only those parameters you actually use and try to keep the time needed for fetching Studer Xcom data below 20 seconds. While in debug mode (see below), keep an eye on the log (Settings -> System -> Log -> Load Full Logs ),
and search for lines looking like:

`2024-08-26 09:57:46.383 DEBUG (MainThread) [custom_components.studer_xcom.coordinator] Finished fetching Studer Xcom data in 1.450 seconds (success: True)`

Note: the first data retrieval after a restart will always take longer than subsequent data retrievals.


# Entity writes to device

When the value of a Studer param is changed via this integration (via a Number, Select or Switch entity), these are written via Xcom to the affected device. 
Changes are stored in the device's RAM memory, not in its flash memory as you can only write to flash a limited number of times over its lifetime.

However, reading back the value from the entity will be from flash. 
As a result, the change to the entity value is not visible in the RCC or remote console.
You can only tell from the behavior of the PV system that the Studer param was indeed changed.  

After a restart/reboot of the PV system the system will revert to the value from Flash. So you may want to periodically repeat the write of changed param values via an automation.

**IMPORTANT**:

Be very carefull in changing params marked as having level Expert, Installer or even Qualified Service Person. If you do not know what the effect of a Studer param change is, then do not change it!


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
- [zocker-160](https://github.com/zocker-160/xcom-protocol)
- [Michael Jeffers](https://community.home-assistant.io/u/JeffersM)


# Knowledge base

## Local install
It is recommended to run Configuration on the local network, i.e. from a computer within the same network as where Home Assistant and the Studer devices are connected to.

If for some reasone you do need to run Configuration remotely (via a Nabu Casa cloud connection), then use the following method:
- Connect to the remote Home Assistant 
- Install the [Firefox addon](https://github.com/mincka/ha-addons)
- Open a firefox web browser window via the addon and connect to homeassistant.local:8123
- Add and configure the Studer-Innotec integration.

## Synchronise Time
The clock inside the Studer RCC will slowly drift out of sync with actual time. Moreover, it will not automatically switch from and to daylight savings time leading to a one hour offset during half of the year.

Both these issues can easily be resolved by configuring the following automation in Home Assistant; it will correct the time once a day. The chosen trigger time of 3:05am is so that it is after any daylight savings time adjustment.

```
alias: Studer RCC Sync Time
description: ""
triggers:
  - trigger: time_pattern
    hours: "3"
    minutes: "0"
    seconds: "5"
conditions: []
actions:
  - action: datetime.set_value
    target:
      entity_id: datetime.studer_4001_rcc_5002
    data:
      datetime: "{{ now() }}"
mode: restart
```

## Pause during Studer datalog uploads
The local Xcom-LAN will do a daily upload of datalogs to the Studer portal servers. This occurs at midnight on the RCC clock and can take up to 45 minutes. 

For larger systems the datalog uploads can fail when the Studer integration requests data updates at that same time (observed in a system with 16 Studer devices). In smaller systems no such conflict is observed.

To prevent problems it is better to configure the Studer integration to not send requests to the Xcom-LAN module during the daily datalog uploads. This requires the following three settings:

1. Disable automatic polling for updates of Studer entities.
    - Go to Settings -> Integrations -> Studer Innotec
    - Press the ⋮ and choose System Options
    - Turn OFF 'Enable polling for changes'

2. Add custom polling for updates of Studer entities.
    - Go to Settings -> Automations -> Create Automation
    - Define the new automation according to the following yaml:
      ```
      alias: Studer update entities
      description: ""
      triggers:
        - trigger: time_pattern
          seconds: /30
      conditions:
        - condition: time
          after: "01:00:00"
          before: "23:59:00"
      actions:
        - action: homeassistant.update_entity
          data:
            entity_id:
              - sensor.studer_4001_bsp_7032
      mode: single
      ```

      Note that you only need to set one entity_id and it does not matter which studer entity is chosen. A trigger to update one entity will result in update of all Studer entities. The chosen entity_id above is 'sensor.studer_4001_bsp_7032' (BSP State of Charge). Another logical candidate is 'datetime.studer_4001_rcc_5002' (RCC Datetime).

3. Make sure the RCC Datetime is regularly synchronised so that time drift and start or end of Daylight savings will not invalidate the time condition in the automation of step 2. See knowledge base section [Synchronise Time](#synchronise-time).
