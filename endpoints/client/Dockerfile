FROM alpine:3.20

RUN apk add --no-cache wpa_supplicant curl

COPY wpa_supplicant-*.conf /etc/wpa_supplicant/
COPY entrypoint.sh udhcpc.script /usr/local/bin/
RUN chmod +x /usr/local/bin/entrypoint.sh /usr/local/bin/udhcpc.script

ENV WPA_CONF=/etc/wpa_supplicant/wpa_supplicant-staff1.conf \
    CLIENT_NAME=campus-client

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
