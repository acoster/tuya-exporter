import sys
import tinytuya
import schedule
import time
import os.path
import json
import functools

from collections import defaultdict
from prometheus_client import Gauge, start_http_server

CURRENT_TEMPERATURE = Gauge('tuya_sensor_temperature', 'Current temperature', ['device'], unit='celsius')
CURRENT_HUMIDITY = Gauge('tuya_sensor_relative_humidity', 'Relative humidity', ['device'], unit='percent')
UPDATE_AGE = Gauge('tuya_update_age', 'Update age for each sensor', ['device'], unit='seconds')


class Collector(object):
    def __init__(self, tuya_client: tinytuya.Cloud):
        self.__client = tuya_client
        self.__scale_factors = {}

    def collect(self):
        """Retrieves sensor statuses from Tuya cloud, and update the respective Prometheus metrics."""
        result = self.__client.getdevices(verbose=True)
        if result is None or 'success' not in result or not result['success']:
            raise Exception('Failed to retrieve data from Tuya Cloud')
        time_now = time.time()

        for device in result['result']:
            if device['category'] != 'wsdcg':
                continue
            update_age = time_now - device['update_time']
            if update_age > 10_800:
                continue
            UPDATE_AGE.labels(device['name']).set(int(update_age))

            for entry in device['status']:
                factor = self.get_scale_factor(device['id'], entry['code'])
                if entry['code'] == 'va_temperature':
                    temperature = entry['value'] / factor
                    CURRENT_TEMPERATURE.labels(device['name']).set(temperature)
                if entry['code'] == 'va_humidity':
                    humidity = entry['value'] / factor
                    CURRENT_HUMIDITY.labels(device['name']).set(humidity)

    def get_scale_factor(self, device_id, property_name):
        """Returns the scale factor for a (device, property) pair.

        If the scale factors have not been fetched for the device, this function will first retrieve them from Tuya Cloud
        and then store them locally.
        """
        if device_id not in self.__scale_factors:
            self.__retrieve_scale_factors(device_id)
        return self.__scale_factors[device_id][property_name]

    def __retrieve_scale_factors(self, device_id: str):
        """Retrieves the scale factors for a device from Tuya."""
        device_properties = self.__client.getproperties(device_id)
        if device_properties is None or 'success' not in device_properties or not device_properties['success']:
            raise Exception(f'Failed to fetch properties for device {device_id}')

        self.__scale_factors[device_id] = defaultdict(lambda: 1.0)

        for p in device_properties['result']['status']:
            if p['type'] == 'Integer' and 'values' in p:
                values = json.loads(p['values'])
                if 'scale' in values:
                    self.__scale_factors[device_id][p['code']] = 10 ** float(values['scale'])


def catch_exceptions(cancel_on_failure=False):
    """Wrapper to cancel schedule"""
    def catch_exceptions_decorator(job_func):
        @functools.wraps(job_func)
        def wrapper(*args, **kwargs):
            try:
                return job_func(*args, **kwargs)
            except:
                import traceback
                print(traceback.format_exc())
                if cancel_on_failure:
                    sys.exit(1)

        return wrapper

    return catch_exceptions_decorator


@catch_exceptions(cancel_on_failure=True)
def collect(collector: Collector):
    collector.collect()


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

    u = Collector(client)
    u.collect()
    schedule.every(refresh_period).seconds.do(collect, collector=u)
    start_http_server(listening_port)
    while True:
        schedule.run_pending()
