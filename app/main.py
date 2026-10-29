import os
import sys
import time
import hid
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader, ConsoleMetricExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

resource = Resource.create({"service.name": "comonitor"})
reader = PeriodicExportingMetricReader(
    OTLPMetricExporter(),          # reads OTEL_EXPORTER_OTLP_* env vars when no args given (OTEL_EXPORTER_OTLP_ENDPOINT="http://otel-collector.observability:4318", OTEL_EXPORTER_OTLP_TIMEOUT="10")
    export_interval_millis=60_000,  # push every 60s
)
metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[reader]))

# acquire a meter
meter = metrics.get_meter("comonitor.meter")

# create a gauge
coconcentration_gauge = meter.create_gauge("comonitor.coconc", unit="[ppm]", description="CO2 concentration in parts per million")
temperature_gauge = meter.create_gauge("comonitor.temp", unit="Cel", description="Temperature in degrees Celsius")

DEVICE_PATH = b"/dev/comonitor"

NODE_NAME_TO_ROOM_NAME_MAP = {"regal": "kitchen", "maus": "living room"}

def get_attributes():
    return {"room_name": NODE_NAME_TO_ROOM_NAME_MAP.get(os.getenv("NODE_NAME"), "unknown")}

def open_device():
    try:
        print("Opening the device")
        h = hid.device()
        h.open_path(DEVICE_PATH)

        print("Manufacturer: %s" % h.get_manufacturer_string())
        print("Product: %s" % h.get_product_string())
        print("Serial No: %s" % h.get_serial_number_string())
        return h

    except IOError as ex:
        print(ex)
        print("You probably don't have the hard-coded device.")
        h.close()
        sys.exit(1)


def get_metrics(h):
    ret_temp = None
    ret_co2 = None

    try:
        print("Send feature report:")
        h.send_feature_report(bytearray([0xc4, 0xc6, 0xc0, 0x92, 0x40, 0x23, 0xdc, 0x96]))
        while True:
            r = h.read(8, timeout_ms=1000)
            if r:
                # print('read: "{}"'.format(r))
                metric = r[0]
                value = r[1]
                value_thousands = r[2]
                checksum = r[3]
                r4 = r[4]
                if r4 != 0x0d:
                    print("Unexpected data from device")
                    continue
                value_sum = metric + value + value_thousands

                metric_name = ""
                value_shifted = value << 8
                metric_value = value_shifted + value_thousands
                if metric == 0x42: # temperature
                    metric_value = metric_value / 16 - 273.15
                    ret_temp = metric_value
                    temperature_gauge.set(ret_temp, attributes=get_attributes())
                elif metric == 0x50: # CO2
                    ret_co2 = metric_value
                    coconcentration_gauge.set(ret_co2, attributes=get_attributes())
                elif metric == 0x44: # humidity
                    continue
                else: # unknown
                    continue
                print(hex(metric), metric_name, "%.1f" % metric_value)

            if ret_temp and ret_co2:
                return
    except IOError as ex:
        print(ex)

def main():
    h = open_device()
    while True:
        try:
            get_metrics(h)
        except IOError as ex:
            print(ex)
            h = open_device()
        time.sleep(60)

if __name__ == "__main__":
    main()