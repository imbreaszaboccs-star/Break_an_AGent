#!/bin/bash
# Replays the recorded tool calls on a fresh copy of the simulator and writes the reward.
# A missing trace (agent never called a tool) scores as do-nothing.
mkdir -p /logs/verifier
PYTHONPATH=/tests python -m triage_env.score --trace /logs/agent/triage_trace.json --out /logs/verifier
