#!/bin/bash
# Oracle run: the reference policy over MCP HTTP. solution/ exists only in Harbor oracle runs.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHONPATH="$DIR" python -m oncall.cli solve --url http://oncall-sim:8000/mcp
