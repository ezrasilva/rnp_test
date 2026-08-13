#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
readonly TOPOLOGY="${PROJECT_DIR}/lab/openran-pqc.clab.yml"
readonly PROFILE="${1:-m1}"
readonly PROFILE_FILE="${SCRIPT_DIR}/profiles/${PROFILE}.env"
readonly RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
readonly RESULT_DIR="${PROJECT_DIR}/results/experiments/${RUN_ID}"
readonly DISTRIBUTED_RESULT_DIR="${PROJECT_DIR}/results/distributed/${RUN_ID}"
readonly SPOOL_ROOT="${PROJECT_DIR}/results/spool"
readonly RIC="clab-openran-pqc-ric"
readonly DU="clab-openran-pqc-du"
readonly ARTIFACTS="${PROJECT_DIR}/experiments/artifacts.py"
readonly IMAGE="openran-pqc:6.0.7"
readonly EXPERIMENT_KIND="${EXPERIMENT_KIND:-combined}"

[[ -f "${PROFILE_FILE}" ]] || { printf 'Unknown profile: %s\n' "${PROFILE}" >&2; exit 2; }
# shellcheck disable=SC1090
source "${PROFILE_FILE}"
[[ "${MODE}" = M1 || "${MODE}" = M2 || "${MODE}" = M3 ]] \
    || { printf 'Unsupported mode: %s\n' "${MODE}" >&2; exit 2; }
[[ "${EXPERIMENT_KIND}" = combined || "${EXPERIMENT_KIND}" = steady || \
   "${EXPERIMENT_KIND}" = establishment ]] \
    || { printf 'Unsupported experiment kind: %s\n' "${EXPERIMENT_KIND}" >&2; exit 2; }
[[ "${MODE}" != M1 || "${EXPERIMENT_KIND}" != establishment ]] \
    || { printf 'M1 has no IKE establishment experiment\n' >&2; exit 2; }

mkdir -p "${RESULT_DIR}" "${PROJECT_DIR}/results/distributed" \
    "${SPOOL_ROOT}/ric" "${SPOOL_ROOT}/du"
exec > >(tee "${RESULT_DIR}/run.log") 2>&1
CAPTURE_PID=""
SECRET_FILE=""

fail() { printf 'FAIL: %s\n' "$*"; exit 1; }

clab() {
    if [[ "${EUID}" -eq 0 ]]; then
        containerlab "$@"
    elif sudo -n true 2>/dev/null; then
        sudo -n containerlab "$@"
    else
        fail "Containerlab requires root; configure passwordless sudo or run this script with sudo"
    fi
}

containerlab_cleanup() {
    if [[ "${EUID}" -eq 0 ]]; then
        containerlab destroy --topo "${TOPOLOGY}" --cleanup >/dev/null 2>&1 || true
    else
        sudo -n containerlab destroy --topo "${TOPOLOGY}" --cleanup >/dev/null 2>&1 || true
    fi
}

cleanup() {
    local endpoint local_spool
    if [[ -n "${CAPTURE_PID}" ]]; then
        docker exec "${RIC}" kill -INT "${CAPTURE_PID}" >/dev/null 2>&1 || true
    fi
    docker exec "${RIC}" pkill -f 'pqc-agent' >/dev/null 2>&1 || true
    docker exec "${DU}" pkill -f 'pqc-agent' >/dev/null 2>&1 || true
    if [[ -n "${SECRET_FILE}" && -f "${SECRET_FILE}" ]]; then
        # The file contains only an ephemeral laboratory PSK and is never copied
        # into results. Removing the explicit mktemp path is safe.
        unlink "${SECRET_FILE}" || true
    fi
    containerlab_cleanup
    if [[ -n "${SUDO_UID:-}" && -n "${SUDO_GID:-}" && \
          -d "${DISTRIBUTED_RESULT_DIR}" ]]; then
        chown -R "${SUDO_UID}:${SUDO_GID}" "${DISTRIBUTED_RESULT_DIR}"
        chmod -R u+rwX,go+rX "${DISTRIBUTED_RESULT_DIR}"
    fi
    if [[ -n "${SUDO_UID:-}" && -n "${SUDO_GID:-}" ]]; then
        for endpoint in ric du; do
            local_spool="${SPOOL_ROOT}/${endpoint}/${RUN_ID}"
            if [[ -d "${local_spool}" ]]; then
                chown -R "${SUDO_UID}:${SUDO_GID}" "${local_spool}"
                chmod -R u+rwX,go+rX "${local_spool}"
            fi
        done
    fi
}
trap cleanup EXIT

