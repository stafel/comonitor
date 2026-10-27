import sys
import time
import hid
from fastapi import FastAPI
from fastapi_utils.tasks import repeat_every
from opentelemetry import metrics
import asyncio
from contextlib import asynccontextmanager

# acquire a meter
meter = metrics.get_meter("comonitor.meter")

# create a gauge
coconcentration_gauge = meter.create_gauge("comonitor.coconc", unit="[ppm]", description="CO2 concentration in parts per million")
temperature_gauge = meter.create_gauge("comonitor.temp", unit="Cel", description="Temperature in degrees Celsius")

DEVICE_PATH = b"/dev/comonitor"

vid = 0x04d9
pid = 0xa052

try:
    print("Opening the device")
    h = hid.device()
    #h.open(vid, pid) # this wont work with only the symlinked device path
    h.open_path(DEVICE_PATH)

    print("Manufacturer: %s" % h.get_manufacturer_string())
    print("Product: %s" % h.get_product_string())
    print("Serial No: %s" % h.get_serial_number_string())

except IOError as ex:
    print(ex)
    print("You probably don't have the hard-coded device.")
    print("Update the h.open() line in this script with the one")
    print("from the enumeration list output above and try again.")
    h.close()
    sys.exit(1)


def get_metrics():
    ret_temp = None
    ret_co2 = None

    try:
        print("Send feature report:")
        h.send_feature_report(bytearray([0xc4, 0xc6, 0xc0, 0x92, 0x40, 0x23, 0xdc, 0x96]))
        while True:
            r = h.read(8)
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
                if metric == 0x42:
                    metric_name = "Temperature"
                    metric_value = metric_value / 16 - 273.15
                    ret_temp = metric_value
                elif metric == 0x50:
                    metric_name = "CO2"
                    ret_co2 = metric_value
                elif metric == 0x44:
                    metric_name = "Humidity"
                else:
                    continue
                    metric_name = "Unknown"
                print(hex(metric), metric_name, "%.1f" % metric_value)

            if ret_temp and ret_co2:
                return ret_temp, ret_co2
    except IOError as ex:
        print(ex)
        print("You probably don't have the hard-coded device.")
        print("Update the h.open() line in this script with the one")
        print("from the enumeration list output above and try again.")
    
    coconcentration_gauge.set(ret_co2) # attributes={"room": "roomname"}
    temperature_gauge.set(ret_temp)

    return ret_temp, ret_co2

async def run_every_60s():
    while True:
        await asyncio.sleep(60)
        try:
            get_metrics()  # your periodic logic
        except Exception as ex:
            print(ex)

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(run_every_60s())
    yield
    task.cancel()  # runs on shutdown
    try:
        await task
    except asyncio.CancelledError:
        pass

app = FastAPI(lifespan=lifespan)