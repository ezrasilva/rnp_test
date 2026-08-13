#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
readonly COMPOSE_FILE="${SCRIPT_DIR}/compose.yml"
readonly RIC="openran-pqc-g0-ric"
readonly DU="openran-pqc-g0-du"
readonly RIC_IP="10.10.0.1"
readonly DU_IP="10.10.0.2"
readonly RUN_ID="${PHASE0_RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
readonly RESULT_DIR="${PROJECT_DIR}/results/phase0/${RUN_ID}"
readonly PCAP_IN_CONTAINER="/tmp/phase0-esp.pcap"
# RFC 4106 AES-GCM uses 16 bytes of key material plus a 4-byte salt.
readonly AEAD_KEY="0x00112233445566778899aabbccddeeff01020304"

KEEP_LAB="${PHASE0_KEEP_LAB:-0}"
CAPTURE_PID=""

mkdir -p "${RESULT_DIR}"
exec > >(tee "${RESULT_DIR}/gate.log") 2>&1

compose() {
    docker compose -f "${COMPOSE_FILE}" "$@"
}

in_ric() {
    docker exec "${RIC}" "$@"
}

in_du() {
    docker exec "${DU}" "$@"
}

cleanup() {
    local exit_code=$?
    if [[ -n "${CAPTURE_PID}" ]]; then
        docker exec "${RIC}" kill -INT "${CAPTURE_PID}" >/dev/null 2>&1 || true
    fi
    if [[ "${KEEP_LAB}" != "1" ]]; then
        compose down --remove-orphans >/dev/null 2>&1 || true
    fi
    exit "${exit_code}"
}
trap cleanup EXIT

fail() {
    printf 'FAIL: %s\n' "$*"
    exit 1
}

printf 'Phase 0 / Gate 0 - XFRM dataplane validation\n'
printf 'run_id=%s\nresult_dir=%s\n' "${RUN_ID}" "${RESULT_DIR}"

command -v docker >/dev/null || fail "docker is not installed"
docker info >/dev/null 2>&1 || fail "Docker daemon is unavailable"

compose down --remove-orphans >/dev/null 2>&1 || true
compose up -d --build

printf '\n[1/6] Checking namespace capabilities and XFRM API\n'
for endpoint in "${RIC}" "${DU}"; do
    docker exec "${endpoint}" ip xfrm state list >/dev/null \
        || fail "${endpoint} cannot execute 'ip xfrm state' (NET_ADMIN/XFRM unavailable)"
    docker exec "${endpoint}" ip xfrm policy list >/dev/null \
        || fail "${endpoint} cannot execute 'ip xfrm policy'"
done

printf '\n[2/6] Checking clear-text baseline connectivity\n'
in_ric ping -c 2 -W 1 "${DU_IP}" >/dev/null \
    || fail "baseline connectivity failed"

printf '\n[3/6] Installing ephemeral AES-GCM/ESP transport SAs\n'
in_ric ip xfrm state flush
in_ric ip xfrm policy flush
in_du ip xfrm state flush
in_du ip xfrm policy flush

# RIC -> DU uses SPI 0x100; DU -> RIC uses SPI 0x200.
in_ric ip xfrm state add src "${RIC_IP}" dst "${DU_IP}" proto esp spi 0x100 \
    mode transport aead 'rfc4106(gcm(aes))' "${AEAD_KEY}" 128
in_ric ip xfrm state add src "${DU_IP}" dst "${RIC_IP}" proto esp spi 0x200 \
    mode transport aead 'rfc4106(gcm(aes))' "${AEAD_KEY}" 128
in_du ip xfrm state add src "${RIC_IP}" dst "${DU_IP}" proto esp spi 0x100 \
    mode transport aead 'rfc4106(gcm(aes))' "${AEAD_KEY}" 128
in_du ip xfrm state add src "${DU_IP}" dst "${RIC_IP}" proto esp spi 0x200 \
    mode transport aead 'rfc4106(gcm(aes))' "${AEAD_KEY}" 128

in_ric ip xfrm policy add dir out src "${RIC_IP}/32" dst "${DU_IP}/32" \
    tmpl src "${RIC_IP}" dst "${DU_IP}" proto esp mode transport
