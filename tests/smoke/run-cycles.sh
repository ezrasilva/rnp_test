#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
readonly CAMPAIGN_ID="${CAMPAIGN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"

for cycle in 1 2 3; do
    printf '\n=== M1 deploy/run/destroy cycle %d/3 ===\n' "${cycle}"
    RUN_ID="${CAMPAIGN_ID}-m1-cycle-${cycle}" "${PROJECT_DIR}/experiments/run.sh" m1
done

for cycle in 1 2 3; do
    jq -e '.status == "pass" and .mode == "M1" and .xfrm_states == 0 and
           .xfrm_policies == 0 and .esp_packets == 0 and .cleartext_sctp_packets > 0' \
        "${PROJECT_DIR}/results/experiments/${CAMPAIGN_ID}-m1-cycle-${cycle}/summary.json" >/dev/null
done

printf '\nPASS: all three complete M1 cycles met the Gate 2 criteria.\n'