agent_event() {
    if [[ -n "${2:-}" ]]; then
        python3 "${ARTIFACTS}" event --output "${RESULT_DIR}/events.jsonl" \
            --name "$1" --endpoint "$2"
    else
        python3 "${ARTIFACTS}" event --output "${RESULT_DIR}/events.jsonl" --name "$1"
    fi
}

wait_for_vici() {
    local endpoint=$1
    for _ in {1..40}; do
        docker exec "${endpoint}" swanctl --stats >/dev/null 2>&1 && return 0
        sleep 0.25
    done
    fail "charon/VICI did not become ready in ${endpoint}"
}

configure_ipsec() {
    local ric_config="${PROJECT_DIR}/strongswan/swanctl-ric.conf"
    local du_config="${PROJECT_DIR}/strongswan/swanctl-du.conf"
    local connection="m2-classical"
    if [[ "${MODE}" = M3 ]]; then
        ric_config="${PROJECT_DIR}/strongswan/swanctl-pqc-ric.conf"
        du_config="${PROJECT_DIR}/strongswan/swanctl-pqc-du.conf"
        connection="m3-hybrid"
    fi

    printf '\nStarting strongSwan and loading the %s profile\n' "${MODE}"
    docker cp "${ric_config}" \
        "${RIC}:/etc/swanctl/conf.d/connection.conf" >/dev/null
    docker cp "${du_config}" \
        "${DU}:/etc/swanctl/conf.d/connection.conf" >/dev/null

    SECRET_FILE="$(umask 077 && mktemp)"
    local psk
    psk="$(openssl rand -hex 32)"
    printf 'secrets {\n  ike-runtime {\n    id-ric = ric\n    id-du = du\n    secret = 0x%s\n  }\n}\n' \
        "${psk}" > "${SECRET_FILE}"
    unset psk
    docker cp "${SECRET_FILE}" "${RIC}:/etc/swanctl/conf.d/runtime-secret.conf" >/dev/null
    docker cp "${SECRET_FILE}" "${DU}:/etc/swanctl/conf.d/runtime-secret.conf" >/dev/null
    unlink "${SECRET_FILE}"
    SECRET_FILE=""

    docker exec --detach "${RIC}" sh -c \
        'exec /usr/libexec/ipsec/charon >/tmp/charon.log 2>&1'
    docker exec --detach "${DU}" sh -c \
        'exec /usr/libexec/ipsec/charon >/tmp/charon.log 2>&1'
    wait_for_vici "${RIC}"
    wait_for_vici "${DU}"
    docker exec "${RIC}" swanctl --load-all
    docker exec "${DU}" swanctl --load-all

    # The daemon has loaded the credentials; remove their filesystem copies so
    # they cannot enter subsequently collected artifacts.
    docker exec "${RIC}" unlink /etc/swanctl/conf.d/runtime-secret.conf
    docker exec "${DU}" unlink /etc/swanctl/conf.d/runtime-secret.conf

    agent_event ike_start ric
    docker exec "${RIC}" swanctl --initiate --child e2 --timeout 15 \
        | tee "${RESULT_DIR}/initiate.txt"
    docker exec "${RIC}" swanctl --list-sas --pretty \
        | tee "${RESULT_DIR}/ric-sas.txt"
    docker exec "${DU}" swanctl --list-sas --pretty \
        | tee "${RESULT_DIR}/du-sas.txt"

    grep -Eqi 'ESTABLISHED' "${RESULT_DIR}/ric-sas.txt" || fail "IKE SA is not established"
    grep -Eqi 'INSTALLED' "${RESULT_DIR}/ric-sas.txt" || fail "CHILD SA is not installed"
    agent_event child_sa_installed ric
    grep -Eqi 'CURVE_25519|X25519' "${RESULT_DIR}/ric-sas.txt" || fail "X25519 was not negotiated"
    if [[ "${MODE}" = M2 ]]; then
        ! grep -Eqi 'ML.?KEM' "${RESULT_DIR}/ric-sas.txt" \
            || fail "ML-KEM appeared in classical mode"
    else
        grep -Eqi 'ML.?KEM.?768' "${RESULT_DIR}/ric-sas.txt" \
            || fail "ML-KEM-768 was not negotiated"
    fi
}

containerlab_cleanup
clab deploy --topo "${TOPOLOGY}" --reconfigure