in_ric ip xfrm policy add dir in src "${DU_IP}/32" dst "${RIC_IP}/32" \
    tmpl src "${DU_IP}" dst "${RIC_IP}" proto esp mode transport
in_du ip xfrm policy add dir in src "${RIC_IP}/32" dst "${DU_IP}/32" \
    tmpl src "${RIC_IP}" dst "${DU_IP}" proto esp mode transport
in_du ip xfrm policy add dir out src "${DU_IP}/32" dst "${RIC_IP}/32" \
    tmpl src "${DU_IP}" dst "${RIC_IP}" proto esp mode transport

printf '\n[4/6] Capturing the experimental link and sending protected traffic\n'
in_ric sh -c "tcpdump -U -n -i eth0 -w '${PCAP_IN_CONTAINER}' 'esp or icmp' >/tmp/tcpdump.log 2>&1 & echo \$!" \
    >"${RESULT_DIR}/capture.pid"
CAPTURE_PID="$(tr -d '[:space:]' < "${RESULT_DIR}/capture.pid")"
sleep 1
in_ric ping -c 5 -W 1 "${DU_IP}" | tee "${RESULT_DIR}/ping.txt"
in_ric kill -INT "${CAPTURE_PID}" || true
CAPTURE_PID=""
sleep 1
docker cp "${RIC}:${PCAP_IN_CONTAINER}" "${RESULT_DIR}/capture.pcap"

printf '\n[5/6] Recording XFRM state, policies, algorithms and counters\n'
{
    printf '%s\n' '=== RIC state ==='
    in_ric ip -s xfrm state
    printf '%s\n' '=== RIC policy ==='
    in_ric ip -s xfrm policy
    printf '%s\n' '=== DU state ==='
    in_du ip -s xfrm state
    printf '%s\n' '=== DU policy ==='
    in_du ip -s xfrm policy
    printf '%s\n' '=== Kernel crypto: GCM/AES ==='
    in_ric sh -c "grep -E '^(name|driver).*gcm.*aes' /proc/crypto || true"
} | tee "${RESULT_DIR}/xfrm.txt"

printf '\n[6/6] Evaluating acceptance criteria\n'
ESP_COUNT="$(in_ric tcpdump -n -r "${PCAP_IN_CONTAINER}" 'esp' 2>/dev/null | wc -l)"
CLEAR_ICMP_COUNT="$(in_ric tcpdump -n -r "${PCAP_IN_CONTAINER}" 'icmp and host 10.10.0.2' 2>/dev/null | wc -l)"
OUT_PACKETS="$(in_ric ip -s xfrm state | awk '
    /src 10.10.0.1 dst 10.10.0.2/{found=1}
    found && /lifetime current:/{getline; gsub(/\(packets\)/, "", $2); print $2; exit}
')"
IN_PACKETS="$(in_ric ip -s xfrm state | awk '
    /src 10.10.0.2 dst 10.10.0.1/{found=1}
    found && /lifetime current:/{getline; gsub(/\(packets\)/, "", $2); print $2; exit}
')"

[[ "${ESP_COUNT}" -gt 0 ]] || fail "no ESP packet was captured"
[[ "${CLEAR_ICMP_COUNT}" -eq 0 ]] || fail "clear-text ICMP appeared on the experimental link"
[[ "${OUT_PACKETS:-0}" -gt 0 ]] || fail "outbound XFRM counter did not increase"
[[ "${IN_PACKETS:-0}" -gt 0 ]] || fail "inbound XFRM counter did not increase"

cat >"${RESULT_DIR}/summary.json" <<EOF
{
  "run_id": "${RUN_ID}",
  "status": "pass",
  "esp_packets_captured": ${ESP_COUNT},
  "cleartext_icmp_packets_captured": ${CLEAR_ICMP_COUNT},
  "ric_outbound_xfrm_packets": ${OUT_PACKETS},
  "ric_inbound_xfrm_packets": ${IN_PACKETS}
}
EOF

printf '\nPASS: Gate 0 accepted (%s ESP packets, zero clear-text ICMP packets).\n' "${ESP_COUNT}"
printf 'Evidence: %s\n' "${RESULT_DIR}"
