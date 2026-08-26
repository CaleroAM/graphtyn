#!/usr/bin/env bash
# Portable stdio wrapper. Install Graphtyn in the runtime environment or set
# GRAPHTYN_SOURCE_PATH; set GRAPHTYN_PROJECT_PATH to the path visible there.
: "${GRAPHTYN_PROJECT_PATH:?define GRAPHTYN_PROJECT_PATH}"
if [[ -n "${GRAPHTYN_SOURCE_PATH:-}" ]]; then
  export PYTHONPATH="${GRAPHTYN_SOURCE_PATH}${PYTHONPATH:+:$PYTHONPATH}"
fi
exec python3 -m graphtyn.cli mcp --path "${GRAPHTYN_PROJECT_PATH}"
