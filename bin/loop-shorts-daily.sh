#!/usr/bin/env bash
# Cut and schedule one Short a day, straight from renders/<slug>-final.mp4.
#
# One a day comfortably feeds a 4/week release schedule and stays weeks ahead of
# it. Nothing is rendered here: shorts.py crops the master's burned caption band
# off and redraws the source credit, so the finished episode is the only input.
# Ends by itself once every finished episode has a Short.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
exec .venv/bin/python loop/shorts_lane.py --limit 1