printf '\nStarting endpoint-local agents on the management network\n'
for endpoint in ric du; do
    container="clab-openran-pqc-${endpoint}"
    docker exec --detach "${container}" pqc-agent \
        --node-id "${endpoint}" --run-id "${RUN_ID}" --mode "${MODE}" \
        --collector clab-openran-pqc-collector:50051 --insecure --sample-interval 1.0
done

python3 "${ARTIFACTS}" manifest --output "${RESULT_DIR}/manifest.json" \
    --run-id "${RUN_ID}" --mode "${MODE}" --image "${IMAGE}" \
    --experiment-kind "${EXPERIMENT_KIND}" \
    --topology "${TOPOLOGY}" --profile "${PROFILE_FILE}"
agent_event lab_deployed

printf '\nChecking experimental-link health\n'
for endpoint in "${RIC}" "${DU}"; do
    docker inspect --format '{{.State.Running}}' "${endpoint}" | grep -qx true \
        || fail "${endpoint} is not running"
    docker exec "${endpoint}" ip -4 address show dev eth1 | grep -q '10.10.0.' \
        || fail "${endpoint} has no experimental address"
done
docker exec "${RIC}" ping -I eth1 -c 3 -W 1 10.10.0.2 | tee "${RESULT_DIR}/icmp-before-ipsec.txt"

printf '\nStarting capture on the experimental link\n'
CAPTURE_PID="$(docker exec "${RIC}" sh -c \
    'tcpdump -U -n -i eth1 -w /tmp/experiment.pcap >/tmp/tcpdump.log 2>&1 & echo $!')"
sleep 1
agent_event capture_started ric

if [[ "${MODE}" = M1 ]]; then
    printf '\nChecking absence of XFRM state and policy\n'
    for endpoint in "${RIC}" "${DU}"; do
        [[ -z "$(docker exec "${endpoint}" ip xfrm state list)" ]] || fail "${endpoint} has XFRM state in M1"
        [[ -z "$(docker exec "${endpoint}" ip xfrm policy list)" ]] || fail "${endpoint} has XFRM policy in M1"
    done
else
    configure_ipsec
fi

printf '\nRunning smoke traffic on eth1\n'
agent_event traffic_start

docker exec "${RIC}" ping -I eth1 -c 3 -W 1 10.10.0.2 \
    | tee "${RESULT_DIR}/icmp.txt"
if [[ "${EXPERIMENT_KIND}" != establishment ]]; then
    docker exec --detach "${DU}" sh -c 'exec iperf3 -s -B 10.10.0.2 -1 >/tmp/iperf-tcp.log 2>&1'
    sleep 0.3
    docker exec "${RIC}" iperf3 -c 10.10.0.2 -B 10.10.0.1 -b 10M -t 1 -J \
        > "${RESULT_DIR}/tcp.json"
    docker exec --detach "${DU}" sh -c 'exec iperf3 -s -B 10.10.0.2 -1 >/tmp/iperf-udp.log 2>&1'
    sleep 0.3
    docker exec "${RIC}" iperf3 -c 10.10.0.2 -B 10.10.0.1 -u -t 1 -J > "${RESULT_DIR}/udp.json"

    docker exec "${DU}" python3 /opt/openran-pqc/traffic/sctp_server.py \
        --bind 10.10.0.2 --port "${SCTP_PORT}" --count "${SCTP_COUNT}" \
        >"${RESULT_DIR}/sctp-server.jsonl" 2>&1 &
    SERVER_HOST_PID=$!
    sleep 0.5
    docker exec "${RIC}" python3 /opt/openran-pqc/traffic/sctp_client.py \
        --bind 10.10.0.1 --host 10.10.0.2 --port "${SCTP_PORT}" \
        --count "${SCTP_COUNT}" --rate "${SCTP_RATE}" \
        | tee "${RESULT_DIR}/sctp-client.jsonl"
    wait "${SERVER_HOST_PID}"
fi
agent_event traffic_end

