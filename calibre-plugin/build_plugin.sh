#!/usr/bin/env bash
# Builds the Calibre plugin zip for installation.
set -euo pipefail
cd "$(dirname "$0")"
rm -f calibrewebsync.zip
cd calibrewebsync
zip -r ../calibrewebsync.zip . -x '*.pyc' -x '*__pycache__*'
cd ..
echo "Built calibre-plugin/calibrewebsync.zip"
