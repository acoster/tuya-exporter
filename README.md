# tuya-exporter

Prometheus exporter for [Tuya](http://tuya.com).

## Prerequisites

- A Tuya API key. You can follow the instructions at https://developer.tuya.com/en/docs/iot/Tuya_Homebridge_Plugin 
  on how to set up a cloud project and link it with your account
- One or more temperature and humidity sensors. I got a bunch of cheapo ones on AliExpress. Some devices don't use 
  the "Standard Instruction Set", and you'll need to enable DP Instruction Mode. Please refer to [this 
  discussion](https://github.com/jasonacox/tinytuya/discussions/284#discussioncomment-4953888) for more info on how 
  to do it.

## Metrics

All metrics have a `device` label, with the device's name.

| Metric Name                             | Description                                                                                              |
|-----------------------------------------|----------------------------------------------------------------------------------------------------------|
| `tuya_sensor_temperature_celsius`       | Temperature reading, in Celsius                                                                          |
| `tuya_sensor_relative_humidity_percent` | Relative Humidity                                                                                        |
| `tuya_data_age_seconds`                 | Time in seconds since data was last reported by the sensor                                               |
| `tuya_battery_state`                    | Enum with the reported battery state (`unknown`, `low`, `middle`, `high`) in label `tuya_battery_state`. |

## Environment Variables

The job's behaviour is controlled with the following environment varialbes:

| Name                           | Description                                                                                  |
|--------------------------------|----------------------------------------------------------------------------------------------|
| `TUYA_EXPORTER_PORT`           | The port where the service listens to. Defaults to 7979                                      |
| `TUYA_EXPORTER_REFRESH_PERIOD` | The number of seconds the exporter will wait between data updates. Defaults to 60            |
| `TUYA_LOGLEVEL`                | The log level: messages at this level and above will be output to stderr. Defaults to `INFO` |
| `TUYA_REGION`                  | **Required** The region for your account (the "datacentre code", e.g. `eu`)                  |
| `TUYA_API_KEY`                 | **Required** Your API key                                                                    |
| `TUYA_API_SECRET`              | **Required** Your API secret                                                                 |
| `TUYA_DEVICE_ID`                | **Required** The ID of one of your tuya devices (doesn't need to be a sensor).               |

