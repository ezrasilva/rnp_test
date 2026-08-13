#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
readonly TEST_RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)-m2}"
readonly SUMMARY="${PROJECT_DIR}/results/experiments/${TEST_RUN_ID}/summary.json"

RUN_ID="${TEST_RUN_ID}" "${PROJECT_DIR}/experiments/run.sh" m2

jq -e '.status == "pass" and .mode == "M2" and
       .cleartext_sctp_packets == 0 and .esp_packets > 0 and .xfrm_packets > 0 and
       .grpc_packets_on_experimental_link == 0' \
    "${SUMMARY}" >/dev/null

printf 'PASS: M2 classical integration checks succeeded.\n'
