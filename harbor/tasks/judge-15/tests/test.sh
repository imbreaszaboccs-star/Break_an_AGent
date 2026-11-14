#!/bin/bash
# Asks the sim sidecar for the final score. Any failure leaves the reward at 0.
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt
curl -sS --fail --max-time 240 -X POST -H "Authorization: Bearer 06e4df9a9f5e7de0c1397e2ad8823947735cf998b141f3c7d64132d02a94dbb4" \
  http://oncall-sim:8000/admin/finalize -o /logs/verifier/reward_breakdown.json || exit 0
python3 - <<'EOF' || echo 0 > /logs/verifier/reward.txt
import json
score = float(json.load(open("/logs/verifier/reward_breakdown.json"))["score"])
open("/logs/verifier/reward.txt", "w").write(str(score))
EOF
exit 0
