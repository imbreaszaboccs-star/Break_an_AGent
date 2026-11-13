#!/bin/bash
# Oracle: the scripted reference policy, using only the information the tools expose.
mkdir -p /logs/agent
PYTHONPATH=/opt/triage python -m triage_env.baselines reference --trace /logs/agent/triage_trace.json
