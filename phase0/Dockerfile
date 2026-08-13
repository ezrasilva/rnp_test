FROM alpine:3.22

RUN apk add --no-cache \
        iproute2 \
        iputils \
        tcpdump

COPY entrypoint.sh /usr/local/bin/phase0-entrypoint
RUN chmod 0755 /usr/local/bin/phase0-entrypoint

ENTRYPOINT ["/usr/local/bin/phase0-entrypoint"]

