#!/usr/bin/env sh
# The one dependency, pinned: forge-std (test helpers only; the contract itself imports nothing).
set -eu
cd "$(dirname "$0")"
[ -d lib/forge-std ] || git clone -q --depth 1 --branch v1.17.0 https://github.com/foundry-rs/forge-std lib/forge-std
