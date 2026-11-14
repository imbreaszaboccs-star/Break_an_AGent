#!/bin/bash
# Asks the sim sidecar for the final score. Any failure leaves the reward at 0.
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt
curl -sS --fail --max-time 240 -X POST -H "Authorization: Bearer a4dc7d35cedbf8ab6bd7060f613d96ec8f00b39c0e31b7d34cf4065b54715287" \
  http://oncall-sim:8000/admin/finalize -o /logs/verifier/reward_breakdown.json || exit 0
python3 - <<'EOF' || echo 0 > /logs/verifier/reward.txt
import json
score = float(json.load(open("/logs/verifier/reward_breakdown.json"))["score"])
open("/logs/verifier/reward.txt", "w").write(str(score))
EOF
exit 0
