#!/bin/sh
set -eu

# Keep the namespace alive. Configuration is deliberately performed by the
# host-side gate so each command and its output can be recorded as evidence.
exec sleep infinity

