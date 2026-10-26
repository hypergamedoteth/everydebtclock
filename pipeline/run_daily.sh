#!/usr/bin/env bash
# Daily job: fetch + validate + rebuild. Schedule (America/Chicago):
#   0 6 * * *   (morning recalibration; picks up Census/BEA/MTS changes)
#   30 15 * * 1-5  (after Treasury's ~4 PM ET Debt to the Penny + DTS release)
set -euo pipefail
cd "$(dirname "$0")/.."
python3 pipeline/fetch.py
python3 build.py
# deploy step goes here (e.g. `wrangler pages deploy .` or git push to the static host) — not run in the prototype
