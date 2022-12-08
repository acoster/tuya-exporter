import tinytuya
import schedule
import os

from prometheus_client import Gauge, start_http_server

TEMPERATURE_SETTING = Gauge('tuya_temperature_setting_celsius', 'Temperature setting for heater', ['device'])
CURRENT_TEMPERATURE = Gauge('tuya_sensor_temperature_celsius', 'Current temperature', ['device'])
DEVICE_STATE = Gauge('tuya_device_on', 'Is the device on?', ['device'])


class Updater(object):
    def __init__(self, tuya_client: tinytuya.Cloud):
        self.__client = tuya_client
        self.__devices = {x['name']: x for x in self.__client.getdevices() if x['category'] == 'qn'}
        self.update()

    def update(self):
        for device_name, device in self.__devices.items():
            status = self.__client.getstatus(device['id'])
            if 'success' not in status or not status['success']:
                return

            for entry in status['result']:
                if entry['code'] == 'switch':
                    if entry['value']:
                        DEVICE_STATE.labels(device_name).set(1)
                    else:
                        DEVICE_STATE.labels(device_name).set(0)
                elif entry['code'] == 'temp_set':
                    TEMPERATURE_SETTING.labels(device_name).set(entry['value'])
                elif entry['code'] == 'temp_current':
                    CURRENT_TEMPERATURE.labels(device_name).set(entry['value'])


if __name__ == '__main__':
    tuya_region = os.environ['TUYA_REGION']
    tuya_api_key = os.environ['TUYA_API_KEY']
    tuya_api_secret = os.environ['TUYA_API_SECRET']
    tuya_device_id = os.environ['TUYA_DEVICE_ID']

    listening_port = int(os.getenv('TUYA_EXPORTER_PORT', 7979))
    refresh_period = int(os.getenv('TUYA_EXPORTER_REFRESH_PERIOD', 30))

    client = tinytuya.Cloud(tuya_region, tuya_api_key, tuya_api_secret, tuya_device_id)
    u = Updater(client)
    schedule.every(refresh_period).seconds.do(lambda: u.update())
    start_http_server(listening_port)
    while True:
        schedule.run_pending()