if [[ "${MODE}" != M1 && "${EXPERIMENT_KIND}" != steady ]]; then
    CONNECTION_NAME="m2-classical"
    [[ "${MODE}" = M3 ]] && CONNECTION_NAME="m3-hybrid"
    printf '\nPerforming a controlled IKE SA rekey\n'
    agent_event ike_rekey_start ric
    docker exec "${RIC}" swanctl --rekey --ike "${CONNECTION_NAME}" --pretty \
        | tee "${RESULT_DIR}/ike-rekey.txt"
    agent_event ike_rekey_end ric
    docker exec "${RIC}" ping -I eth1 -c 3 -W 1 10.10.0.2 \
        | tee "${RESULT_DIR}/icmp-after-ike-rekey.txt"

    printf '\nPerforming a controlled CHILD SA rekey\n'
    agent_event child_rekey_start ric
    docker exec "${RIC}" swanctl --rekey --child e2 --pretty \
        | tee "${RESULT_DIR}/child-rekey.txt"
    agent_event child_rekey_end ric
    docker exec "${RIC}" ping -I eth1 -c 3 -W 1 10.10.0.2 \
        | tee "${RESULT_DIR}/icmp-after-rekey.txt"
    docker exec "${RIC}" swanctl --list-sas --pretty \
        | tee "${RESULT_DIR}/ric-sas-after-rekey.txt"
    grep -Eqi 'ESTABLISHED' "${RESULT_DIR}/ric-sas-after-rekey.txt" \
        || fail "IKE SA was lost during rekey"
    grep -Eqi 'INSTALLED' "${RESULT_DIR}/ric-sas-after-rekey.txt" \
        || fail "CHILD SA was not installed after rekey"
fi

docker exec "${RIC}" kill -INT "${CAPTURE_PID}" || true
CAPTURE_PID=""
agent_event capture_stopped ric
sleep 1
docker cp "${RIC}:/tmp/experiment.pcap" "${RESULT_DIR}/capture.pcap" >/dev/null

SCTP_PACKETS="$(docker exec "${RIC}" tshark -r /tmp/experiment.pcap -Y sctp -T fields -e sctp.srcport 2>/dev/null | wc -l)"
ESP_PACKETS="$(docker exec "${RIC}" tshark -r /tmp/experiment.pcap -Y esp -T fields -e esp.spi 2>/dev/null | wc -l)"
IKE_PACKETS="$(docker exec "${RIC}" tshark -r /tmp/experiment.pcap -Y isakmp -T fields -e isakmp.exchangetype 2>/dev/null | wc -l)"
IKE_INTERMEDIATE_PACKETS="$(docker exec "${RIC}" tshark -r /tmp/experiment.pcap \
    -Y 'isakmp.exchangetype == 43' -T fields -e isakmp.exchangetype 2>/dev/null | wc -l)"
MLKEM_EXCHANGE_NS=null
if [[ "${MODE}" = M3 ]]; then
    MLKEM_EXCHANGE_NS="$(docker exec "${RIC}" tshark -r /tmp/experiment.pcap \
        -Y 'isakmp.exchangetype == 43' -T fields -e frame.time_epoch 2>/dev/null \
        | awk 'NR==1{start=$1} NR==2{printf "%.0f", ($1-start)*1000000000; exit}')"
    [[ -n "${MLKEM_EXCHANGE_NS}" ]] || MLKEM_EXCHANGE_NS=null
fi

if [[ "${MODE}" = M1 ]]; then
    [[ "${SCTP_PACKETS}" -gt 0 ]] || fail "SCTP was not visible in clear text"
    [[ "${ESP_PACKETS}" -eq 0 ]] || fail "ESP appeared in M1 baseline"
    XFRM_PACKETS=0
