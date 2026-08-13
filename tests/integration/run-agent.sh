#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
readonly MODE_ARG="${1:-m3}"
readonly TEST_RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)-agent-${MODE_ARG}}"
readonly RESULT_DIR="${PROJECT_DIR}/results/experiments/${TEST_RUN_ID}"

RUN_ID="${TEST_RUN_ID}" "${PROJECT_DIR}/experiments/run.sh" "${MODE_ARG}"

python3 "${PROJECT_DIR}/experiments/artifacts.py" validate \
    --result-dir "${RESULT_DIR}" \
    --telemetry-dir "${PROJECT_DIR}/results/distributed/${TEST_RUN_ID}"
jq -e '.agent_schema_version == 1 and .metric_samples > 0 and
       (.durations.traffic_ns // 0) > 0' "${RESULT_DIR}/summary.json" >/dev/null
jq -e '.schema_version == 2 and .telemetry_architecture == "distributed-grpc" and
       .agent_enabled == true' "${RESULT_DIR}/manifest.json" >/dev/null

printf 'PASS: agent generated and validated a self-contained %s run.\n' "${MODE_ARG^^}"
