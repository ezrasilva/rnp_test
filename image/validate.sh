#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
readonly IMAGE="${OPENRAN_PQC_IMAGE:-openran-pqc:6.0.7}"
readonly RUN_ID="${IMAGE_RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
readonly RESULT_DIR="${PROJECT_DIR}/results/image/${RUN_ID}"
readonly ENDPOINTS=(ric du)
RUNNING_CONTAINERS=()

mkdir -p "${RESULT_DIR}"
exec > >(tee "${RESULT_DIR}/validation.log") 2>&1

fail() {
    printf 'FAIL: %s\n' "$*"
    exit 1
}

cleanup() {
    if ((${#RUNNING_CONTAINERS[@]})); then
        docker rm -f "${RUNNING_CONTAINERS[@]}" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

check_endpoint() {
    local endpoint=$1
    local output="${RESULT_DIR}/${endpoint}-algorithms.txt"
    local stats="${RESULT_DIR}/${endpoint}-stats.txt"
    local container="openran-pqc-image-${endpoint}"

    docker run --detach --name "${container}" --cap-add NET_ADMIN --cap-add NET_RAW \
        "${IMAGE}" >/dev/null
    RUNNING_CONTAINERS+=("${container}")
    for _ in {1..20}; do
        docker exec "${container}" swanctl --stats >/dev/null 2>&1 && break
        sleep 0.25
    done
    docker exec "${container}" swanctl --version \
        | tee "${RESULT_DIR}/${endpoint}-version.txt"
    docker exec "${container}" swanctl --list-algs | tee "${output}"
    docker exec "${container}" swanctl --stats | tee "${stats}"

    grep -Eqi 'X25519|CURVE_25519' "${output}" \
        || fail "${endpoint}: X25519 is unavailable"
    grep -Eqi 'ML.?KEM.?768' "${output}" \
        || fail "${endpoint}: ML-KEM-768 is unavailable"
    grep -Eqi 'ml([^[:alnum:]]|$)' "${output}" \
        || fail "${endpoint}: ml plugin is not reported"
    grep -Eqi 'vici' "${stats}" \
        || fail "${endpoint}: vici plugin is not reported"
    grep -Eqi 'kernel-netlink' "${stats}" \
        || fail "${endpoint}: kernel-netlink plugin is not reported"

    docker rm -f "${container}" >/dev/null
}

for endpoint in "${ENDPOINTS[@]}"; do
    printf '\nValidating endpoint %s\n' "${endpoint}"
    check_endpoint "${endpoint}"
done

docker run --rm "${IMAGE}" cat /usr/share/openran-pqc/components.txt \
    > "${RESULT_DIR}/components.txt"

docker run --rm "${IMAGE}" sh -c '
    for tool in charon swanctl ip tc tcpdump tshark iperf3 ping sctp_test python3; do
        if [ "$tool" = charon ]; then
            test -x /usr/libexec/ipsec/charon
        else
            command -v "$tool" >/dev/null
        fi
    done
' || fail "one or more required runtime tools are unavailable"

jq -Rn '
  [inputs
   | select(length > 0)
   | capture("^(?<name>[^=]+)=(?<version>.*)$")
   | {type: "library", name: .name, version: .version}]
  | {
      bomFormat: "CycloneDX",
      specVersion: "1.5",
      version: 1,
      metadata: {component: {type: "container", name: "openran-pqc", version: "6.0.7"}},
      components: .
    }
' < "${RESULT_DIR}/components.txt" > "${RESULT_DIR}/sbom.cdx.json"

if docker history --no-trunc "${IMAGE}" \
    | grep -Eqi '(psk|password|private[_ -]?key|secret=)'; then
    fail "the image history contains a possible embedded credential"
fi

IMAGE_ID="$(docker image inspect "${IMAGE}" --format '{{.Id}}')"
BASE_DIGEST="$(sed -n 's/^ARG DEBIAN_DIGEST=//p' "${SCRIPT_DIR}/Dockerfile")"
SOURCE_SHA256="$(sed -n 's/^ARG STRONGSWAN_SHA256=//p' "${SCRIPT_DIR}/Dockerfile")"

jq -n \
    --arg run_id "${RUN_ID}" \
    --arg image "${IMAGE}" \
    --arg image_id "${IMAGE_ID}" \
    --arg base_digest "${BASE_DIGEST}" \
    --arg source_sha256 "${SOURCE_SHA256}" \
    '{
      run_id: $run_id,
      status: "pass",
      image: $image,
      image_id: $image_id,
      strongswan_version: "6.0.7",
      base_image_digest: $base_digest,
      strongswan_source_sha256: $source_sha256,
      sbom: "sbom.cdx.json",
      embedded_credentials_check: "pass",
      validated_endpoints: ["ric", "du"],
      required_algorithms: ["X25519", "ML-KEM-768"],
      required_plugins: ["vici", "kernel-netlink", "ml"]
    }' > "${RESULT_DIR}/manifest.json"

printf '\nPASS: reproducible image exposes X25519, ML-KEM-768, VICI and kernel-netlink.\n'
printf 'Evidence: %s\n' "${RESULT_DIR}"
