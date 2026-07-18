#!/usr/bin/env bash
# Fetch the official SRD 5.2.1 PDF from Wizards of the Coast and verify integrity.
set -euo pipefail
cd "$(dirname "$0")"

URL="https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf"
OUT="SRD_CC_v5.2.1.pdf"

curl -fL --retry 3 -o "$OUT" "$URL"

if [[ -f "$OUT.sha256" ]]; then
  shasum -a 256 -c "$OUT.sha256"
else
  shasum -a 256 "$OUT" > "$OUT.sha256"
  echo "Recorded new hash: $(cat "$OUT.sha256")"
fi
