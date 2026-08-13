#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
readonly TEST_RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)-m3}"
readonly RESULT_DIR="${PROJECT_DIR}/results/experiments/${TEST_RUN_ID}"

RUN_ID="${TEST_RUN_ID}" "${PROJECT_DIR}/experiments/run.sh" m3

jq -e '.status == "pass" and .mode == "M3" and
       .cleartext_sctp_packets == 0 and .esp_packets > 0 and .xfrm_packets > 0 and
       .ike_packets > 0 and .ike_intermediate_packets > 0 and
       .grpc_packets_on_experimental_link == 0' \
    "${RESULT_DIR}/summary.json" >/dev/null
grep -Eqi 'ML.?KEM.?768' "${RESULT_DIR}/ric-sas.txt"
grep -Eqi 'IKE_INTERMEDIATE' "${RESULT_DIR}/ric-charon.log"
grep -Eqi 'NO_PROPOSAL_CHOSEN|no proposal|failed' "${RESULT_DIR}/negative-no-downgrade.txt"

printf 'PASS: M3 hybrid integration and strict no-downgrade checks succeeded.\n'
