#!/usr/bin/env python3
"""Publish fake IoT sensor readings to the campus MQTT broker.

Environment variables:
  SENSOR_ID         unique id, e.g. temp-01
  SENSOR_TYPE       temperature | motion | humidity
  MQTT_BROKER       default 192.168.50.20
  MQTT_PORT         default 1883
  PUBLISH_INTERVAL  seconds, default 5
  MQTT_TOPIC        default campus/iot/<SENSOR_ID>
"""

import json
import os
import random
import signal
import sys
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

BROKER = os.getenv("MQTT_BROKER", "192.168.50.20")
PORT = int(os.getenv("MQTT_PORT", "1883"))
SENSOR_ID = os.getenv("SENSOR_ID", "sensor-01")
SENSOR_TYPE = os.getenv("SENSOR_TYPE", "temperature").strip().lower()
INTERVAL = float(os.getenv("PUBLISH_INTERVAL", "5"))
TOPIC = os.getenv("MQTT_TOPIC", f"campus/iot/{SENSOR_ID}")

ALLOWED_TYPES = {"temperature", "motion", "humidity"}
if SENSOR_TYPE not in ALLOWED_TYPES:
    print(
        f"[{SENSOR_ID}] WARNING: SENSOR_TYPE={SENSOR_TYPE!r} is not one of "
        f"{sorted(ALLOWED_TYPES)}; falling back to temperature",
        flush=True,
    )
    SENSOR_TYPE = "temperature"

_stop = False


def _handle_signal(signum, _frame):
    global _stop
    _stop = True
    print(f"[{SENSOR_ID}] received signal {signum}, stopping", flush=True)


def make_reading():
    if SENSOR_TYPE == "temperature":
        value = round(random.uniform(18.0, 26.0), 2)
    elif SENSOR_TYPE == "humidity":
        value = round(random.uniform(35.0, 65.0), 2)
    else:  # motion
        value = random.choice([0, 1])
    return {
        "id": SENSOR_ID,
        "type": SENSOR_TYPE,
        "value": value,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def connect_with_retry():
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=SENSOR_ID,
        clean_session=True,
    )
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    while not _stop:
        try:
            print(f"[{SENSOR_ID}] connecting to {BROKER}:{PORT}", flush=True)
            client.connect(BROKER, PORT, keepalive=60)
            return client
        except OSError as exc:
            print(f"[{SENSOR_ID}] connect failed: {exc}; retrying in 5s", flush=True)
            time.sleep(5)
    return client


def main():
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    print(
        f"[{SENSOR_ID}] type={SENSOR_TYPE} topic={TOPIC} "
        f"broker={BROKER}:{PORT} interval={INTERVAL}s",
        flush=True,
    )

    client = connect_with_retry()
    if _stop:
        return 0
    client.loop_start()

    try:
        while not _stop:
            payload = make_reading()
            body = json.dumps(payload, separators=(",", ":"))
            result = client.publish(TOPIC, body, qos=1)
            try:
                result.wait_for_publish(timeout=5)
            except RuntimeError:
                pass

            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                print(f"[{SENSOR_ID}] published {body}", flush=True)
            else:
                print(
                    f"[{SENSOR_ID}] publish failed rc={result.rc}; "
                    "will keep trying",
                    flush=True,
                )

            slept = 0.0
            while slept < INTERVAL and not _stop:
                time.sleep(min(1.0, INTERVAL - slept))
                slept += 1.0
    finally:
        client.loop_stop()
        client.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
