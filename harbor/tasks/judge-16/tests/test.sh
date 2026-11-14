#!/bin/bash
# Asks the sim sidecar for the final score. Any failure leaves the reward at 0.
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt
curl -sS --fail --max-time 240 -X POST -H "Authorization: Bearer d15aa52374799aa4ff2b818aa67a66ee3388a9b0c503dabe4c4d71e4a50180a6" \
  http://oncall-sim:8000/admin/finalize -o /logs/verifier/reward_breakdown.json || exit 0
python3 - <<'EOF' || echo 0 > /logs/verifier/reward.txt
import json
score = float(json.load(open("/logs/verifier/reward_breakdown.json"))["score"])
open("/logs/verifier/reward.txt", "w").write(str(score))
EOF
exit 0
