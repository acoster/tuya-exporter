import tinytuya
import schedule
import json
import os
import os.path

from prometheus_client import Gauge, start_http_server

TEMPERATURE_SETTING = Gauge('tuya_temperature_setting_celsius', 'Temperature setting for heater', ['device'])
CURRENT_TEMPERATURE = Gauge('tuya_sensor_temperature_celsius', 'Current temperature', ['device'])
HUMIDITY = Gauge('tuya_sensor_humidity', 'Relative humidity (%)', ['device'])
DEVICE_CURRENT = Gauge('tuya_current', 'Tuya plug/socket current (mA)', ['device'])
DEVICE_POWER = Gauge('tuya_power', 'Tuya plug/socket power (W)', ['device'])
DEVICE_VOLTAGE = Gauge('tuya_voltage', 'Tuya plug/socket voltage (V)', ['device'])
DEVICE_STATE = Gauge('tuya_device_on', 'Is the device on?', ['device'])


class Updater(object):
    def __init__(self, tuya_client: tinytuya.Cloud):
        self.__client = tuya_client
        self.__devices = {x['name']: x for x in self.__client.getdevices() if x['category'] in ('qn', 'cz', 'wsdcg')}
        self.__get_scale_factors()
        self.update()

    def __get_scale_factors(self):
        self.__scale_factors = dict()

        for device_name, device in self.__devices.items():
            r = self.__client.getproperties(device['id'])
            if r is None or 'success' not in r or not r['success']:
                raise Exception(f'Failed to fetch properties for device {device["id"]}')
            for p in r['result']['status']:
                if p['type'] == 'Integer' and 'values' in p:
                    v = json.loads(p['values'])
                    if 'scale' in v:
                        self.__scale_factors[(device['id'], p['code'])] = 10 ** int(v['scale'])

    def get_scale_factor(self, device_id, property_name):
        key = (device_id, property_name)
        if key in self.__scale_factors:
            return self.__scale_factors[key]
        return 1

    def update(self):
        for device_name, device in self.__devices.items():
            status = self.__client.getstatus(device['id'])
            if status is None or 'success' not in status or not status['success']:
                return

            for entry in status['result']:
                try:
                    entry_code = entry['code']
                    entry_value = entry['value']
                except KeyError:
                    continue

                factor = self.get_scale_factor(device['id'], entry_code)
                if entry_code in ('switch', 'switch_1'):
                    if entry_value:
                        DEVICE_STATE.labels(device_name).set(1)
                    else:
                        DEVICE_STATE.labels(device_name).set(0)
                elif entry_code == 'temp_set':
                    TEMPERATURE_SETTING.labels(device_name).set(entry_value / factor)
                elif entry_code in ('temp_current', 'va_temperature'):
                    CURRENT_TEMPERATURE.labels(device_name).set(entry_value / factor)
                elif entry_code == 'va_humidity':
                    HUMIDITY.labels(device_name).set(entry_value / factor)
                elif entry_code == 'cur_current':
                    DEVICE_CURRENT.labels(device_name).set(entry_value / factor)
                elif entry_code == 'cur_power':
                    DEVICE_POWER.labels(device_name).set(entry_value / factor)
                elif entry_code == 'cur_voltage':
                    DEVICE_VOLTAGE.labels(device_name).set(entry_value / factor)


if __name__ == '__main__':
    listening_port = int(os.getenv('TUYA_EXPORTER_PORT', 7979))
    refresh_period = int(os.getenv('TUYA_EXPORTER_REFRESH_PERIOD', 30))

    if os.path.isfile('tinytuya.json'):
        client = tinytuya.Cloud()
    else:
        tuya_region = os.environ['TUYA_REGION']
        tuya_api_key = os.environ['TUYA_API_KEY']
        tuya_api_secret = os.environ['TUYA_API_SECRET']
        tuya_device_id = os.environ['TUYA_DEVICE_ID']

        client = tinytuya.Cloud(tuya_region, tuya_api_key, tuya_api_secret, tuya_device_id)

    u = Updater(client)
    schedule.every(refresh_period).seconds.do(lambda: u.update())
    start_http_server(listening_port)
    while True:
        schedule.run_pending()
