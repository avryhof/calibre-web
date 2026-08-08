#!/usr/bin/env bash
# Builds the Calibre plugin zip for installation.
# All plugin modules live at the zip root (Calibre requires a top-level
# __init__.py); plugin-import-name-calibrewebsync.txt is what makes Calibre
# import the plugin as calibre_plugins.calibrewebsync.
set -euo pipefail
cd "$(dirname "$0")"
rm -f calibrewebsync.zip
cd calibrewebsync
zip -r ../calibrewebsync.zip . -x '*.pyc' -x '*__pycache__*'
cd ..
echo "Built calibre-plugin/calibrewebsync.zip"
