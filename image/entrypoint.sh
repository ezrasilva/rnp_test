#!/bin/sh
set -eu

if [ "${1:-}" = "charon" ]; then
    shift
    exec /usr/libexec/ipsec/charon "$@"
fi

exec "$@"

