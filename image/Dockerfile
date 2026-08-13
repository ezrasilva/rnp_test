ARG DEBIAN_DIGEST=sha256:abd67ffcfa541b485a3dff59865ab629aa048a6c613e639d36e7456b0b229241

FROM debian:bookworm-slim@${DEBIAN_DIGEST} AS builder

ARG STRONGSWAN_VERSION=6.0.7
ARG STRONGSWAN_SHA256=b58266a437f054fbdba90db4555e92248ed80be383ca7dc903e681e24ac1f852

RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        libssl-dev \
        pkg-config \
 && curl --fail --show-error --location \
        "https://download.strongswan.org/strongswan-${STRONGSWAN_VERSION}.tar.gz" \
        --output /tmp/strongswan.tar.gz \
 && echo "${STRONGSWAN_SHA256}  /tmp/strongswan.tar.gz" | sha256sum --check --strict \
 && mkdir /tmp/strongswan \
 && tar --extract --gzip --file /tmp/strongswan.tar.gz \
        --directory /tmp/strongswan --strip-components=1 \
 && cd /tmp/strongswan \
 && ./configure \
        --prefix=/usr \
        --sysconfdir=/etc \
        --libexecdir=/usr/libexec \
        --enable-ml \
        --enable-curve25519 \
        --enable-openssl \
        --enable-vici \
        --enable-swanctl \
        --enable-kernel-netlink \
        --disable-systemd \
 && make -j"$(nproc)" \
 && make DESTDIR=/opt/strongswan install

FROM debian:bookworm-slim@${DEBIAN_DIGEST}

ARG STRONGSWAN_VERSION=6.0.7
LABEL org.opencontainers.image.title="OpenRAN PQC endpoint" \
      org.opencontainers.image.description="strongSwan endpoint with X25519 and ML-KEM for the OpenRAN PQC laboratory" \
      org.opencontainers.image.version="${STRONGSWAN_VERSION}" \
      org.opencontainers.image.source="https://download.strongswan.org/strongswan-${STRONGSWAN_VERSION}.tar.gz"

RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates \
        iperf3 \
        iproute2 \
        iputils-ping \
        jq \
        libsctp1 \
        lksctp-tools \
        libssl3 \
        procps \
        python3 \
        python3-pip \
        tcpdump \
        tshark \
 && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/strongswan/ /
COPY image/entrypoint.sh /usr/local/bin/openran-pqc-entrypoint
COPY strongswan/strongswan.conf /etc/strongswan.conf
COPY agent/ /opt/openran-pqc/source/agent/
COPY collector/ /opt/openran-pqc/source/collector/

RUN chmod 0755 /usr/local/bin/openran-pqc-entrypoint \
 && mkdir -p /run/charon /etc/swanctl/conf.d /var/log/strongswan /usr/share/openran-pqc \
 && pip3 install --no-cache-dir --break-system-packages \
        /opt/openran-pqc/source/agent /opt/openran-pqc/source/collector \
 && rm -rf /opt/openran-pqc/source \
 && { \
      printf 'strongSwan=%s\n' "${STRONGSWAN_VERSION}"; \
      dpkg-query -W -f='${binary:Package}=${Version}\n' | sort; \
    } > /usr/share/openran-pqc/components.txt

ENTRYPOINT ["/usr/local/bin/openran-pqc-entrypoint"]
CMD ["charon"]