else
    [[ "${SCTP_PACKETS}" -eq 0 ]] || fail "clear-text SCTP appeared in ${MODE}"
    [[ "${ESP_PACKETS}" -gt 0 ]] || fail "no ESP was captured in ${MODE}"
    docker exec "${RIC}" ip -s xfrm state \
        | sed -E 's/(aead [^ ]+ )0x[[:xdigit:]]+/\1<redacted>/' \
        | tee "${RESULT_DIR}/ric-xfrm.txt"
    docker exec "${DU}" ip -s xfrm state \
        | sed -E 's/(aead [^ ]+ )0x[[:xdigit:]]+/\1<redacted>/' \
        | tee "${RESULT_DIR}/du-xfrm.txt"
    XFRM_PACKETS="$(awk '/lifetime current:/{getline; if (match($0, /[0-9]+\(packets\)/)) {v=substr($0,RSTART,RLENGTH); sub(/\(packets\)/,"",v); sum+=v}} END{print sum+0}' "${RESULT_DIR}/ric-xfrm.txt")"
    [[ "${XFRM_PACKETS}" -gt 0 ]] || fail "XFRM counters did not increase"
    docker cp "${RIC}:/tmp/charon.log" "${RESULT_DIR}/ric-charon.log" >/dev/null
    docker cp "${DU}:/tmp/charon.log" "${RESULT_DIR}/du-charon.log" >/dev/null
    if [[ "${MODE}" = M3 ]]; then
        [[ "${IKE_INTERMEDIATE_PACKETS}" -gt 0 ]] \
            || fail "IKE_INTERMEDIATE was not captured on eth1"
        grep -Eqi 'IKE_INTERMEDIATE' "${RESULT_DIR}/ric-charon.log" \
            || fail "IKE_INTERMEDIATE was not observed"
        grep -Eqi 'ML.?KEM.?768' "${RESULT_DIR}/ric-charon.log" \
            || fail "ML-KEM-768 was not observed in the daemon log"
        agent_event ike_intermediate_observed ric

        if [[ "${EXPERIMENT_KIND}" = combined ]]; then
            printf '\nRunning strict no-downgrade negative test\n'
            docker exec "${RIC}" swanctl --terminate --ike m3-hybrid >/dev/null
            docker cp "${PROJECT_DIR}/strongswan/swanctl-du.conf" \
                "${DU}:/etc/swanctl/conf.d/connection.conf" >/dev/null
            docker exec "${DU}" swanctl --load-conns >/dev/null
            set +e
            docker exec "${RIC}" swanctl --initiate --child e2 --timeout 5 \
                > "${RESULT_DIR}/negative-no-downgrade.txt" 2>&1
            NEGATIVE_STATUS=$?
            set -e
            [[ "${NEGATIVE_STATUS}" -ne 0 ]] \
                || fail "strict hybrid profile silently downgraded to the classical peer"
            grep -Eqi 'NO_PROPOSAL_CHOSEN|no proposal|failed' \
                "${RESULT_DIR}/negative-no-downgrade.txt" \
                || fail "negative test failed without explicit proposal evidence"
        fi
    fi
    if rg -i '(secret[[:space:]]*=|aead .*0x[[:xdigit:]]{32})' "${RESULT_DIR}"; then
        fail "possible secret material found in collected artifacts"
    fi
fi

jq -n --arg run_id "${RUN_ID}" --arg mode "${MODE}" \
    --arg experiment_kind "${EXPERIMENT_KIND}" \
    --argjson sctp_packets "${SCTP_PACKETS}" --argjson esp_packets "${ESP_PACKETS}" \
    --argjson xfrm_packets "${XFRM_PACKETS}" --argjson ike_packets "${IKE_PACKETS}" \
    --argjson ike_intermediate_packets "${IKE_INTERMEDIATE_PACKETS}" \
    --argjson mlkem_exchange_ns "${MLKEM_EXCHANGE_NS}" \
    '{run_id:$run_id, mode:$mode, experiment_kind:$experiment_kind,
      status:"pass", cleartext_sctp_packets:$sctp_packets,
      esp_packets:$esp_packets, xfrm_packets:$xfrm_packets,
      ike_packets:$ike_packets, ike_intermediate_packets:$ike_intermediate_packets,
      mlkem_exchange_ns:$mlkem_exchange_ns,
      xfrm_states:(if $mode == "M1" then 0 else 2 end),
      xfrm_policies:(if $mode == "M1" then 0 else 2 end)}' > "${RESULT_DIR}/summary.json"

agent_event run_complete
docker exec "${RIC}" pkill -INT -f 'pqc-agent' >/dev/null 2>&1 || true
docker exec "${DU}" pkill -INT -f 'pqc-agent' >/dev/null 2>&1 || true
sleep 1
python3 "${ARTIFACTS}" finalize --result-dir "${RESULT_DIR}" \
    --telemetry-dir "${DISTRIBUTED_RESULT_DIR}"
python3 "${ARTIFACTS}" validate --result-dir "${RESULT_DIR}" \
    --telemetry-dir "${DISTRIBUTED_RESULT_DIR}"

printf '\nPASS: %s met its negotiation and dataplane acceptance criteria.\n' "${MODE}"
printf 'Evidence: %s\n' "${RESULT_DIR}"

# When the complete runner is invoked with sudo, return readable artifacts to
# the original workspace user. This happens only after secret scanning.
if [[ -n "${SUDO_UID:-}" && -n "${SUDO_GID:-}" ]]; then
    chown -R "${SUDO_UID}:${SUDO_GID}" "${RESULT_DIR}"
    chmod -R u+rwX,go+rX "${RESULT_DIR}"
fi
