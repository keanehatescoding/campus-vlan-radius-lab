FROM python:3.12-alpine

RUN pip install --no-cache-dir paho-mqtt==2.1.0

WORKDIR /app
COPY sensor.py entrypoint.sh udhcpc.script /app/
RUN chmod +x /app/entrypoint.sh /app/udhcpc.script

ENV MQTT_BROKER=192.168.50.20 \
    MQTT_PORT=1883 \
    PUBLISH_INTERVAL=5 \
    SENSOR_DHCP=1

ENTRYPOINT ["/app/entrypoint.sh"]
