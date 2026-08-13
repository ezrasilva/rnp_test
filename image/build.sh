#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
readonly IMAGE="${OPENRAN_PQC_IMAGE:-openran-pqc:6.0.7}"

docker build --pull --tag "${IMAGE}" --file "${SCRIPT_DIR}/Dockerfile" "${PROJECT_DIR}"

printf 'Built %s\n' "${IMAGE}"
docker image inspect "${IMAGE}" --format 'image_id={{.Id}}'

