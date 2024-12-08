import functools
import json
import logging
import os.path
import sys
import time
import typing
from collections import defaultdict

import schedule
import tinytuya
from prometheus_client import Gauge, Enum, start_http_server

logger = logging.getLogger()


class Collector(object):
    def __init__(self, tuya_client: tinytuya.Cloud):
        self.__client = tuya_client
        self.__scale_factors = {}
        self.__device_has_th_data = {}

        self.__temp_gauge = Gauge('tuya_sensor_temperature', 'Current temperature', ['device'], unit='celsius')
        self.__humidity_gauge = Gauge('tuya_sensor_relative_humidity', 'Relative humidity', ['device'], unit='percent')
        self.__data_age_gauge = Gauge('tuya_data_age', 'Data age for each sensor', ['device'], unit='seconds')
        self.__battery_state = Enum('tuya_battery_state', 'Tuya Battery State', ['device'],
                                    states=['unknown', 'low', 'middle', 'high'])

    def collect(self):
        """Retrieves sensor statuses from Tuya cloud, and update the respective Prometheus metrics."""
        logger.debug("Collecting sensor data")
        self.__clear_gauges()

        result = self.__client.getdevices(verbose=True)
        if result is None or 'success' not in result or not result['success']:
            raise Exception('Failed to retrieve data from Tuya Cloud')
        time_now = time.time()

        for device in result['result']:
            if not self.__has_humidity_or_temperature_data(device):
                continue

            update_age = time_now - device['update_time']
            if update_age > 10_800:
                logger.debug(f'Dropping device f{device["id"]}, as data is {update_age} seconds old.')
                continue

            self.__data_age_gauge.labels(device['name']).set(int(update_age))

            for entry in device['status']:
                factor = self.get_scale_factor(device['id'], entry['code'])
                if entry['code'] in ('va_temperature', 'temp_current'):
                    temperature = entry['value'] / factor
                    self.__temp_gauge.labels(device['name']).set(temperature)

                if entry['code'] in ('va_humidity', 'humidity_value'):
                    humidity = entry['value'] / factor
                    self.__humidity_gauge.labels(device['name']).set(humidity)

                if entry['code'] == 'battery_state' and self.is_valid_battery_state(entry['value']):
                    self.__battery_state.labels(device['name']).state(entry['value'])

    def get_scale_factor(self, device_id, property_name):
        """Returns the scale factor for a (device, property) pair.

        If the scale factors have not been fetched for the device, this function will first retrieve them from Tuya Cloud
        and then store them locally.
        """
        if device_id not in self.__scale_factors:
            self.__retrieve_scale_factors(device_id)
        return self.__scale_factors[device_id][property_name]

    @staticmethod
    def is_valid_battery_state(battery_state):
        return battery_state in ('low', 'middle', 'high')

    def __clear_gauges(self):
        """Clears data stored in gauges.

        This is done to stop reporting data for sensors whose name was changed, or that were removed from one's account.
        """
        self.__temp_gauge.clear()
        self.__humidity_gauge.clear()
        self.__data_age_gauge.clear()
        self.__battery_state.clear()

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

    def __has_humidity_or_temperature_data(self, device: typing.Dict):
        """Returns whether a device has temperature and humidity data."""
        if device['id'] not in self.__device_has_th_data:
            has_temperature = False
            has_humidity = False

            if 'status' in device:
                for entry in device['status']:
                    if 'code' not in entry:
                        pass

                    if entry['code'] in ('va_temperature', 'temp_current'):
                        has_temperature = True

                    if entry['code'] in ('va_humidity', 'humidity_value'):
                        has_humidity = True

            self.__device_has_th_data[device['id']] = has_temperature or has_humidity
            if self.__device_has_th_data[device['id']]:
                logger.debug(f'Device {device["id"]}, type {device["category"]} has temperature or humidity data')
        return self.__device_has_th_data[device['id']]


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
    refresh_period = int(os.getenv('TUYA_EXPORTER_REFRESH_PERIOD', 60))
    loglevel = os.getenv('TUYA_LOGLEVEL', 'INFO')

    logging.basicConfig(stream=sys.stderr, level=loglevel,
                        format='%(asctime)s %(levelname)s %(module)s - %(funcName)s: %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')
    logger.info(f'Starting Tuya Exporter on port {listening_port}, refreshing every {refresh_period} seconds.')

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
