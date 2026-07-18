#!/usr/bin/env bash
# Fetch the official SRD 5.1 (2014 rules, CC-BY-4.0) PDF and verify its hash.
set -euo pipefail
cd "$(dirname "$0")"
URL="https://media.wizards.com/2023/downloads/dnd/SRD_CC_v5.1.pdf"
OUT="SRD_CC_v5.1.pdf"
curl -fL --retry 3 -o "$OUT" "$URL"
shasum -a 256 -c "$OUT.sha256"
